#!/usr/bin/env python3
from dataclasses import dataclass


@dataclass
class Task:
    task_id: int = 0
    task_type: int = 0
    task_value: float = 0  # task reward
    start_time: float = 0  # task start time (sec)
    end_time: float = 0  # task expiry time (sec)
    duration: float = 0  # task default duration (sec)
    discount: float = 0.1  # task exponential discount (lambda)
    x: float = 0  # task position (meters)
    y: float = 0  # task position (meters)
    z: float = 0  # task position (meters)
    # Optional {agent_type index: duration (sec)}. Agent types not listed use `duration`.
    duration_by_agent_type: dict = None

    def duration_for(self, agent_type: int) -> float:
        """Return how long an agent of `agent_type` takes to execute this task."""
        if self.duration_by_agent_type and agent_type in self.duration_by_agent_type:
            return self.duration_by_agent_type[agent_type]
        return self.duration
