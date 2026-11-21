"""Check the Experiment 2 (exclusive capabilities) mission and trial protocol."""

import math
import unittest

from test.run_exclusive_capabilities_experiment import METHODS, make_mission, run_trial


class MissionTest(unittest.TestCase):
    def test_mission_matches_the_specification(self):
        # Spec: equal air/ground robots; 9/18/36 tasks of each type.
        for team_size, tasks_per_type in ((6, 9), (12, 18), (24, 36)):
            with self.subTest(team_size=team_size):
                config, agents, tasks, world = make_mission(seed=0, team_size=team_size)
                robot_types = [config["AGENT_TYPES"][a.agent_type] for a in agents]
                task_types = [config["TASK_TYPES"][t.task_type] for t in tasks]
                self.assertEqual(robot_types.count("air"), team_size // 2)
                self.assertEqual(robot_types.count("ground"), team_size // 2)
                self.assertEqual(task_types.count("air_only"), tasks_per_type)
                self.assertEqual(task_types.count("ground_only"), tasks_per_type)
                self.assertEqual(config["COMPATIBILITY"],
                                 {"air": ["air_only"], "ground": ["ground_only"]})
                self.assertEqual((world.limit_x, world.limit_y), ([0, 100], [0, 100]))
                for item in agents + tasks:
                    self.assertTrue(0 <= item.x <= 100 and 0 <= item.y <= 100)
                self.assertTrue(all(a.nom_velocity == 5 for a in agents))
                for task in tasks:
                    self.assertEqual((task.task_value, task.duration), (100, 8))
                    self.assertEqual((task.start_time, task.end_time), (0, 240))
                self.assertEqual(len({t.task_id for t in tasks}), len(tasks))
                self.assertEqual([a.agent_id for a in agents], list(range(team_size)))

    def test_same_seed_gives_the_same_mission(self):
        first = make_mission(seed=4, team_size=12)
        again = make_mission(seed=4, team_size=12)
        other = make_mission(seed=5, team_size=12)
        positions = lambda mission: [(i.x, i.y) for i in mission[1] + mission[2]]
        self.assertEqual(positions(first), positions(again))
        self.assertNotEqual(positions(first), positions(other))


class PairedTrialTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.trials = {(seed, size): run_trial(seed, size, bonus=0.0)
                      for seed in range(6) for size in (6, 12)}

    def test_all_methods_face_the_same_failure(self):
        for rows in self.trials.values():
            self.assertEqual([row["method"] for row in rows], list(METHODS))
            self.assertEqual(len({row["failed_robot"] for row in rows}), 1)
            self.assertEqual(len({row["affected_task_ids"] for row in rows}), 1)
            self.assertGreater(rows[0]["affected_tasks"], 0)

    def test_capacity_five_lets_survivors_take_every_task(self):
        # 6 robots: 2 surviving robots of the failed type x 5 slots >= 9 tasks.
        for (seed, size), rows in self.trials.items():
            for row in rows:
                with self.subTest(seed=seed, size=size, method=row["method"]):
                    self.assertEqual(row["assigned_tasks"], 3 * size)

    def test_local_attempt_uses_only_capable_robots_within_40_m(self):
        local_rows = 0
        for (seed, size), rows in self.trials.items():
            row = rows[METHODS.index("scoped_ed_cbba")]
            if row["scope"] != "local":
                continue
            local_rows += 1
            config, agents, tasks, _ = make_mission(seed, size)
            failed_type = agents[row["failed_robot"]].agent_type
            affected = [tasks[i] for i in row["affected_task_ids"]]
            for robot_id in row["participant_ids"]:
                robot = agents[robot_id]
                self.assertNotEqual(robot_id, row["failed_robot"])
                self.assertEqual(robot.agent_type, failed_type)
                self.assertTrue(any(math.dist((robot.x, robot.y), (t.x, t.y)) <= 40
                                    for t in affected))
        self.assertGreater(local_rows, 0)

    def test_global_methods_never_attempt_a_local_auction(self):
        for rows in self.trials.values():
            for row in rows[:2]:
                self.assertEqual((row["scope"], row["fallback_reason"]), ("global", ""))

    def test_fallback_adds_the_local_attempt_to_the_global_broadcasts(self):
        # The fallback auction is the same deterministic global ED-CBBA run.
        for rows in self.trials.values():
            ed, scoped = rows[METHODS.index("ed_cbba")], rows[METHODS.index("scoped_ed_cbba")]
            if scoped["scope"] != "global":
                continue
            if scoped["fallback_reason"] in ("no_nearby_capable_robot",
                                             "too_many_affected_tasks"):
                self.assertEqual(scoped["broadcasts"], ed["broadcasts"])
            else:
                self.assertGreater(scoped["broadcasts"], ed["broadcasts"])
            self.assertEqual(scoped["assigned_tasks"], ed["assigned_tasks"])


if __name__ == "__main__":
    unittest.main()
