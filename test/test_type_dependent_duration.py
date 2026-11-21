"""Check robot-type-dependent task duration in CBBA scheduling."""

import json
import unittest
from pathlib import Path

from Agent import Agent
from CBBA import CBBA
from Task import Task
from WorldInfo import WorldInfo


ROOT = Path(__file__).resolve().parents[1]
AIR, GROUND = 0, 1
SHARED = 2


def load_config():
    with (ROOT / "config_exp3_shared.json").open() as file:
        return json.load(file)


def shared_task(task_id, end_time=240.0):
    """A shared task at the origin: ground robots take 5 s, air robots 10 s."""
    return Task(task_id=task_id, task_type=SHARED, task_value=100, start_time=0,
                end_time=end_time, duration=8, discount=0.02,
                duration_by_agent_type={AIR: 10.0, GROUND: 5.0})


class DurationForTest(unittest.TestCase):
    def test_falls_back_to_default_duration(self):
        task = Task(duration=8)
        self.assertEqual(task.duration_for(AIR), 8)
        self.assertEqual(task.duration_for(GROUND), 8)

    def test_uses_agent_type_override(self):
        task = shared_task(0)
        self.assertEqual(task.duration_for(AIR), 10.0)
        self.assertEqual(task.duration_for(GROUND), 5.0)

    def test_copy_via_dict_keeps_override(self):
        # CBBA copies tasks with Task(**task.__dict__); the override must survive.
        copy = Task(**shared_task(0).__dict__)
        self.assertEqual(copy.duration_for(GROUND), 5.0)


class ScheduleTest(unittest.TestCase):
    def solve_single_robot(self, agent_type, tasks):
        world = WorldInfo([0, 100], [0, 100], [0, 0])
        agent = Agent(agent_id=0, agent_type=agent_type, nom_velocity=5)
        paths, times = CBBA(load_config()).solve(
            [agent], tasks, world, max_depth=4, time_window_flag=True)
        return paths[0], times[0]

    def test_second_task_starts_after_robot_specific_duration(self):
        for agent_type, duration in ((GROUND, 5.0), (AIR, 10.0)):
            with self.subTest(agent_type=agent_type):
                path, times = self.solve_single_robot(agent_type, [shared_task(0), shared_task(1)])
                self.assertEqual(len(path), 2)
                self.assertAlmostEqual(sorted(times)[1], duration)

    def test_duration_decides_feasibility(self):
        # Second task must start by t = 7: feasible after 5 s (ground), not after 10 s (air).
        tasks = [shared_task(0), shared_task(1, end_time=7.0)]
        ground_path, _ = self.solve_single_robot(GROUND, [Task(**t.__dict__) for t in tasks])
        air_path, _ = self.solve_single_robot(AIR, [Task(**t.__dict__) for t in tasks])
        self.assertEqual(len(ground_path), 2)
        self.assertEqual(len(air_path), 1)

    def test_air_cannot_bid_on_ground_only_task(self):
        ground_only = Task(task_id=0, task_type=1, task_value=100, start_time=0,
                           end_time=240, duration=8, discount=0.02)
        path, _ = self.solve_single_robot(AIR, [ground_only])
        self.assertEqual(path, [])


if __name__ == "__main__":
    unittest.main()
