"""Delivery, refresh, and final-assignment checks for the packet-loss study."""

import copy
import json
import unittest
from pathlib import Path

from test.run_packet_loss_experiment import CBBA, assess_assignment, make_scenario, run_trial

ROOT = Path(__file__).resolve().parents[1]


class PacketLossTest(unittest.TestCase):
    def setUp(self):
        self.config = json.loads((ROOT / "config_example_03.json").read_text())

    def test_loss_free_extension_preserves_original_assignments(self):
        for seed in (1, 7, 13):
            world, agents, tasks, graph = make_scenario(seed=seed)
            original = CBBA(self.config)
            expected, _ = original.solve(copy.deepcopy(agents), copy.deepcopy(tasks), world,
                                         3, False, communication_graph=graph)
            rows, solvers = run_trial(seed, 0, self.config, rounds=60)
            for row, solver in zip(rows, solvers):
                with self.subTest(seed=seed, method=row["method"]):
                    self.assertEqual(solver.path_list, expected)
                    self.assertTrue(row["success"])
                    self.assertEqual(solver.iterations, 60)
                    self.assertEqual(solver.termination_reason, "round_budget")
                    self.assertEqual(row["packets_dropped"], 0)
                    self.assertEqual(row["packet_attempts"], row["packets_delivered"])

    def test_total_loss_is_not_mistaken_for_consensus(self):
        rows, solvers = run_trial(7, 1, self.config, rounds=20)
        for row, solver in zip(rows, solvers):
            with self.subTest(method=row["method"]):
                self.assertEqual(row["packets_delivered"], 0)
                self.assertEqual(row["packet_attempts"], row["packets_dropped"])
                self.assertGreater(row["packet_attempts"], 0)
                self.assertGreater(row["duplicate_tasks"], 0)
                self.assertFalse(row["success"])
        # No ACK: a lost update is still marked sent, so plain ED falls silent.
        self.assertEqual(solvers[1].broadcast_history[1], 10)
        self.assertTrue(all(count == 0 for count in solvers[1].broadcast_history[2:]))
        # Forced refresh sends even when no local state changed.
        for round_number in (5, 10, 15, 20):
            self.assertEqual(solvers[2].broadcast_history[round_number-1], 10)

    def test_reproducible_and_policy_independent_random_field(self):
        rows, solvers = run_trial(3, .3, self.config, rounds=30)
        repeated, _ = run_trial(3, .3, self.config, rounds=30)
        self.assertEqual(rows, repeated)
        for solver in solvers:
            self.assertEqual(solver._packet_rng.getstate(), solvers[0]._packet_rng.getstate())
            self.assertEqual(solver.total_packet_attempts,
                             solver.total_packets_delivered + solver.total_packets_dropped)

    def test_lost_messages_cannot_update_beliefs_or_timestamps(self):
        world, agents, tasks, graph = make_scenario(seed=1, num_agents=2, num_tasks=1)
        solver = CBBA(self.config)
        solver.settings(agents, tasks, world, 1, False, True, graph,
                        packet_loss_probability=1)
        solver.winners_list[0][0] = 0
        solver.winner_bid_list[0][0] = 10
        timestamps = solver.communicate([[0, 0], [0, 0]], 1)
        self.assertEqual(solver.winners_list[1], [-1])
        self.assertEqual(solver.winner_bid_list[1], [-1])
        self.assertEqual(timestamps, [[0, 0], [0, 0]])
        self.assertEqual(solver.last_sent_winners[0], [0])
        solver.communicate(timestamps, 2)
        self.assertEqual(solver.broadcast_history, [1, 0])

    def test_receiver_specific_loss_does_not_erase_entire_broadcast(self):
        world, agents, tasks, _ = make_scenario(seed=1, num_agents=3, num_tasks=1)
        graph = [[i != j for j in range(3)] for i in range(3)]
        solver = CBBA(self.config)
        solver.settings(agents, tasks, world, 1, False, True, graph,
                        packet_loss_probability=.5)
        # Row-major draws: sender 0 reaches receiver 1 but misses receiver 2.
        draws = iter([0, .9, .1, 0, 0, 0, 0, 0, 0])
        class FixedDraws:
            def random(self):
                return next(draws)
        solver._packet_rng = FixedDraws()
        solver.winners_list[0][0] = 0
        solver.winner_bid_list[0][0] = 10
        times = solver.communicate([[0]*3 for _ in range(3)], 1)
        self.assertEqual(solver.winners_list, [[0], [0], [-1]])
        self.assertEqual(times[1][0], 1)
        self.assertEqual(times[2][0], 0)
        self.assertEqual(solver.total_broadcasts, 1)
        self.assertEqual(solver.total_packet_attempts, 2)
        self.assertEqual(solver.total_packets_delivered, 1)
        self.assertEqual(solver.total_packets_dropped, 1)

    def test_agreement_alone_cannot_certify_conflicting_paths(self):
        _, solvers = run_trial(7, 0, self.config, rounds=60)
        solver = solvers[0]
        self.assertTrue(assess_assignment(solver)["success"])
        solver.path_list[1].append(solver.path_list[0][0])
        result = assess_assignment(solver)
        self.assertTrue(result["winners_agree"])
        self.assertGreater(result["duplicate_tasks"], 0)
        self.assertFalse(result["success"])


if __name__ == "__main__":
    unittest.main()
