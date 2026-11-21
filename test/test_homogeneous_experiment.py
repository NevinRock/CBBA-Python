"""Independent validation and branch coverage for Experiment 1."""
import copy
import contextlib
import io
import json
import math
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from test import run_homogeneous_experiment as exp


def fixture(affected=2, held=1, outside=1):
    """Small deterministic policy fixture; five affected is a synthetic guard case."""
    config = exp.load_config()
    agents = [exp.Agent(agent_id=i, agent_type=0, nom_velocity=5, x=x)
              for i, x in enumerate((0, 10, 100))]
    groups = [list(range(affected)), list(range(affected, affected + held)),
              list(range(affected + held, affected + held + outside))]
    tasks = [exp.Task(task_id=i, task_type=0, task_value=100, x=float(i),
                      start_time=0, end_time=240, duration=8, discount=.02)
             for i in range(affected + held + outside)]
    paths = dict(enumerate(groups))
    starts = {}
    for agent, path in zip(agents, groups):
        previous_end, x = 0, agent.x
        starts[agent.agent_id] = []
        for task_id in path:
            start = previous_end + abs(x - tasks[task_id].x) / 5
            starts[agent.agent_id].append(start)
            previous_end, x = start + 8, tasks[task_id].x
    return exp.PreparedTrial(0, config, agents, tasks, exp.WorldInfo([0, 100], [0, 100], [0, 0]),
        {t: a for a, path in paths.items() for t in path}, 0, paths, starts,
        {"valid": True, "complete": True, "broadcasts": 123, "rounds": 99})


def remove_timing(value):
    if isinstance(value, dict):
        return {k: remove_timing(v) for k, v in value.items() if k not in exp.TIMING_FIELDS}
    if isinstance(value, (list, tuple)):
        return [remove_timing(v) for v in value]
    return value


class HomogeneousExperimentTest(unittest.TestCase):
    def test_all_scale_parameters_and_compatibility(self):
        for n, m in ((6, 18), (12, 36), (24, 72)):
            with self.subTest(n=n):
                config, agents, tasks, world = exp.build_scenario(n, 0)
                self.assertEqual((len(agents), len(tasks)), (n, m))
                self.assertEqual(config["COMPATIBILITY"], {"robot": ["task"]})
                self.assertEqual(config["EXPERIMENT"]["MAX_DEPTH"], 4)
                self.assertEqual(config["EXPERIMENT"]["INCUMBENCY_BONUS"], .1)
                self.assertEqual(world.limit_x, [0, 100])
                self.assertTrue(all(a.agent_type == 0 and a.nom_velocity == 5 for a in agents))
                self.assertTrue(all(t.task_type == 0 and t.task_value == 100 and t.duration == 8
                                    and t.start_time == 0 and t.end_time == 240 and t.discount == .02
                                    for t in tasks))
                self.assertTrue(all(0 <= item.x <= 100 and 0 <= item.y <= 100 and item.z == 0
                                    for item in agents + tasks))
        self.assertNotEqual(exp.build_scenario(6, 0)[1], exp.build_scenario(6, 1)[1])
        with self.assertRaises(ValueError):
            exp.build_scenario(7, 0)

    def test_one_common_initial_auction_and_paired_input(self):
        with patch.object(exp, "run_auction", wraps=exp.run_auction) as calls:
            prepared, rows, details = exp.run_paired_trial(6, 1)
        initial_calls = [c for c in calls.call_args_list if c.args[7] == "initial"]
        self.assertEqual(len(initial_calls), 1)
        self.assertEqual(len({r["input_fingerprint"] for r in rows}), 1)
        self.assertEqual({r["failed_agent"] for r in rows}, {prepared.failed_agent})
        self.assertTrue(prepared.initial_paths[prepared.failed_agent])
        self.assertEqual(len({r["initial_broadcasts"] for r in rows}), 1)
        for row, detail in zip(rows, details):
            self.assertEqual(row["post_failure_broadcasts"], sum(e["broadcasts"] for e in detail["episodes"]))
            self.assertNotIn("initial", [e["scope"] for e in detail["episodes"]])
            self.assertNotIn(prepared.failed_agent, detail["final_paths"])
        before = exp.digest(exp.trial_snapshot(prepared))
        exp.run_method(prepared, exp.METHODS[0])
        self.assertEqual(before, exp.digest(exp.trial_snapshot(prepared)))

    def test_snapshot_fingerprint_survives_json_roundtrip(self):
        snapshot = exp.trial_snapshot(exp.prepare_trial(6, 1))
        saved = json.loads(json.dumps(snapshot, default=exp.json_default))
        self.assertEqual(exp.digest(snapshot), exp.digest(saved))

    def test_local_success_preserves_nonparticipants_and_scope(self):
        trial = fixture()
        row, detail = exp.run_method(trial, exp.METHODS[2])
        self.assertTrue(row["local_recovery_success"])
        self.assertEqual(row["auction_scope"], "local")
        self.assertEqual(detail["episodes"][0]["participant_ids"], [1])
        self.assertEqual(set(detail["episodes"][0]["task_ids"]), {0, 1, 2})
        self.assertEqual(detail["final_paths"][2], trial.initial_paths[2])
        self.assertEqual(detail["final_times"][2], trial.initial_times[2])
        self.assertEqual(row["global_broadcasts"], 0)
        self.assertEqual(row["global_rounds"], 0)
        self.assertEqual(row["status"], "ok")

    def test_no_candidates_skips_local_without_fabricated_cost(self):
        trial = fixture()
        trial.agents[1].x = 90
        row, detail = exp.run_method(trial, exp.METHODS[2])
        self.assertEqual(row["fallback_reason"], "no_nearby_capable_robot")
        self.assertFalse(row["local_attempted"])
        for field in ("local_broadcasts", "local_rounds", "local_runtime_seconds"):
            self.assertEqual(row[field], 0)
        self.assertEqual([e["scope"] for e in detail["episodes"]], ["global"])
        self.assertEqual(row["assigned_task_rate"], 1)

    def test_more_than_four_affected_skips_local(self):
        # Cannot occur in a valid capacity-four initial mission; exercise the defensive policy guard.
        trial = fixture(affected=5, held=0, outside=0)
        row, detail = exp.run_method(trial, exp.METHODS[2])
        self.assertEqual(row["affected_tasks"], 5)
        self.assertEqual(row["fallback_reason"], "too_many_affected_tasks")
        self.assertFalse(row["local_attempted"])
        self.assertEqual(row["local_rounds"], 0)
        self.assertEqual(row["assigned_task_rate"], 1)
        self.assertEqual(len(detail["episodes"]), 1)

    def test_failed_local_auction_accumulates_all_costs(self):
        trial = fixture(affected=2, held=3, outside=0)
        row, detail = exp.run_method(trial, exp.METHODS[2])
        self.assertEqual(row["fallback_reason"], "local_capacity_or_schedule_infeasible")
        self.assertTrue(row["local_attempted"])
        self.assertEqual(len(detail["episodes"]), 2)
        self.assertFalse(detail["episodes"][0]["complete"])
        self.assertTrue(detail["episodes"][1]["complete"])
        self.assertGreater(row["local_broadcasts"], 0)
        self.assertGreater(row["global_broadcasts"], 0)
        self.assertEqual(row["post_failure_broadcasts"], row["local_broadcasts"] + row["global_broadcasts"])
        self.assertEqual(row["consensus_rounds"], row["local_rounds"] + row["global_rounds"])
        self.assertAlmostEqual(row["auction_runtime_seconds"], row["local_runtime_seconds"] + row["global_runtime_seconds"])
        self.assertGreaterEqual(row["runtime_seconds"], row["auction_runtime_seconds"])
        self.assertEqual(row["broadcasts_per_affected_task"], row["post_failure_broadcasts"] / 2)
        self.assertEqual(row["status"], "ok")

    def test_radius_inclusive_boundary_and_per_task_eligibility(self):
        trial = fixture(affected=2, held=0, outside=0)
        trial.agents[1].x, trial.agents[2].x = 40, 41.000001
        candidates = exp.local_candidates(trial, [0, 1])
        self.assertEqual(candidates[0], [1])
        self.assertEqual(candidates[1], [1])
        trial.agents[2].x = 41
        candidates = exp.local_candidates(trial, [0, 1])
        self.assertEqual(candidates[0], [1])
        self.assertEqual(candidates[1], [1, 2])
        row, detail = exp.run_method(trial, exp.METHODS[2])
        self.assertTrue(row["local_recovery_success"])
        for agent, path in detail["episodes"][0]["paths"].items():
            for task in path:
                self.assertIn(agent, candidates[task])

    def test_schedule_validator_detects_each_constraint_and_true_score(self):
        trial = fixture()
        check = lambda paths, starts: exp.validate_schedule(trial.config, trial.agents, trial.tasks, paths, starts, 0)
        self.assertIn("duplicate_task_ownership", check({1: [0], 2: [0]}, {1: [2], 2: [20]})["errors"])
        self.assertIn("failed_agent_assigned", check({0: [0]}, {0: [0]})["errors"])
        self.assertIn("time_window:0", check({1: [0]}, {1: [241]})["errors"])
        self.assertIn("travel_time:0", check({1: [0]}, {1: [0]})["errors"])
        self.assertIn("capacity:1", check({1: [0] * 5}, {1: [2] * 5})["errors"])
        trial.config["COMPATIBILITY"]["robot"] = []
        self.assertIn("incompatible:1:0", check({1: [0]}, {1: [2]})["errors"])
        trial.config["COMPATIBILITY"]["robot"] = ["task"]
        self.assertAlmostEqual(check({1: [0]}, {1: [2]})["assignment_score"], 100 * math.exp(-.02 * 2))

    def test_real_solver_winner_and_bid_corruption_is_detected(self):
        trial = fixture()
        solver = exp.CBBA(trial.config)
        solver.solve(copy.deepcopy(trial.agents), copy.deepcopy(trial.tasks), trial.world, 4, True)
        self.assertTrue(exp.assess_consensus(solver)["valid"])
        solver.winner_bid_list[0][0] += 10
        self.assertFalse(exp.assess_consensus(solver)["valid"])
        solver.winner_bid_list[0][0] -= 10
        solver.winners_list[0][0] = -1
        self.assertFalse(exp.assess_consensus(solver)["valid"])

    def test_invalid_local_diagnostic_survives_global_recovery(self):
        real = exp.run_auction
        def corrupt(*args, **kwargs):
            result = real(*args, **kwargs)
            if result["scope"] == "local":
                result["valid"] = False
                result["errors"].append("injected_consensus_error")
            return result
        with patch.object(exp, "run_auction", side_effect=corrupt):
            row, detail = exp.run_method(fixture(), exp.METHODS[2])
        self.assertEqual(row["status"], "recovered_with_diagnostics")
        self.assertEqual(row["fallback_reason"], "local_invalid_or_solver_error")
        self.assertIn("injected_consensus_error", detail["episodes"][0]["errors"])
        self.assertTrue(row["complete"])

    def test_round_watchdog_retains_partial_diagnostic(self):
        trial = fixture()
        trial.config["EXPERIMENT"]["AUCTION_ROUND_LIMIT"] = 1
        row, detail = exp.run_method(trial, exp.METHODS[1])
        self.assertEqual(row["status"], "invalid")
        self.assertEqual(row["global_rounds"], 1)
        self.assertIn("AuctionRoundLimit", detail["episodes"][0]["exception"])
        self.assertIsNotNone(detail["episodes"][0]["partial_internal_paths_on_exception"])

    def test_incomplete_initial_is_retained_without_resampling(self):
        trial = fixture()
        trial.initial_auction["complete"] = False
        with patch.object(exp, "run_auction") as calls:
            row, detail = exp.run_method(trial, exp.METHODS[0])
        calls.assert_not_called()
        self.assertEqual(row["status"], "initial_invalid_or_incomplete")
        self.assertEqual(row["post_failure_broadcasts"], 0)
        self.assertEqual(detail["episodes"], [])

    def test_reproducibility_except_timing(self):
        for scale, seed in ((6, 2), (12, 1), (24, 0)):
            with self.subTest(scale=scale):
                first = exp.run_paired_trial(scale, seed)
                second = exp.run_paired_trial(scale, seed)
                self.assertEqual(exp.trial_snapshot(first[0]), exp.trial_snapshot(second[0]))
                self.assertEqual(remove_timing(first[1:]), remove_timing(second[1:]))
                self.assertEqual(first[2][0]["final_paths"], first[2][1]["final_paths"])
                self.assertEqual(first[2][0]["final_times"], first[2][1]["final_times"])
                for row in first[1]:
                    self.assertEqual(row["assigned_task_rate"], 1)
                    self.assertEqual(row["duplicate_tasks"], 0)
                    self.assertTrue(row["valid_assignment"])
                self.assertIsNone(first[1][0]["local_recovery_success"])

    def test_export_na_and_cli_safety(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "rows.csv"
            exp.write_csv(path, [{"local_recovery_success": None, "score": None}])
            self.assertIn("N/A,N/A", path.read_text())
            with contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as caught:
                    exp.main(["--full"])
                self.assertEqual(caught.exception.code, 2)
            (Path(temp) / "existing").write_text("preserve")
            with contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as caught:
                    exp.main(["--output-dir", temp])
                self.assertEqual(caught.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
