"""Tests for failed agents, warm start, inform rounds (CBBA) and the breaking-point runner."""

import copy
import unittest

from CBBA import CBBA
from test.run_breakpoints import CONFIG_PATH, SWEEPS, capacity_bound, n_groups, run_job
from test.run_exp3_shared import auction, build_mission, load_config


def warm_state(solver):
    return dict(winners=solver.winners_list, bids=solver.winner_bid_list,
                bundles=solver.bundle_list, paths=solver.path_list,
                times=solver.times_list, scores=solver.scores_list)


class FailedAgentTest(unittest.TestCase):
    def setUp(self):
        self.config = load_config()
        self.agents, self.tasks, self.world = build_mission(self.config, 12, 0)
        _, _, stats = auction(self.config, self.agents, self.tasks, self.world,
                              [a.agent_id for a in self.agents],
                              {t.task_id for t in self.tasks}, event_triggered=True)
        self.init = stats["solver"]
        self.dead = next(i for i, b in enumerate(self.init.bundle_list) if b)

    def solve(self, inform_round=None, max_rounds=None):
        solver = CBBA(self.config)
        paths, _ = solver.solve(copy.deepcopy(self.agents), copy.deepcopy(self.tasks), self.world,
                                max_depth=4, time_window_flag=True, event_triggered=True,
                                failed_agents={self.dead}, warm_start=copy.deepcopy(warm_state(self.init)),
                                inform_round=inform_round, max_rounds=max_rounds)
        return solver, paths

    def test_everyone_informed_reassigns_failed_robots_tasks(self):
        solver, paths = self.solve()
        live = [i for i in range(len(self.agents)) if i != self.dead]
        self.assertTrue(all(solver.winners_list[i] == solver.winners_list[live[0]] for i in live))
        self.assertNotIn(self.dead, solver.winners_list[live[0]])
        assigned = [t for i in live for t in paths[i] if t != -1]
        self.assertEqual(len(assigned), len(set(assigned)))
        self.assertTrue(all(self.dead not in agents for agents in solver.broadcast_agents_history))

    def test_uninformed_robot_never_agrees(self):
        live = [i for i in range(len(self.agents)) if i != self.dead]
        solver, _ = self.solve(inform_round={live[0]: None})
        self.assertIn(self.dead, solver.winners_list[live[0]])  # still believes the dead robot
        self.assertNotIn(self.dead, solver.winners_list[live[1]])

    def test_late_inform_delays_the_auction(self):
        live = [i for i in range(len(self.agents)) if i != self.dead]
        solver, _ = self.solve(inform_round={live[0]: 15})
        self.assertGreaterEqual(solver.iterations, 15)
        self.assertNotIn(self.dead, solver.winners_list[live[0]])

    def test_round_cap(self):
        solver, _ = self.solve(max_rounds=2)
        self.assertEqual(solver.termination_reason, "max_rounds")


class RunnerTest(unittest.TestCase):
    def test_helpers(self):
        self.assertEqual(n_groups([(0, 0), (10, 0), (50, 0)], 15), 2)
        self.assertEqual(n_groups([(0, 0), (50, 0)], None), 1)
        config = load_config()
        agents, tasks, _ = build_mission(config, 6, 0)
        self.assertEqual(capacity_bound(config, agents, tasks, set(), 4), 18)

    def test_every_sweep_runs(self):
        for sweep, spec in SWEEPS.items():
            with self.subTest(sweep=sweep):
                result = run_job((sweep, 6, 0, str(CONFIG_PATH)))
                self.assertIsNone(result["error"], result["error"])
                self.assertEqual(len(result["rows"]), len(spec["levels"]) * len(spec["methods"]))
                for row in result["rows"]:
                    self.assertLessEqual(row["assigned"], row["capacity_bound"] + row["duplicates"])
                    if row["success"]:
                        self.assertTrue(row["consistent"])
                # The least stressed level of the communication sweeps is the plain baseline.
                if sweep in ("split", "loss_sparse", "stale_never", "stale_delay"):
                    first = [r for r in result["rows"] if r["level"] == result["rows"][0]["level"]]
                    self.assertTrue(all(r["consistent"] for r in first))


if __name__ == "__main__":
    unittest.main()
