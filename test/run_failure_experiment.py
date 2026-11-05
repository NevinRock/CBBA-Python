#!/usr/bin/env python3
"""Run a seeded failure experiment and save an agent/task timeline."""

import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import Patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))

from FailureSimulation import FailureSimulation, make_failure_scenario


def plot_timeline(simulation, output):
    fig, ax = plt.subplots(figsize=(14, 6))
    colors = {0: "#2b76a8", 1: "#e49b35"}
    y_position = {agent_id: index for index, agent_id in enumerate(sorted(simulation.agents))}

    for segment in simulation.segments:
        if segment.end is None or segment.end <= segment.start:
            continue
        y = y_position[segment.agent_id]
        color = colors[simulation.tasks[segment.task_id].task_type]
        ax.barh(y, segment.end - segment.start, left=segment.start,
                height=0.65, color=color, edgecolor="white", linewidth=1, zorder=2)
        if segment.end - segment.start >= 3:
            ax.text((segment.start + segment.end) / 2, y,
                    f"T{segment.task_id}", ha="center", va="center",
                    color="white", fontsize=8, weight="bold", zorder=3)
        if segment.outcome == "failed":
            ax.scatter(segment.end, y, marker="x", s=150, color="#bb1e2d",
                       linewidths=3, zorder=5)

    for tick, reason, _ in simulation.auctions:
        if tick:
            ax.axvline(tick, color="#6b7280", linestyle="--", alpha=0.45, zorder=1)

    for failed in (s for s in simulation.segments if s.outcome == "failed"):
        replacement = next((s for s in simulation.segments
                            if s.task_id == failed.task_id and
                            s.agent_id != failed.agent_id and s.start >= failed.end), None)
        if replacement is not None:
            ax.annotate("", xy=(replacement.start, y_position[replacement.agent_id]),
                        xytext=(failed.end, y_position[failed.agent_id]),
                        arrowprops={"arrowstyle": "->", "color": "#bb1e2d",
                                    "linestyle": ":", "linewidth": 1.5}, zorder=4)

    ax.set_yticks(list(y_position.values()),
                  [f"{simulation.config['AGENT_TYPES'][simulation.agents[i].agent_type]} {i}"
                   for i in y_position])
    ax.invert_yaxis()
    ax.set_xlabel("Simulation time (ticks)")
    ax.set_ylabel("Agent")
    ax.set_title("Failure-triggered CBBA re-auction: task execution timeline")
    ax.grid(axis="x", alpha=0.2)
    ax.set_axisbelow(True)
    ax.set_xlim(0, max((segment.end or 0) for segment in simulation.segments) + 2)
    ax.legend(handles=[Patch(facecolor=colors[0], label="Track task"),
                       Patch(facecolor=colors[1], label="Rescue task"),
                       Line2D([], [], marker="x", color="#bb1e2d", linestyle="None",
                              markersize=10, markeredgewidth=2.5, label="Robot failed"),
                       Line2D([], [], color="#6b7280", linestyle="--", label="Re-auction")],
              loc="upper right")
    fig.tight_layout()
    fig.savefig(output, dpi=180)
    plt.close(fig)


def plot_trigger_timeline(simulation, output):
    """Show which agent caused each E1/E2 trigger and when auction restarted."""
    fig, ax = plt.subplots(figsize=(12, 5.5))
    agent_ids = sorted(simulation.agents)
    y_position = {agent_id: index for index, agent_id in enumerate(agent_ids)}
    auction_y = len(agent_ids)
    trigger_labels = {
        "neighbour disappeared": "E1 leave",
        "neighbour joined": "E1 join",
        "silence timeout": "E2 timeout",
    }
    orange = "#e77923"

    for tick, event, agent_id in simulation.events:
        if event not in trigger_labels:
            continue
        y = y_position[agent_id]
        ax.scatter(tick, y, marker="x", s=170, color=orange,
                   linewidths=3, zorder=3)
        ax.annotate(trigger_labels[event], (tick, y), xytext=(7, -5),
                    textcoords="offset points", color="#95430d", fontsize=8)

    for tick, reason, _ in simulation.auctions:
        if tick == 0:
            continue
        ax.scatter(tick, auction_y, marker="x", s=210, color=orange,
                   linewidths=3.5, zorder=3)
        ax.annotate("re-auction", (tick, auction_y), xytext=(7, -5),
                    textcoords="offset points", color="#95430d", fontsize=8)
        ax.axvline(tick, color="#9ca3af", linestyle="--", alpha=0.45, zorder=1)

    tick_end = max(tick for tick, _, _ in simulation.auctions) + 7
    ax.set_xlim(0, tick_end)
    ax.set_ylim(-0.7, auction_y + 0.7)
    ax.set_yticks(range(auction_y + 1),
                  [f"{simulation.config['AGENT_TYPES'][simulation.agents[i].agent_type]} {i}"
                   for i in agent_ids] + ["Re-auction"])
    ax.invert_yaxis()
    ax.set_xlabel("Simulation time (ticks)")
    ax.set_ylabel("Agent / action")
    ax.set_title("Neighbour and silence triggers over time")
    ax.grid(axis="both", alpha=0.18)
    ax.set_axisbelow(True)
    fig.tight_layout()
    fig.savefig(output, dpi=180)
    plt.close(fig)


def plot_ed_trigger_frequency(simulation, output):
    """Plot ED-CBBA broadcast events across all re-auction episodes."""
    fig, (ax, count_ax) = plt.subplots(
        2, 1, figsize=(13, 6), sharex=True,
        gridspec_kw={"height_ratios": [2, 1]}, constrained_layout=True)
    orange = "#f07a1f"
    times, heights, counts, baseline = [], [], [], []
    boundaries = []
    logical_round = 0
    for tick, reason, active_count, history in simulation.auction_trigger_histories:
        boundaries.append((logical_round + 1, tick, reason))
        for senders in history:
            logical_round += 1
            counts.append(len(senders))
            baseline.append(active_count)
            for agent_id in senders:
                times.append(logical_round)
                heights.append(1 + 0.006 *
                               (agent_id - (len(simulation.agents) - 1) / 2))

    ax.axhline(1, color="#f8c9a6", linewidth=1.5)
    ax.scatter(times, heights, marker="x", s=43, color=orange,
               linewidths=1.3, alpha=0.85)
    ax.set_ylim(0.93, 1.07)
    ax.set_yticks([1], ["Trigger"])
    ax.set_ylabel("Event condition")
    ax.set_title("ED-CBBA broadcast triggers across failure and recovery")
    ax.grid(axis="x", alpha=0.25)

    rounds = list(range(1, logical_round + 1))
    count_ax.bar(rounds, counts, color=orange, width=0.8, label="ED-CBBA")
    count_ax.step(rounds, baseline, where="mid", color="#64748b",
                  linestyle="--", label="All-agent broadcast")
    count_ax.set_ylim(0, max(baseline) + 1)
    count_ax.set_ylabel("Broadcasts / round")
    count_ax.set_xlabel("Logical time (consensus rounds across auctions)")
    count_ax.legend(loc="upper right")
    count_ax.grid(axis="y", alpha=0.2)

    for first_round, tick, reason in boundaries:
        if first_round > 1:
            for axis in (ax, count_ax):
                axis.axvline(first_round - 0.5, color="#9ca3af",
                             linestyle="--", linewidth=1.2)
        ax.text(first_round, 1.059, f"{reason}, t={tick}",
                fontsize=8, color="#465266", va="top")
    count_ax.set_xlim(0.5, logical_round + 0.5)
    fig.savefig(output, dpi=180)
    plt.close(fig)


def main():
    with (ROOT / "config_example_03.json").open() as file:
        config = json.load(file)
    world, agents, tasks = make_failure_scenario(seed=7)
    simulation = FailureSimulation(agents, tasks, config, world, seed=7).run(horizon=100)
    output = ROOT / "doc" / "failure_reauction_timeline.png"
    plot_timeline(simulation, output)
    print("Saved:", output)
    trigger_output = ROOT / "doc" / "failure_trigger_timeline.png"
    plot_trigger_timeline(simulation, trigger_output)
    print("Saved:", trigger_output)
    ed_output = ROOT / "doc" / "failure_ed_cbba_trigger_frequency.png"
    plot_ed_trigger_frequency(simulation, ed_output)
    print("Saved:", ed_output)
    print("Failures:", sorted(simulation.failed))
    print("Tasks completed:", len(simulation.done), "/", len(tasks))
    print("Heartbeats:", simulation.heartbeats)
    print("Auctions (time, reason, ED-CBBA broadcasts):", simulation.auctions)
    print("Events:", simulation.events)


if __name__ == "__main__":
    main()
