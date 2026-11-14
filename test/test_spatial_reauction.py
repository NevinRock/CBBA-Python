"""Check spatial eligibility and failure-auction capacity enforcement."""

import json
import unittest
from pathlib import Path

from test.run_spatial_reauction_experiment import run_trial
from CBBA import CBBA
from Agent import Agent
from Task import Task
from WorldInfo import WorldInfo


ROOT = Path(__file__).resolve().parents[1]


class SpatialReauctionTest(unittest.TestCase):
    def test_agent_task_eligibility_overrides_a_better_bid(self):
        with (ROOT / "config_example_01.json").open() as file:
            config = json.load(file)
        agents = [Agent(agent_id=0, agent_type=0, nom_velocity=2, x=0),
                  Agent(agent_id=1, agent_type=0, nom_velocity=2, x=10)]
        tasks = [Task(task_id=0, task_type=0, task_value=100,
                      start_time=0, end_time=100, duration=5, x=0)]
        world = WorldInfo([0, 10], [0, 10], [0, 0])
        solver = CBBA(config)
        paths, _ = solver.solve(agents, tasks, world, max_depth=1,
                                time_window_flag=True,
                                agent_task_eligibility=[[False], [True]])
        self.assertEqual(paths, [[], [0]])

    def test_radius_trial_reassigns_every_task_with_capacity(self):
        for radius in (20, 40, 60, None):
            with self.subTest(radius=radius):
                result = run_trial(seed=7, radius=radius)
                self.assertEqual(result["assigned_tasks"], 24)
                self.assertGreater(result["broadcasts"], 0)
                self.assertLessEqual(result["participants"], 11)
                if result["scope"] == "local":
                    self.assertLess(result["participants"], 11)


if __name__ == "__main__":
    unittest.main()
