"""Discrete-time failure and re-auction experiment for the existing CBBA solver."""

import copy
import math
import random
from dataclasses import dataclass

from CBBA import CBBA
from Agent import Agent
from Task import Task
from WorldInfo import WorldInfo


@dataclass
class TaskSegment:
    agent_id: int
    task_id: int
    start: int
    end: int = None
    outcome: str = "ongoing"


class FailureSimulation:
    def __init__(self, agents: list, tasks: list, config: dict, world: WorldInfo,
                 seed: int = 7, failure_probability: float = 0.10,
                 link_loss_probability: float = 0.05, heartbeat_interval: int = 2,
                 timeout: int = 6, incumbency_bonus: float = 0.10,
                 failure_tick: int = 6, link_loss_tick: int = 20,
                 link_loss_duration: int = 4, radio_range: float = 10.0):
        if not 0 <= failure_probability <= 1 or not 0 <= link_loss_probability <= 1:
            raise ValueError("probabilities must be in [0, 1]")
        if heartbeat_interval < 1 or timeout <= heartbeat_interval:
            raise ValueError("timeout must exceed the heartbeat interval")
        self.agents = {agent.agent_id: copy.deepcopy(agent) for agent in agents}
        self.tasks = {task.task_id: copy.deepcopy(task) for task in tasks}
        self.config = config
        self.world = world
        self.rng = random.Random(seed)
        self.failure_probability = failure_probability
        self.link_loss_probability = link_loss_probability
        self.heartbeat_interval = heartbeat_interval
        self.timeout = timeout
        self.incumbency_bonus = incumbency_bonus
        self.failure_tick = failure_tick
        self.link_loss_tick = link_loss_tick
        self.link_loss_duration = link_loss_duration
        self.radio_range = radio_range

        self.failed = set()
        self.suspected = set()
        self.offline_until = {}
        self.last_heard = {agent_id: 0 for agent_id in self.agents}
        self.remaining = {task.task_id: float(task.duration) for task in tasks}
        self.done = set()
        self.owner = {}
        self.queues = {agent_id: [] for agent_id in self.agents}
        self.current = {agent_id: None for agent_id in self.agents}
        self.open_segment = {}
        self.segments = []
        self.events = []
        self.auctions = []
        self.auction_trigger_histories = []
        self.heartbeats = 0
        self.last_online = set(self.agents)

    def _online(self, tick):
        return {i for i in self.agents
                if i not in self.failed and tick >= self.offline_until.get(i, 0)}

    def _heard_over_network(self, online):
        """Reachability models a direct or relayed heartbeat in the live network."""
        if not online:
            return set()
        root = min(online)
        heard = {root}
        pending = [root]
        while pending:
            source = pending.pop()
            a = self.agents[source]
            for target in online - heard:
                b = self.agents[target]
                if math.dist((a.x, a.y), (b.x, b.y)) <= self.radio_range:
                    heard.add(target)
                    pending.append(target)
        return heard

    def _close_segment(self, agent_id, tick, outcome):
        segment = self.open_segment.pop(agent_id, None)
        if segment is not None:
            segment.end = tick
            segment.outcome = outcome
        self.current[agent_id] = None

    def _sample_failures(self, tick):
        # Sample only agents currently working, then preserve one per type.
        candidates = [i for i in sorted(self.agents)
                      if i not in self.failed and self.current[i] is not None]
        sampled = {i for i in candidates
                   if self.rng.random() < self.failure_probability}
        for agent_type in self.config["AGENT_TYPES"]:
            type_index = self.config["AGENT_TYPES"].index(agent_type)
            survivors = [i for i, agent in self.agents.items()
                         if agent.agent_type == type_index and i not in self.failed]
            if survivors and set(survivors) <= sampled:
                sampled.remove(self.rng.choice(survivors))
        for agent_id in sorted(sampled):
            self.failed.add(agent_id)
            self._close_segment(agent_id, tick, "failed")
            self.events.append((tick, "failure", agent_id))

    def _sample_link_loss(self, tick):
        for agent_id in sorted(self._online(tick)):
            if self.rng.random() < self.link_loss_probability:
                self.offline_until[agent_id] = tick + self.link_loss_duration
                self._close_segment(agent_id, tick, "paused")
                self.events.append((tick, "link loss", agent_id))

    def _auction(self, tick, reason):
        active_ids = sorted(self._online(tick) - self.suspected)
        pending_tasks = [self.tasks[i] for i in sorted(self.tasks) if i not in self.done]
        if not active_ids or not pending_tasks:
            return

        # The CBBA implementation indexes winner IDs as 0..N-1. Map the
        # surviving robots to local IDs for this auction and map paths back.
        local_id = {agent_id: index for index, agent_id in enumerate(active_ids)}
        local_agents = []
        for agent_id in active_ids:
            agent = copy.deepcopy(self.agents[agent_id])
            agent.agent_id = local_id[agent_id]
            local_agents.append(agent)
        local_tasks = []
        for task in pending_tasks:
            task = copy.deepcopy(task)
            task.duration = self.remaining[task.task_id]
            local_tasks.append(task)
        incumbents = {task_id: local_id[agent_id]
                      for task_id, agent_id in self.owner.items()
                      if agent_id in local_id and task_id not in self.done}
        solver = CBBA(self.config)
        paths, _ = solver.solve(
            local_agents, local_tasks, self.world, max_depth=len(local_tasks),
            time_window_flag=False, event_triggered=True,
            incumbent_owners=incumbents, incumbency_bonus=self.incumbency_bonus)
        new_queues = {agent_id: [] for agent_id in self.agents}
        new_owner = {}
        for local, path in enumerate(paths):
            agent_id = active_ids[local]
            new_queues[agent_id] = path
            for task_id in path:
                new_owner[task_id] = agent_id

        for agent_id, task_id in list(self.current.items()):
            if task_id is not None and new_owner.get(task_id) != agent_id:
                self._close_segment(agent_id, tick, "reassigned")
        self.queues = new_queues
        self.owner = new_owner
        self.auctions.append((tick, reason, solver.total_broadcasts))
        self.auction_trigger_histories.append(
            (tick, reason, len(active_ids),
             [[active_ids[local] for local in senders]
              for senders in solver.broadcast_agents_history]))
        self.events.append((tick, "re-auction", reason))

    def _work(self, tick, online):
        for agent_id in sorted(online - self.suspected):
            task_id = self.current[agent_id]
            if task_id is None:
                task_id = next((task for task in self.queues[agent_id]
                                if task not in self.done and self.owner.get(task) == agent_id), None)
                if task_id is None:
                    continue
                self.current[agent_id] = task_id
                segment = TaskSegment(agent_id, task_id, tick)
                self.open_segment[agent_id] = segment
                self.segments.append(segment)
            self.remaining[task_id] = max(0.0, self.remaining[task_id] - 1.0)
            if self.remaining[task_id] == 0:
                self.done.add(task_id)
                self._close_segment(agent_id, tick + 1, "completed")

    def run(self, horizon: int = 100):
        self._auction(0, "initial")
        for tick in range(horizon):
            if tick == self.failure_tick:
                self._sample_failures(tick)
            if tick == self.link_loss_tick:
                self._sample_link_loss(tick)

            online = self._online(tick)
            joined = online - self.last_online
            disappeared = self.last_online - online
            for agent_id in sorted(disappeared):
                self.events.append((tick, "neighbour disappeared", agent_id))
            for agent_id in sorted(joined):
                self.events.append((tick, "neighbour joined", agent_id))
                self.suspected.discard(agent_id)

            if tick % self.heartbeat_interval == 0:
                heard = self._heard_over_network(online)
                self.heartbeats += len(online)
                for agent_id in heard:
                    self.last_heard[agent_id] = tick
            newly_suspected = set()
            for agent_id in self.agents:
                if agent_id not in self.suspected and tick - self.last_heard[agent_id] >= self.timeout:
                    self.suspected.add(agent_id)
                    newly_suspected.add(agent_id)
                    self._close_segment(agent_id, tick, "paused")
                    self.events.append((tick, "silence timeout", agent_id))

            if joined or newly_suspected:
                reason = "join" if joined else "silence timeout"
                self._auction(tick, reason)
            self._work(tick, online)
            self.last_online = online
            if len(self.done) == len(self.tasks):
                break

        for agent_id in list(self.open_segment):
            self._close_segment(agent_id, horizon, "ongoing")
        return self


def make_failure_scenario(seed=7):
    """Original quad/track and car/rescue capabilities, with both types present."""
    rng = random.Random(seed)
    world = WorldInfo([-2, 2], [-2, 2], [0, 0])
    agents = [Agent(agent_id=i, agent_type=0 if i < 4 else 1,
                    x=rng.uniform(-2, 2), y=rng.uniform(-2, 2),
                    nom_velocity=2.0) for i in range(8)]
    tasks = [Task(task_id=j, task_type=0 if j < 10 else 1,
                  task_value=100.0, duration=rng.randint(10, 17),
                  x=rng.uniform(-2, 2), y=rng.uniform(-2, 2))
             for j in range(20)]
    return world, agents, tasks
