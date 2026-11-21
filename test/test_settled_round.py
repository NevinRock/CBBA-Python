"""Check the solver's count of rounds and broadcasts until the allocation settles."""

import json
import unittest
from pathlib import Path

from test.run_ed_cbba_example import CBBA, make_scenario


ROOT = Path(__file__).resolve().parents[1]


def solve(event_triggered, round_budget=None):
    with (ROOT / "config_example_01.json").open() as file:
        config = json.load(file)
    world, agents, tasks, _ = make_scenario(seed=3, num_agents=6, num_tasks=12)
    solver = CBBA(config)
    paths, _ = solver.solve(agents, tasks, world, max_depth=3,
                            time_window_flag=False,
                            event_triggered=event_triggered,
                            round_budget=round_budget)
    return solver, paths


class SettledRoundTest(unittest.TestCase):
    def test_settled_round_is_before_the_idle_tail(self):
        for event_triggered in (False, True):
            with self.subTest(event_triggered=event_triggered):
                solver, _ = solve(event_triggered)
                self.assertGreater(solver.settled_round, 0)
                # The quiet stopping rule adds idle rounds after settling.
                self.assertLess(solver.settled_round, solver.iterations)

    def test_stopping_at_the_settled_round_gives_the_same_allocation(self):
        for event_triggered in (False, True):
            with self.subTest(event_triggered=event_triggered):
                full, full_paths = solve(event_triggered)
                _, cut_paths = solve(event_triggered,
                                     round_budget=full.settled_round)
                self.assertEqual(cut_paths, full_paths)

    def test_standard_cbba_counts_every_robot_in_every_settled_round(self):
        solver, _ = solve(event_triggered=False)
        self.assertEqual(solver.broadcasts_until_settled,
                         solver.num_agents * solver.settled_round)

    def test_event_triggered_cbba_sends_nothing_after_settling(self):
        solver, _ = solve(event_triggered=True)
        self.assertEqual(solver.broadcasts_until_settled,
                         solver.total_broadcasts)

    def test_a_run_cut_off_while_changing_is_not_settled(self):
        cut, _ = solve(event_triggered=True, round_budget=1)
        self.assertFalse(cut.allocation_settled)
        full, _ = solve(event_triggered=True)
        self.assertTrue(full.allocation_settled)


if __name__ == "__main__":
    unittest.main()
