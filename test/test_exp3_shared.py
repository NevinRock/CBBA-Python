"""Smoke and invariant tests for the Experiment 3 (shared capabilities) runner."""

import math
import unittest

from test.run_exp3_shared import (CONDITIONS, CONFIG_PATH, METHODS, adjacency, advance,
                                  build_mission, choose_failures, connect_threshold,
                                  graph_stats, load_config, run_job, type_counts)


class MissionTest(unittest.TestCase):
    def setUp(self):
        self.config = load_config()

    def test_counts_and_types_per_team_size(self):
        for condition, expected_ground in (("baseline", {6: 3, 12: 6, 24: 12}),
                                           ("imbalanced", {6: 2, 12: 3, 24: 6})):
            for size in (6, 12, 24):
                with self.subTest(condition=condition, size=size):
                    agents, tasks, _ = build_mission(self.config, size, 0, condition)
                    self.assertEqual(len(agents), size)
                    self.assertEqual(sum(a.agent_type == 1 for a in agents), expected_ground[size])
                    self.assertEqual(len(tasks), 3 * size)
                    for task_type in range(3):
                        self.assertEqual(sum(t.task_type == task_type for t in tasks), size)
                    self.assertTrue(all(a.nom_velocity == 5 for a in agents))
                    self.assertTrue(all(0 <= p <= 100 for o in agents + tasks for p in (o.x, o.y)))
                    self.assertTrue(all((t.start_time, t.end_time, t.task_value) == (0, 240, 100)
                                        for t in tasks))
                    self.assertEqual([a.agent_id for a in agents], list(range(size)))
                    self.assertEqual([t.task_id for t in tasks], list(range(3 * size)))

    def test_ids_are_shuffled_across_types(self):
        # CBBA breaks ties by lower ID; IDs must not be grouped by robot type.
        agents, tasks, _ = build_mission(self.config, 24, 0)
        first_half_types = {a.agent_type for a in agents[:12]}
        self.assertEqual(first_half_types, {0, 1})
        self.assertEqual({t.task_type for t in tasks[:24]}, {0, 1, 2})

    def test_durations(self):
        _, tasks, _ = build_mission(self.config, 6, 0)
        for task in tasks:
            expected = (10, 5) if task.task_type == 2 else (8, 8)
            self.assertEqual((task.duration_for(0), task.duration_for(1)), expected)

    def test_same_seed_gives_identical_mission(self):
        positions = lambda m: [(o.x, o.y, o.agent_type if hasattr(o, "agent_type") else o.task_type)  # noqa: E731
                               for o in m[0] + m[1]]
        first = build_mission(self.config, 12, 3)
        self.assertEqual(positions(first), positions(build_mission(self.config, 12, 3)))
        self.assertNotEqual(positions(first), positions(build_mission(self.config, 12, 4)))
        # Conditions that change only comms or failure timing reuse the baseline mission.
        for condition in ("mid_mission", "range_limited", "double_failure", "cascading"):
            self.assertEqual(positions(first), positions(build_mission(self.config, 12, 3, condition)))

    def test_clustered_tasks_are_concentrated(self):
        def spread(condition):
            _, tasks, _ = build_mission(self.config, 24, 0, condition)
            near = [min(math.dist((t.x, t.y), (u.x, u.y)) for u in tasks if u is not t) for t in tasks]
            return sum(near) / len(near)
        self.assertLess(spread("clustered"), spread("baseline"))


class GraphTest(unittest.TestCase):
    def test_threshold_connects_and_line_graph_stats(self):
        points = [(0, 0), (10, 0), (20, 0), (30, 0)]
        self.assertAlmostEqual(connect_threshold(points), 10)
        ok, diameter, lam2 = graph_stats(adjacency(points, 10))
        self.assertTrue(ok)
        self.assertEqual(diameter, 3)
        self.assertGreater(lam2, 0)
        self.assertFalse(graph_stats(adjacency(points, 9))[0])


class AdvanceTest(unittest.TestCase):
    def test_states_at_failure_time(self):
        config = load_config()
        agents, tasks, _ = build_mission(config, 6, 0)
        robot = agents[0]
        a, b = tasks[0], tasks[1]
        a.x, a.y, b.x, b.y = robot.x + 10, robot.y, robot.x + 10, robot.y + 20
        da, db = a.duration_for(robot.agent_type), b.duration_for(robot.agent_type)
        paths, times = {robot.agent_id: [a.task_id, b.task_id]}, {robot.agent_id: [2.0, 2.0 + da + 4.0]}
        # t = 1: travelling, halfway along the first leg
        states, done, running, rest, _ = advance([robot], tasks, paths, times, 1.0)
        self.assertAlmostEqual(states[0].x, robot.x + 5)
        self.assertEqual((done, running, rest[robot.agent_id]), ({}, {}, [a.task_id, b.task_id]))
        # t = 3: executing task a
        states, done, running, rest, _ = advance([robot], tasks, paths, times, 3.0)
        self.assertIn(a.task_id, running)
        self.assertEqual(states[0].availability, 2.0 + da)
        self.assertEqual(rest[robot.agent_id], [b.task_id])
        # after both tasks: done, robot at b
        states, done, running, rest, _ = advance([robot], tasks, paths, times, 100.0)
        self.assertEqual(set(done), {a.task_id, b.task_id})
        self.assertEqual((states[0].x, states[0].y), (b.x, b.y))
        self.assertEqual(db, b.duration_for(robot.agent_type))


class FailureChoiceTest(unittest.TestCase):
    def test_targeted_failure_holds_most_shared_tasks(self):
        config = load_config()
        agents, tasks, _ = build_mission(config, 12, 1)
        shared = [t.task_id for t in tasks if t.task_type == 2]
        others = [t.task_id for t in tasks if t.task_type != 2]
        owner = {others[0]: 0, others[1]: 0, shared[0]: 1}
        owner.update({task_id: 5 for task_id in shared[1:4]})
        self.assertEqual(choose_failures(config, agents, tasks, owner, 12, 1, "targeted_shared"), [[5]])

    def test_failure_shapes(self):
        config = load_config()
        agents, tasks, _ = build_mission(config, 12, 1)
        owner = {t.task_id: t.task_id % 12 for t in tasks}
        self.assertEqual(len(choose_failures(config, agents, tasks, owner, 12, 1, "random_pair")[0]), 2)
        pair = choose_failures(config, agents, tasks, owner, 12, 1, "ground_pair")[0]
        self.assertTrue(all(agents[a].agent_type == 1 for a in pair))
        cascade = choose_failures(config, agents, tasks, owner, 12, 1, "cascade")
        self.assertEqual([len(e) for e in cascade], [1, 1])
        self.assertNotEqual(cascade[0], cascade[1])


class TrialTest(unittest.TestCase):
    def test_every_condition_runs_with_invariants(self):
        config = load_config()
        for condition, settings in CONDITIONS.items():
            with self.subTest(condition=condition):
                result = run_job((condition, 12, 0, METHODS, str(CONFIG_PATH)))
                self.assertIsNone(result["error"], result["error"])
                rows = result["trials"]
                self.assertEqual(len(rows), len(settings["failure_modes"]) * len(METHODS))
                for row in rows:
                    self.assertLessEqual(row["assigned_tasks"], row["n_tasks"])
                    self.assertLessEqual(row["broadcasts_to_converge"], row["broadcasts"])
                    self.assertLessEqual(row["rounds_to_converge"], row["rounds"])
                    self.assertEqual(row["shared_won_air"] + row["shared_won_ground"]
                                     + row["shared_unassigned"], row["shared_total"])
                    if row["scope"] == "local":
                        self.assertEqual(row["method"], "scoped_ed")
                        self.assertLessEqual(row["affected_tasks"],
                                             config["EXPERIMENT"]["MAX_LOCAL_AFFECTED"])
                    if row["method"] != "scoped_ed":
                        self.assertEqual(row["scope"], "global")
                    if settings["comms"] == "range":
                        self.assertNotEqual(row["comm_range_m"], "")
                        self.assertNotEqual(row["graph_diameter"], "")
                    if settings["failure_time"] == "mid":
                        self.assertGreater(row["fail_time_s"], 0)
                # Paired: within a failure mode all methods share failed robots and time.
                for mode in settings["failure_modes"]:
                    same = {(r["failed_agents"], r["fail_time_s"]) for r in rows if r["failure_mode"] == mode}
                    self.assertEqual(len(same), 1)
                self.assertEqual(len(result["winners"]), len(rows) * 12)

    def test_type_counts(self):
        self.assertEqual(type_counts(6, 0.25), (4, 2))
        self.assertEqual(type_counts(24, 0.5), (12, 12))


if __name__ == "__main__":
    unittest.main()
