"""Regression checks for event-driven consensus on connected graphs."""

import copy
import json
import unittest
from pathlib import Path

from test.run_ed_cbba_example import CBBA, make_scenario


ROOT = Path(__file__).resolve().parents[1]


class EventDrivenCBBATest(unittest.TestCase):
    def test_matches_baseline_with_fewer_broadcasts(self):
        with (ROOT / "config_example_03.json").open() as file:
            config = json.load(file)

        for seed in (1, 7, 13):
            world, agents, tasks, sparse_graph = make_scenario(seed=seed)
            for graph in (None, sparse_graph):
                with self.subTest(seed=seed, sparse=graph is not None):
                    results = []
                    for triggered in (False, True):
                        solver = CBBA(config)
                        paths, _ = solver.solve(
                            copy.deepcopy(agents), copy.deepcopy(tasks), world,
                            max_depth=3, time_window_flag=False,
                            event_triggered=triggered, communication_graph=graph)
                        results.append((paths, solver))

                    baseline_paths, baseline = results[0]
                    event_paths, event = results[1]
                    self.assertEqual(event_paths, baseline_paths)
                    assigned = [task for path in event_paths for task in path]
                    self.assertEqual(len(assigned), len(set(assigned)))
                    self.assertLess(event.total_broadcasts, baseline.total_broadcasts)
                    self.assertEqual(event.broadcast_history[0], 0)
                    self.assertEqual(baseline.broadcast_history,
                                     [len(agents)] * baseline.iterations)
                    self.assertEqual(sum(event.broadcast_history), event.total_broadcasts)
                    self.assertEqual([len(senders) for senders in event.broadcast_agents_history],
                                     event.broadcast_history)


if __name__ == "__main__":
    unittest.main()
