#!/usr/bin/env python3
"""Experiment 2: post-failure re-auction with exclusive air/ground capabilities."""

import argparse
import copy
import csv
import json
import math
import random
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "lib"))

from Agent import Agent
from CBBA import CBBA
from Task import Task
from WorldInfo import WorldInfo


MAP_SIZE = 100.0
SPEED = 5.0
TASK_VALUE = 100
TASK_DURATION = 8
START_WINDOW = (0, 240)
DISCOUNT = 0.02
TASKS_PER_ROBOT_PER_TYPE = 3
# The spec's 4 leaves a 6-robot team 2 x 4 = 8 slots for 9 tasks after a failure.
CAPACITY = 5
LOCAL_RADIUS = 40.0
# The spec permits a local attempt for every affected task a robot can hold.
MAX_LOCAL_AFFECTED = CAPACITY
METHODS = ("cbba", "ed_cbba", "scoped_ed_cbba")


def make_mission(seed, team_size):
    """Place equal air/ground teams and 1.5 tasks per robot uniformly on the map."""
    with (ROOT / "config_exclusive_capabilities.json").open(encoding="utf-8") as file:
        config = json.load(file)
    rng = random.Random(f"{seed}-{team_size}")
    point = lambda: (rng.uniform(0, MAP_SIZE), rng.uniform(0, MAP_SIZE))
    half = team_size // 2
    agents = []
    for type_name in ("air", "ground"):
        for _ in range(half):
            x, y = point()
            agents.append(Agent(agent_id=len(agents),
                                agent_type=config["AGENT_TYPES"].index(type_name),
                                x=x, y=y, nom_velocity=SPEED))
    tasks = []
    for type_name in ("air_only", "ground_only"):
        for _ in range(half * TASKS_PER_ROBOT_PER_TYPE):
            x, y = point()
            tasks.append(Task(task_id=len(tasks),
                              task_type=config["TASK_TYPES"].index(type_name),
                              task_value=TASK_VALUE, start_time=START_WINDOW[0],
                              end_time=START_WINDOW[1], duration=TASK_DURATION,
                              discount=DISCOUNT, x=x, y=y))
    world = WorldInfo([0, MAP_SIZE], [0, MAP_SIZE], [0, 0])
    return config, agents, tasks, world


def auction(config, agents, tasks, world, participant_ids, task_ids, owner,
            bonus, event_triggered, eligible=None):
    """Run one re-auction among some survivors over some tasks.

    eligible(robot, task) may forbid a bid. Returns paths and start times
    keyed by robot ID, plus the solver for its communication counts.
    """
    by_task = {task.task_id: task for task in tasks}
    participants = [copy.deepcopy(agents[robot_id]) for robot_id in participant_ids]
    for local_id, robot in enumerate(participants):
        robot.agent_id = local_id
    local_tasks = [copy.deepcopy(by_task[task_id]) for task_id in sorted(task_ids)]
    local_of = {robot_id: index for index, robot_id in enumerate(participant_ids)}
    incumbents = {task_id: local_of[robot_id] for task_id, robot_id in owner.items()
                  if task_id in task_ids and robot_id in local_of}
    eligibility = None
    if eligible is not None:
        eligibility = [[eligible(agents[robot_id], task) for task in local_tasks]
                       for robot_id in participant_ids]
    solver = CBBA(config)
    paths, starts = solver.solve(participants, local_tasks, world, max_depth=CAPACITY,
                                 time_window_flag=True, event_triggered=event_triggered,
                                 incumbent_owners=incumbents, incumbency_bonus=bonus,
                                 agent_task_eligibility=eligibility)
    return (dict(zip(participant_ids, paths)), dict(zip(participant_ids, starts)), solver)


def initial_allocation(config, agents, tasks, world):
    """The common pre-failure allocation, shared by all methods in a trial."""
    paths, starts, _ = auction(config, agents, tasks, world,
                               [agent.agent_id for agent in agents],
                               {task.task_id for task in tasks}, {}, 0.0, True)
    owner = {task_id: robot_id for robot_id, path in paths.items() for task_id in path}
    if len(owner) != len(tasks):
        raise AssertionError("The initial allocation must assign every task")
    return paths, starts, owner


def capable(config, robot, task):
    robot_type = config["AGENT_TYPES"][robot.agent_type]
    return config["TASK_TYPES"][task.task_type] in config["COMPATIBILITY"][robot_type]


def allocation_score(config, agents, tasks, paths, starts):
    """Check the final schedules and score them by task value, without the bonus."""
    by_task = {task.task_id: task for task in tasks}
    assigned = [task_id for path in paths.values() for task_id in path]
    if len(assigned) != len(set(assigned)):
        raise AssertionError("A task has two owners")
    score = 0.0
    for robot_id, path in paths.items():
        robot = agents[robot_id]
        if len(path) > CAPACITY or len(path) != len(starts[robot_id]):
            raise AssertionError("Schedule exceeds capacity or lacks start times")
        free_at, position = robot.availability, (robot.x, robot.y, robot.z)
        for task_id, start in zip(path, starts[robot_id]):
            task = by_task[task_id]
            if not capable(config, robot, task):
                raise AssertionError("Robot owns a task it cannot do")
            arrival = free_at + math.dist(position, (task.x, task.y, task.z)) / robot.nom_velocity
            if start + 1e-7 < arrival or not task.start_time - 1e-7 <= start <= task.end_time + 1e-7:
                raise AssertionError("Infeasible start time")
            score += task.task_value * math.exp(-task.discount * (start - task.start_time))
            free_at, position = start + task.duration, (task.x, task.y, task.z)
    return len(assigned), score


class Tally:
    """Communication and runtime summed over every auction one method runs."""

    def __init__(self):
        self.broadcasts = self.broadcasts_settled = 0
        self.rounds = self.rounds_settled = 0
        self.runtime = 0.0

    def run(self, *args, **kwargs):
        began = time.perf_counter()
        paths, starts, solver = auction(*args, **kwargs)
        self.runtime += time.perf_counter() - began
        self.broadcasts += solver.total_broadcasts
        self.broadcasts_settled += solver.broadcasts_until_settled
        self.rounds += solver.iterations
        self.rounds_settled += solver.settled_round
        return paths, starts


def run_trial(seed, team_size, bonus):
    """Fail one robot after a common initial allocation; re-auction with each method.

    Returns one result row per method, in METHODS order.
    """
    config, agents, tasks, world = make_mission(seed, team_size)
    initial_paths, initial_starts, owner = initial_allocation(config, agents, tasks, world)
    rng = random.Random(f"failure-{seed}-{team_size}")
    failed = rng.choice(sorted(robot_id for robot_id, path in initial_paths.items() if path))
    survivors = [agent.agent_id for agent in agents if agent.agent_id != failed]
    affected = sorted(task_id for task_id, robot_id in owner.items() if robot_id == failed)
    all_tasks = {task.task_id for task in tasks}
    near = lambda robot, task: math.dist((robot.x, robot.y), (task.x, task.y)) <= LOCAL_RADIUS

    rows = []
    for method in METHODS:
        tally = Tally()
        scope, reason, participants = "global", "", survivors
        final = None
        if method == "scoped_ed_cbba":
            nearby = {task_id: [robot_id for robot_id in survivors
                                if capable(config, agents[robot_id], tasks[task_id])
                                and near(agents[robot_id], tasks[task_id])]
                      for task_id in affected}
            if len(affected) > MAX_LOCAL_AFFECTED:
                reason = "too_many_affected_tasks"
            elif any(not robots for robots in nearby.values()):
                reason = "no_nearby_capable_robot"
            else:
                local_ids = sorted({r for robots in nearby.values() for r in robots})
                scoped = set(affected) | {task_id for task_id, robot_id in owner.items()
                                          if robot_id in local_ids}
                # Affected tasks are open only to robots within the radius.
                eligible = lambda robot, task: task.task_id not in affected or near(robot, task)
                paths, starts = tally.run(config, agents, tasks, world, local_ids, scoped,
                                          owner, bonus, True, eligible=eligible)
                if {t for path in paths.values() for t in path} == scoped:
                    final = ({r: initial_paths[r] for r in survivors},
                             {r: initial_starts[r] for r in survivors})
                    final[0].update(paths)
                    final[1].update(starts)
                    scope, participants = "local", local_ids
                else:
                    reason = "local_schedule_infeasible"
        if final is None:
            final = tally.run(config, agents, tasks, world, survivors, all_tasks, owner,
                              bonus, method != "cbba")
        assigned, score = allocation_score(config, agents, tasks, *final)
        changed = sum(owner[t] != robot_id for robot_id, path in final[0].items() for t in path)
        rows.append(dict(
            seed=seed, team_size=team_size, bonus=bonus, method=method,
            failed_robot=failed, failed_type=config["AGENT_TYPES"][agents[failed].agent_type],
            affected_tasks=len(affected), affected_task_ids=tuple(affected),
            scope=scope, fallback_reason=reason, participants=len(participants),
            participant_ids=tuple(participants),
            broadcasts=tally.broadcasts, broadcasts_settled=tally.broadcasts_settled,
            rounds=tally.rounds, rounds_settled=tally.rounds_settled,
            runtime_s=round(tally.runtime, 6), assigned_tasks=assigned,
            total_tasks=len(tasks), score=round(score, 3), changed_owners=changed))
    return rows


TEAM_SIZES = (6, 12, 24)
LABELS = {"cbba": "Standard CBBA", "ed_cbba": "ED-CBBA",
          "scoped_ed_cbba": "Distance-scoped ED-CBBA"}
# Validated categorical slots 1-3; markers carry identity without colour.
STYLE = {"cbba": ("#2a78d6", "o"), "ed_cbba": ("#eb6834", "s"),
         "scoped_ed_cbba": ("#1baf7a", "^")}
MEASURES = (
    ("broadcasts_settled", "Broadcasts until settled", lambda r: r["broadcasts_settled"]),
    ("per_affected", "Broadcasts per affected task",
     lambda r: r["broadcasts_settled"] / r["affected_tasks"]),
    ("rounds_settled", "Consensus rounds until settled", lambda r: r["rounds_settled"]),
    ("runtime_ms", "Re-auction runtime (ms)", lambda r: 1000 * r["runtime_s"]),
    ("assigned_rate", "Assigned-task rate (%)",
     lambda r: 100 * r["assigned_tasks"] / r["total_tasks"]),
    ("score_per_task", "Allocation score per task (max 100)",
     lambda r: r["score"] / r["total_tasks"]),
)


def mean_ci(values):
    """Mean and normal-approximation 95% confidence half-width."""
    mean = statistics.mean(values)
    half = 1.96 * statistics.stdev(values) / math.sqrt(len(values)) if len(values) > 1 else 0.0
    return mean, half


def summarise(rows, bonus):
    lines = [f"## Incumbency bonus β = {bonus:g}", "",
             "Values are means over paired trials with 95% confidence half-widths. "
             "Broadcasts and rounds are counted until the allocation settled; "
             "the raw columns include the solver's idle rounds before it stopped.", ""]
    header = "| Robots | Method | " + " | ".join(name for _, name, _ in MEASURES) + \
             " | Raw broadcasts | Raw rounds |"
    lines += [header, "|" + " --- |" * (len(MEASURES) + 4)]
    for size in TEAM_SIZES:
        for method in METHODS:
            sample = [r for r in rows if r["bonus"] == bonus and r["team_size"] == size
                      and r["method"] == method]
            cells = []
            for _, _, value in MEASURES:
                mean, half = mean_ci([value(r) for r in sample])
                cells.append(f"{mean:.1f} ± {half:.1f}")
            raw_b = statistics.mean(r["broadcasts"] for r in sample)
            raw_r = statistics.mean(r["rounds"] for r in sample)
            lines.append(f"| {size} | {LABELS[method]} | " + " | ".join(cells) +
                         f" | {raw_b:.1f} | {raw_r:.1f} |")
    lines += ["", "Local recovery by distance-scoped ED-CBBA:", "",
              "| Robots | Trials | Local recovery | No capable robot within 40 m | "
              "Local schedule infeasible | Too many affected tasks | Mean participants when local |",
              "| --- | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for size in TEAM_SIZES:
        sample = [r for r in rows if r["bonus"] == bonus and r["team_size"] == size
                  and r["method"] == "scoped_ed_cbba"]
        local = [r for r in sample if r["scope"] == "local"]
        count = lambda reason: sum(r["fallback_reason"] == reason for r in sample)
        participants = (f"{statistics.mean(r['participants'] for r in local):.1f}"
                        if local else "—")
        lines.append(f"| {size} | {len(sample)} | {len(local)} ({100 * len(local) / len(sample):.0f}%) | "
                     f"{count('no_nearby_capable_robot')} | {count('local_schedule_infeasible')} | "
                     f"{count('too_many_affected_tasks')} | {participants} |")
    return lines + [""]


def plot(rows, bonus, path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    panels = len(MEASURES) + 1
    fig, axes = plt.subplots(2, 4, figsize=(17, 7.5), constrained_layout=True)
    axes = axes.flatten()
    # Methods are offset sideways so identical results stay visible.
    offset = {"cbba": -0.4, "ed_cbba": 0.0, "scoped_ed_cbba": 0.4}
    for ax, (key, name, value) in zip(axes, MEASURES):
        for method in METHODS:
            means, halves = zip(*[mean_ci([value(r) for r in rows if r["bonus"] == bonus
                                           and r["team_size"] == size and r["method"] == method])
                                  for size in TEAM_SIZES])
            colour, marker = STYLE[method]
            ax.errorbar([size + offset[method] for size in TEAM_SIZES], means, yerr=halves, color=colour, marker=marker,
                        markersize=8, linewidth=2, capsize=3, label=LABELS[method])
        ax.set_title(name, fontsize=11)
        if key == "assigned_rate":
            ax.set_ylim(0, 105)
    ax = axes[len(MEASURES)]
    rates = [100 * statistics.mean(r["scope"] == "local" for r in rows if r["bonus"] == bonus
                                   and r["team_size"] == size and r["method"] == "scoped_ed_cbba")
             for size in TEAM_SIZES]
    colour, marker = STYLE["scoped_ed_cbba"]
    ax.plot(TEAM_SIZES, rates, color=colour, marker=marker, markersize=8, linewidth=2)
    ax.set_title("Local recovery rate (%), distance-scoped only", fontsize=11)
    ax.set_ylim(0, 100)
    for ax in axes[:panels]:
        ax.set_xticks(TEAM_SIZES)
        ax.set_xlabel("Robots in team")
        ax.grid(alpha=0.25)
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
    handles, labels = axes[0].get_legend_handles_labels()
    axes[-1].axis("off")
    axes[-1].legend(handles, labels, loc="center", frameon=False, fontsize=11)
    fig.suptitle(f"Experiment 2, exclusive capabilities: post-failure re-auction "
                 f"(incumbency bonus β = {bonus:g}; mean ± 95% CI)", fontsize=13)
    fig.savefig(path, dpi=160)
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trials", type=int, default=30,
                        help="paired trials per team size (at least 2, for confidence intervals)")
    parser.add_argument("--bonuses", type=float, nargs="+", default=[0.0, 0.1],
                        help="incumbency bonus values; the solver multiplies an owner's bid by 1 + β")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "doc" / "exclusive_capabilities")
    args = parser.parse_args()
    if args.trials < 2:
        parser.error("--trials must be at least 2")
    args.output_dir.mkdir(parents=True, exist_ok=True)

    rows = [row for bonus in args.bonuses for size in TEAM_SIZES
            for seed in range(args.trials) for row in run_trial(seed, size, bonus)]
    with (args.output_dir / "trials.csv").open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: " ".join(map(str, v)) if isinstance(v, tuple) else v
                             for k, v in row.items()})
    lines = ["# Experiment 2 results: exclusive capabilities", "",
             f"Generated by `test/run_exclusive_capabilities_experiment.py` with "
             f"{args.trials} paired trials per team size. See `report.md` for the method "
             "and the decisions behind it, and `trials.csv` for every trial.", ""]
    for bonus in args.bonuses:
        lines += summarise(rows, bonus)
        figure = f"bonus_{bonus:g}.png"
        plot(rows, bonus, args.output_dir / figure)
        lines += [f"![Measures against team size, β = {bonus:g}]({figure})", ""]
    (args.output_dir / "summary.md").write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
