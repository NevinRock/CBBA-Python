"""Check that the multi-type demonstration remains a valid robot schedule."""

import math
import unittest

from run_multitype_scenario import build_scenario
from CBBA import CBBA


class MultiTypeScenarioTest(unittest.TestCase):
    def test_assignment_respects_capability_time_and_travel(self):
        config, agents, tasks, world = build_scenario()
        solver = CBBA(config)
        paths, times = solver.solve(agents, tasks, world, max_depth=4,
                                    time_window_flag=True, event_triggered=True)
        task_by_id = {task.task_id: task for task in tasks}
        self.assertEqual(set(task_by_id), {task_id for path in paths for task_id in path})
        self.assertEqual(len(tasks), sum(map(len, paths)))

        for agent, path, starts in zip(agents, paths, times):
            previous_end = agent.availability
            previous_position = (agent.x, agent.y, agent.z)
            agent_type = config["AGENT_TYPES"][agent.agent_type]
            for task_id, start in zip(path, starts):
                task = task_by_id[task_id]
                task_type = config["TASK_TYPES"][task.task_type]
                self.assertIn(task_type, config["COMPATIBILITY"][agent_type])
                self.assertGreaterEqual(start, task.start_time)
                self.assertLessEqual(start, task.end_time)
                position = (task.x, task.y, task.z)
                earliest = previous_end + math.dist(previous_position, position) / agent.nom_velocity
                self.assertGreaterEqual(start + 1e-7, earliest)
                previous_end = start + task.duration
                previous_position = position


if __name__ == "__main__":
    unittest.main()
