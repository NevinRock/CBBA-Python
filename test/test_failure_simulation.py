"""Check the failure experiment's task accounting and survivor rule."""

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))

from Agent import Agent
from CBBA import CBBA
from FailureSimulation import FailureSimulation, make_failure_scenario
from Task import Task


class FailureSimulationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with (ROOT / "config_example_03.json").open() as file:
            cls.config = json.load(file)
        cls.world, cls.agents, cls.tasks = make_failure_scenario(seed=7)

    def test_failed_tasks_resume_without_duplicate_work(self):
        sim = FailureSimulation(self.agents, self.tasks, self.config,
                                self.world, seed=7).run(horizon=100)
        self.assertEqual(len(sim.done), len(self.tasks))
        failed_segments = [s for s in sim.segments if s.outcome == "failed"]
        self.assertTrue(failed_segments)
        for segment in failed_segments:
            self.assertTrue(any(s.task_id == segment.task_id and
                                s.agent_id != segment.agent_id and
                                s.start >= segment.end for s in sim.segments))
        for task in self.tasks:
            segments = [s for s in sim.segments if s.task_id == task.task_id]
            self.assertEqual(sum(s.end - s.start for s in segments), task.duration)
            for segment in segments:
                agent = sim.agents[segment.agent_id]
                self.assertEqual(agent.agent_type, task.task_type)
        self.assertTrue(any(event[1] == "neighbour joined" for event in sim.events))
        self.assertTrue(any(event[1] == "silence timeout" for event in sim.events))
        for auction, episode in zip(sim.auctions, sim.auction_trigger_histories):
            self.assertEqual(sum(len(senders) for senders in episode[3]), auction[2])

    def test_at_least_one_agent_of_each_type_survives(self):
        sim = FailureSimulation(self.agents, self.tasks, self.config,
                                self.world, seed=7, failure_probability=1.0,
                                link_loss_probability=0.0).run(horizon=7)
        survivors = [agent for agent in self.agents if agent.agent_id not in sim.failed]
        self.assertEqual({agent.agent_type for agent in survivors}, {0, 1})

    def test_incumbent_bonus_favours_current_owner(self):
        agents = [Agent(agent_id=i, agent_type=0, nom_velocity=2.0)
                  for i in range(2)]
        task = Task(task_id=8, task_type=0, task_value=100.0)
        paths, _ = CBBA(self.config).solve(
            agents, [task], self.world, max_depth=1, time_window_flag=False,
            incumbent_owners={8: 1}, incumbency_bonus=0.10)
        self.assertEqual(paths, [[], [8]])


if __name__ == "__main__":
    unittest.main()
