#!/usr/bin/env python3
"""Compare ordinary CBBA and event-driven CBBA on the same seeded scenario."""

import copy
import json
import math
import random
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))

from Agent import Agent
from CBBA import CBBA
from Task import Task
from WorldInfo import WorldInfo


def make_scenario(seed=7, num_agents=10, num_tasks=20, radio_range=10.0):
    """Place agents in a connected chain and tasks in a 100 m square."""
    rng = random.Random(seed)
    world = WorldInfo([0, 100], [0, 100], [0, 0])
    agents = []
    x, y = 50.0, 50.0
    for i in range(num_agents):
        if i:
            while True:
                angle = rng.uniform(0, 2 * math.pi)
                next_x = x + 0.7 * radio_range * math.cos(angle)
                next_y = y + 0.7 * radio_range * math.sin(angle)
                if 0 <= next_x <= 100 and 0 <= next_y <= 100:
                    x, y = next_x, next_y
                    break
        agents.append(Agent(agent_id=i, agent_type=0, x=x, y=y,
                            z=0.0, nom_velocity=2.0))
    tasks = [Task(task_id=j, task_type=0, task_value=100.0,
                  x=rng.uniform(0, 100), y=rng.uniform(0, 100), z=0.0)
             for j in range(num_tasks)]
    graph = [[i != j and math.dist((a.x, a.y), (b.x, b.y)) <= radio_range
              for j, b in enumerate(agents)] for i, a in enumerate(agents)]
    return world, agents, tasks, graph


def plot_trigger_distribution(solver, output):
    """Plot actual ED-CBBA broadcast triggers in logical consensus time."""
    fig, (ax, count_ax) = plt.subplots(
        2, 1, figsize=(12, 6), sharex=True,
        gridspec_kw={"height_ratios": [2.2, 1]}, constrained_layout=True)
    orange = "#f07a1f"
    rounds = list(range(1, solver.iterations + 1))
    trigger_times = []
    trigger_y = []
    for round_number, senders in enumerate(solver.broadcast_agents_history, start=1):
        for agent_id in senders:
            trigger_times.append(round_number)
            # Small vertical offsets reveal simultaneous broadcasts while
            # keeping every cross on the trigger=1 row.
            trigger_y.append(1 + 0.006 * (agent_id - (solver.num_agents - 1) / 2))

    ax.axhline(1, color="#f8c9a6", linewidth=1.5)
    ax.scatter(trigger_times, trigger_y, marker="x", s=48, linewidths=1.4,
               color=orange, alpha=0.85, label="Agent broadcast")
    ax.set_ylim(0.93, 1.07)
    ax.set_yticks([1], ["Trigger"])
    ax.set_ylabel("Event condition")
    ax.set_title("ED-CBBA event-trigger distribution")
    ax.grid(axis="x", linestyle="--", alpha=0.3)

    inset = ax.inset_axes([0.54, 0.53, 0.42, 0.36])
    inset.axhline(1, color="#f8c9a6", linewidth=1)
    inset.scatter(trigger_times, trigger_y, marker="x", s=25,
                  linewidths=1, color=orange, alpha=0.85)
    inset.set_xlim(5.5, 8.5)
    inset.set_ylim(0.96, 1.04)
    inset.set_xticks([6, 7, 8])
    inset.set_yticks([1])
    inset.tick_params(labelsize=8)
    ax.indicate_inset_zoom(inset, edgecolor="#777777")

    count_ax.bar(rounds, solver.broadcast_history, color=orange, alpha=0.85,
                 width=0.75, label="ED-CBBA")
    count_ax.axhline(solver.num_agents, color="#64748b", linestyle="--",
                     linewidth=1.5, label="CBBA (all agents)")
    count_ax.set_ylim(0, solver.num_agents + 1)
    count_ax.set_ylabel("Broadcasts / round")
    count_ax.set_xlabel("Logical time (consensus round)")
    count_ax.set_xticks(rounds)
    count_ax.grid(axis="y", alpha=0.2)
    count_ax.legend(loc="upper right")
    fig.savefig(output, dpi=180)
    plt.close(fig)


def main():
    with (ROOT / "config_example_03.json").open() as file:
        config = json.load(file)
    world, agents, tasks, graph = make_scenario()
    results = []
    for triggered in (False, True):
        solver = CBBA(config)
        paths, _ = solver.solve(copy.deepcopy(agents), copy.deepcopy(tasks), world,
                                max_depth=3, time_window_flag=False,
                                event_triggered=triggered, communication_graph=graph)
        results.append((solver, paths))

    baseline, baseline_paths = results[0]
    event_driven, event_paths = results[1]
    print("Same assignment:", baseline_paths == event_paths)
    print("CBBA broadcasts:", baseline.total_broadcasts)
    print("ED-CBBA broadcasts:", event_driven.total_broadcasts)
    print("Reduction: {:.1f}%".format(
        100 * (1 - event_driven.total_broadcasts / baseline.total_broadcasts)))
    print("CBBA iterations:", baseline.iterations)
    print("ED-CBBA iterations:", event_driven.iterations)
    print("Broadcasts per ED-CBBA iteration:", event_driven.broadcast_history)
    print("Task paths:", event_paths)
    output = ROOT / "doc" / "ed_cbba_trigger_distribution.png"
    plot_trigger_distribution(event_driven, output)
    print("Saved trigger distribution:", output)


if __name__ == "__main__":
    main()
