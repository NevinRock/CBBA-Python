#!/usr/bin/env python3
"""Experiment 3 (shared capabilities): post-failure re-auction stress tests.

Each trial draws one random mission (air and ground robots; N air-only, N ground-only
and N shared tasks for N robots), computes one common initial ED-CBBA allocation, fails
robot(s), then re-auctions with three paired methods:

  global_cbba   standard CBBA (every robot broadcasts every round), all survivors/tasks
  global_ed     event-driven CBBA, all survivors/tasks
  scoped_ed     event-driven CBBA among capable survivors within RADIUS of an affected
                task (up to MAX_LOCAL_AFFECTED affected tasks); global ED fallback

Shared tasks take ground robots 5 s and air robots 10 s; other tasks take 8 s.

Conditions change ONE factor from the baseline (see CONDITIONS). Within a condition,
every method sees the same mission, the same failed robot(s) and the same failure time.

Outputs per condition in <out-root>/<condition>/: trials.csv (one row per mission x
failure mode x method), shared_winners.csv, errors.jsonl, run_meta.json.
"""

import argparse
import copy
import csv
import json
import math
import multiprocessing as mp
import os
import platform
import random
import subprocess
import sys
import time
import traceback
from collections import deque
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "lib"))

from Agent import Agent  # noqa: E402
from CBBA import CBBA  # noqa: E402
from Task import Task  # noqa: E402
from WorldInfo import WorldInfo  # noqa: E402

CONFIG_PATH = ROOT / "config_exp3_shared.json"
METHODS = ("global_cbba", "global_ed", "scoped_ed")

BASE = dict(layout="uniform", ground_fraction=0.5, comms="full", failure_time="pre",
            failure_modes=("random", "targeted_shared"))
CONDITIONS = {
    "baseline": dict(BASE),
    "mid_mission": dict(BASE, failure_time="mid"),
    "range_limited": dict(BASE, comms="range"),
    "clustered": dict(BASE, layout="clustered"),
    "imbalanced": dict(BASE, ground_fraction=0.25),
    "double_failure": dict(BASE, failure_modes=("random_pair", "ground_pair")),
    "cascading": dict(BASE, failure_modes=("cascade",)),
}
RANGE_FACTOR = 1.2          # radio range = 1.2 x the smallest range keeping the graph connected
CLUSTERS, CLUSTER_SIGMA_M = 3, 8.0
MID_FAIL_FRACTION = (0.2, 0.6)  # mid-mission failure time, as a fraction of the initial makespan

TRIAL_FIELDS = [
    "condition", "size", "seed", "failure_mode", "method", "n_agents", "n_air", "n_ground",
    "n_tasks", "initial_assigned", "initial_score", "initial_rounds", "initial_broadcasts",
    "initial_makespan_s", "fail_time_s", "done_before_failure", "n_failed", "failed_agents",
    "failed_types", "affected_tasks", "affected_shared", "comm_range_m", "graph_diameter",
    "lambda2", "scope", "fallback_reason", "participants", "auction_tasks",
    "broadcasts", "broadcasts_to_converge", "broadcasts_per_affected", "rounds",
    "rounds_to_converge", "cpu_s", "wall_s", "consensus_ok", "duplicate_tasks",
    "assigned_tasks", "assigned_rate", "score", "makespan_s", "mean_finish_s",
    "shared_busy_s", "changed_owners", "shared_total", "shared_won_air",
    "shared_won_ground", "shared_unassigned", "termination",
]
WINNER_FIELDS = [
    "condition", "size", "seed", "failure_mode", "method", "task_id", "initial_winner_type",
    "winner_type", "nearest_air_m", "nearest_ground_m",
]


def load_config(path=CONFIG_PATH):
    with Path(path).open() as file:
        return json.load(file)


def trial_seed(size, seed):
    """Paired seed: identical draws for every method, failure mode and condition."""
    return 1_000_003 * size + seed


def type_counts(size, ground_fraction):
    n_ground = max(1, round(size * ground_fraction))
    return size - n_ground, n_ground


# ---------------------------------------------------------------- scenario
def build_mission(config, size, seed, condition="baseline"):
    """Random mission. Robot and task IDs are shuffled so that CBBA's lower-ID
    tie-break does not systematically favour one robot type or task type."""
    cond = CONDITIONS[condition]
    exp = config["EXPERIMENT"]
    agent_types, task_types = config["AGENT_TYPES"], config["TASK_TYPES"]
    side = float(exp["MAP_SIZE_M"])
    rng = random.Random(trial_seed(size, seed))

    n_air, n_ground = type_counts(size, cond["ground_fraction"])
    kinds = ["air"] * n_air + ["ground"] * n_ground
    robot_xy = [(rng.uniform(0, side), rng.uniform(0, side)) for _ in kinds]
    order = list(range(size))
    rng.shuffle(order)
    agents = [Agent(agent_id=new_id, agent_type=agent_types.index(kinds[old]),
                    x=robot_xy[old][0], y=robot_xy[old][1], z=0,
                    nom_velocity=float(exp["AGENT_SPEED_MPS"][kinds[old]]))
              for new_id, old in enumerate(order)]

    per_type = size * int(exp["TASKS_PER_TYPE_PER_ROBOT"])
    task_kinds = [k for k in task_types for _ in range(per_type)]
    task_xy = [(rng.uniform(0, side), rng.uniform(0, side)) for _ in task_kinds]
    if cond["layout"] == "clustered":
        centres = [(rng.uniform(0.15 * side, 0.85 * side), rng.uniform(0.15 * side, 0.85 * side))
                   for _ in range(CLUSTERS)]
        task_xy = []
        for _ in task_kinds:
            cx, cy = rng.choice(centres)
            task_xy.append((min(side, max(0.0, rng.gauss(cx, CLUSTER_SIGMA_M))),
                            min(side, max(0.0, rng.gauss(cy, CLUSTER_SIGMA_M)))))
    order = list(range(len(task_kinds)))
    rng.shuffle(order)
    tasks = []
    for new_id, old in enumerate(order):
        defaults = config["TASK_DEFAULTS"][task_kinds[old]]
        by_type = defaults.get("DURATION_BY_AGENT_TYPE")
        tasks.append(Task(
            task_id=new_id, task_type=task_types.index(task_kinds[old]),
            task_value=float(exp["TASK_VALUE"]), start_time=float(defaults["START_TIME"]),
            end_time=float(defaults["END_TIME"]), duration=float(defaults["DURATION"]),
            discount=float(exp["TASK_DISCOUNT"]), x=task_xy[old][0], y=task_xy[old][1], z=0,
            duration_by_agent_type=({agent_types.index(k): float(v) for k, v in by_type.items()}
                                    if by_type else None)))
    world = WorldInfo([0, side], [0, side], [0, 0])
    return agents, tasks, world


def can_do(config, agent, task):
    agent_type = config["AGENT_TYPES"][agent.agent_type]
    return config["TASK_TYPES"][task.task_type] in config["COMPATIBILITY"][agent_type]


# ---------------------------------------------------------------- communication graph
def connect_threshold(points):
    """Smallest radio range that connects all points (longest edge of the Euclidean MST)."""
    n = len(points)
    if n < 2:
        return 0.0
    best = [math.inf] * n
    in_tree = [False] * n
    best[0], longest = 0.0, 0.0
    for _ in range(n):
        u = min((i for i in range(n) if not in_tree[i]), key=best.__getitem__)
        in_tree[u] = True
        longest = max(longest, best[u])
        for v in range(n):
            if not in_tree[v]:
                best[v] = min(best[v], math.dist(points[u], points[v]))
    return longest


def adjacency(points, comm_range):
    n = len(points)
    return [[i != j and math.dist(points[i], points[j]) <= comm_range for j in range(n)]
            for i in range(n)]


def graph_stats(graph):
    """(connected, diameter in hops, algebraic connectivity lambda2)."""
    n = len(graph)
    if n < 2:
        return True, 0, 0.0
    diameter = 0
    for source in range(n):
        dist = {source: 0}
        queue = deque([source])
        while queue:
            u = queue.popleft()
            for v in range(n):
                if graph[u][v] and v not in dist:
                    dist[v] = dist[u] + 1
                    queue.append(v)
        if len(dist) < n:
            return False, math.inf, 0.0
        diameter = max(diameter, max(dist.values()))
    a = np.array(graph, dtype=float)
    lap = np.diag(a.sum(axis=1)) - a
    return True, diameter, float(np.sort(np.linalg.eigvalsh(lap))[1])


def pick_range(agents, comms):
    """Radio range for a rule: "full" (everyone hears everyone), "range" (RANGE_FACTOR x
    the connectivity threshold), ("factor", f) or ("fixed", metres)."""
    if comms == "full":
        return None
    if comms == "range":
        comms = ("factor", RANGE_FACTOR)
    kind, value = comms
    if kind == "fixed":
        return float(value)
    return value * connect_threshold([(a.x, a.y) for a in agents])


# ---------------------------------------------------------------- auctions
def auction(config, agents, tasks, world, participant_ids, task_ids, event_triggered,
            owner=None, affected_ids=(), radius=None, comm_range=None, **solver_options):
    """One CBBA/ED-CBBA auction over a subset; returns paths/times keyed by real IDs.
    solver_options pass through to CBBA.solve (e.g. packet_loss_probability)."""
    exp = config["EXPERIMENT"]
    participant_ids = sorted(participant_ids)
    by_agent = {a.agent_id: a for a in agents}
    by_task = {t.task_id: t for t in tasks}
    local_id = {agent_id: i for i, agent_id in enumerate(participant_ids)}
    local_agents = []
    for agent_id in participant_ids:
        agent = copy.deepcopy(by_agent[agent_id])
        agent.agent_id = local_id[agent_id]
        local_agents.append(agent)
    local_tasks = [copy.deepcopy(by_task[task_id]) for task_id in sorted(task_ids)]
    incumbents = {task_id: local_id[agent_id] for task_id, agent_id in (owner or {}).items()
                  if task_id in task_ids and agent_id in local_id}
    eligibility = None
    if radius is not None:
        affected_ids = set(affected_ids)
        eligibility = [[t.task_id not in affected_ids or
                        math.dist((by_agent[a].x, by_agent[a].y), (t.x, t.y)) <= radius
                        for t in local_tasks] for a in participant_ids]
    graph = None
    if comm_range is not None:
        graph = adjacency([(a.x, a.y) for a in local_agents], comm_range)
    solver = CBBA(config)
    wall0, cpu0 = time.perf_counter(), time.process_time()
    paths, times = solver.solve(
        local_agents, local_tasks, world, max_depth=int(exp["MAX_DEPTH"]),
        time_window_flag=True, event_triggered=event_triggered, communication_graph=graph,
        incumbent_owners=incumbents,
        incumbency_bonus=float(exp["INCUMBENCY_BONUS"]) if owner else 0.0,
        agent_task_eligibility=eligibility, **solver_options)
    cpu, wall = time.process_time() - cpu0, time.perf_counter() - wall0
    converged = solver.last_change_round
    stats = dict(solver=solver, broadcasts=solver.total_broadcasts,
                 broadcasts_to_converge=sum(solver.broadcast_history[:converged]),
                 rounds=solver.iterations, rounds_to_converge=converged, cpu_s=cpu, wall_s=wall,
                 consensus_ok=all(row == solver.winners_list[0] for row in solver.winners_list),
                 termination=solver.termination_reason or "")
    paths = {agent_id: [t for t in path if t != -1] for agent_id, path in zip(participant_ids, paths)}
    times = {agent_id: list(row[:len(paths[agent_id])]) for agent_id, row in zip(participant_ids, times)}
    return paths, times, stats


def empty_stats():
    return dict(broadcasts=0, broadcasts_to_converge=0, rounds=0, rounds_to_converge=0,
                cpu_s=0.0, wall_s=0.0, consensus_ok=True, termination="")


def add_stats(total, extra):
    for key in ("broadcasts", "broadcasts_to_converge", "rounds", "rounds_to_converge",
                "cpu_s", "wall_s"):
        total[key] += extra[key]
    total["consensus_ok"] = total["consensus_ok"] and extra["consensus_ok"]
    total["termination"] = "+".join(filter(None, [total["termination"], extra["termination"]]))
    return total


# ---------------------------------------------------------------- schedules
def evaluate(config, agents, tasks, paths, times):
    """Check a plan for the given robot states; return per-task execution records.

    Raises only on harness bugs (incompatible type, capacity, infeasible time).
    Duplicate claims are an algorithm outcome and are reported, not raised."""
    exp = config["EXPERIMENT"]
    by_task = {t.task_id: t for t in tasks}
    records, duplicates = {}, 0
    for agent in agents:
        path, starts = paths.get(agent.agent_id, []), times.get(agent.agent_id, [])
        if len(path) > int(exp["MAX_DEPTH"]) or len(path) != len(starts):
            raise AssertionError("capacity or schedule length violated")
        free_at, position = agent.availability, (agent.x, agent.y)
        for task_id, start in zip(path, starts):
            task = by_task[task_id]
            if not can_do(config, agent, task):
                raise AssertionError("incompatible assignment")
            arrival = free_at + math.dist(position, (task.x, task.y)) / agent.nom_velocity
            if not task.start_time - 1e-6 <= start <= task.end_time + 1e-6 or start + 1e-6 < arrival:
                raise AssertionError("infeasible start time")
            end = start + task.duration_for(agent.agent_type)
            if task_id in records:
                duplicates += 1
            else:
                records[task_id] = dict(agent=agent.agent_id, agent_type=agent.agent_type,
                                        start=start, end=end)
            free_at, position = end, (task.x, task.y)
    return records, duplicates


def advance(agents, tasks, paths, times, t):
    """Robot states at time t under a plan: positions, availability, finished tasks,
    tasks in progress, and each robot's not-yet-started remainder of its plan."""
    by_task = {task.task_id: task for task in tasks}
    states, done, running, rest_paths, rest_times = [], {}, {}, {}, {}
    for agent in agents:
        state = copy.deepcopy(agent)
        state.availability = t
        free_at, (x, y) = agent.availability, (agent.x, agent.y)
        path, starts = paths.get(agent.agent_id, []), times.get(agent.agent_id, [])
        rest_paths[agent.agent_id], rest_times[agent.agent_id] = [], []
        placed = False
        for k, (task_id, start) in enumerate(zip(path, starts)):
            task = by_task[task_id]
            end = start + task.duration_for(agent.agent_type)
            leg = math.dist((x, y), (task.x, task.y))
            arrive = free_at + leg / agent.nom_velocity
            if not placed and t < start:
                if t < arrive:  # travelling: interpolate along the leg
                    frac = (t - free_at) / max(arrive - free_at, 1e-9) if t > free_at else 0.0
                    state.x, state.y = x + frac * (task.x - x), y + frac * (task.y - y)
                else:  # waiting at the task location
                    state.x, state.y = task.x, task.y
                rest_paths[agent.agent_id] = list(path[k:])
                rest_times[agent.agent_id] = list(starts[k:])
                placed = True
                break
            if start <= t < end:  # executing
                running[task_id] = dict(agent=agent.agent_id, agent_type=agent.agent_type,
                                        start=start, end=end)
                state.x, state.y, state.availability = task.x, task.y, end
                rest_paths[agent.agent_id] = list(path[k + 1:])
                rest_times[agent.agent_id] = list(starts[k + 1:])
                placed = True
                break
            done[task_id] = dict(agent=agent.agent_id, agent_type=agent.agent_type,
                                 start=start, end=end)
            free_at, (x, y) = end, (task.x, task.y)
        if not placed:
            state.x, state.y = x, y
        states.append(state)
    return states, done, running, rest_paths, rest_times


# ---------------------------------------------------------------- failure choice
def choose_failures(config, agents, tasks, owner, size, seed, mode):
    """Return a list of failure events; each event is a list of robots failing together.
    Choices depend only on the mission, the initial allocation and the seed, never on
    the re-auction method, so all methods face the same failures."""
    rng = random.Random(f"fail-{mode}-{trial_seed(size, seed)}")
    held = {}
    for task_id, agent_id in owner.items():
        held.setdefault(agent_id, []).append(task_id)
    working = sorted(held)
    by_agent = {a.agent_id: a for a in agents}
    by_task = {t.task_id: t for t in tasks}
    ground = config["AGENT_TYPES"].index("ground")
    shared = config["TASK_TYPES"].index("shared")
    if mode == "random":
        return [[rng.choice(working)]]
    if mode == "targeted_shared":
        def key(agent_id):
            return (sum(by_task[t].task_type == shared for t in held[agent_id]), len(held[agent_id]))
        best = max(key(a) for a in working)
        return [[rng.choice([a for a in working if key(a) == best])]]
    if mode == "random_pair":
        return [rng.sample(working, min(2, len(working)))]
    if mode == "ground_pair":
        grounds = [a for a in working if by_agent[a].agent_type == ground]
        if len(grounds) < 2:
            grounds += rng.sample([a for a in working if a not in grounds], 2 - len(grounds))
        return [rng.sample(grounds, 2)]
    if mode == "cascade":
        first, second = rng.sample(working, 2)
        return [[first], [second]]
    raise ValueError(f"unknown failure mode {mode}")


# ---------------------------------------------------------------- one re-auction
def reauction(config, agents, tasks, world, owner, failed, method, plan_paths, plan_times,
              comm_range_rule, refresh_interval=5, **solver_options):
    """Re-auction `tasks` among surviving `agents` (robot states) after `failed` fail.
    plan_paths/times: the survivors' current plans (kept by robots outside a local auction)."""
    exp = config["EXPERIMENT"]
    failed = set(failed)
    survivors = [a for a in agents if a.agent_id not in failed]
    survivor_ids = [a.agent_id for a in survivors]
    task_ids = {t.task_id for t in tasks}
    affected = {t for t, a in owner.items() if a in failed and t in task_ids}
    by_task = {t.task_id: t for t in tasks}
    by_agent = {a.agent_id: a for a in survivors}
    comm_range = pick_range(survivors, comm_range_rule)
    stats = empty_stats()
    info = dict(scope="global", fallback_reason="", participants=len(survivors),
                auction_tasks=len(task_ids), comm_range=comm_range)
    live_owner = {t: a for t, a in owner.items() if a not in failed and t in task_ids}

    if method in ("global_cbba", "global_ed", "global_ed_refresh"):
        options = dict(solver_options)
        if method == "global_ed_refresh":
            options["refresh_interval"] = refresh_interval
        paths, times, s = auction(config, survivors, tasks, world, survivor_ids, task_ids,
                                  event_triggered=(method != "global_cbba"), owner=live_owner,
                                  comm_range=comm_range, **options)
        return paths, times, add_stats(stats, s), info

    if method != "scoped_ed":
        raise ValueError(f"unknown method {method}")
    radius = float(exp["SCOPE_RADIUS_M"])
    if not affected:
        info["fallback_reason"] = "nothing_affected"
    elif len(affected) > int(exp["MAX_LOCAL_AFFECTED"]):
        info["fallback_reason"] = "too_many_affected_tasks"
    else:
        eligible = {t: [a for a in survivor_ids if can_do(config, by_agent[a], by_task[t]) and
                        math.dist((by_agent[a].x, by_agent[a].y),
                                  (by_task[t].x, by_task[t].y)) <= radius]
                    for t in affected}
        participants = sorted({a for e in eligible.values() for a in e})
        local_graph_ok = True
        if comm_range is not None and participants:
            local_graph_ok = graph_stats(adjacency(
                [(by_agent[a].x, by_agent[a].y) for a in participants], comm_range))[0]
        if any(not e for e in eligible.values()):
            info["fallback_reason"] = "no_nearby_capable_robot"
        elif not local_graph_ok:
            info["fallback_reason"] = "local_group_disconnected"
        else:
            scoped = affected | {t for t, a in live_owner.items() if a in participants}
            local_paths, local_times, s = auction(
                config, survivors, tasks, world, participants, scoped, event_triggered=True,
                owner=live_owner, affected_ids=affected, radius=radius, comm_range=comm_range,
                **solver_options)
            add_stats(stats, s)
            if {t for p in local_paths.values() for t in p} == scoped:
                paths = {a: list(plan_paths.get(a, [])) for a in survivor_ids}
                times = {a: list(plan_times.get(a, [])) for a in survivor_ids}
                paths.update(local_paths)
                times.update(local_times)
                info.update(scope="local", participants=len(participants), auction_tasks=len(scoped))
                return paths, times, stats, info
            info["fallback_reason"] = "local_capacity_or_schedule_infeasible"
    paths, times, s = auction(config, survivors, tasks, world, survivor_ids, task_ids,
                              event_triggered=True, owner=live_owner, comm_range=comm_range,
                              **solver_options)
    return paths, times, add_stats(stats, s), info


# ---------------------------------------------------------------- one job
def run_job(args):
    """Run one (condition, size, seed): one common initial allocation, then every
    failure mode x method."""
    condition, size, seed, methods, config_path = args
    cond = CONDITIONS[condition]
    config = load_config(config_path)
    try:
        agents, tasks, world = build_mission(config, size, seed, condition)
        type_name = lambda agent_type: config["AGENT_TYPES"][agent_type]  # noqa: E731
        shared_type = config["TASK_TYPES"].index("shared")
        by_task = {t.task_id: t for t in tasks}
        shared_ids = [t.task_id for t in tasks if t.task_type == shared_type]

        init_range = pick_range(agents, cond["comms"])
        init_paths, init_times, init_stats = auction(
            config, agents, tasks, world, [a.agent_id for a in agents],
            {t.task_id for t in tasks}, event_triggered=True, comm_range=init_range)
        init_records, init_dup = evaluate(config, agents, tasks, init_paths, init_times)
        if init_dup:
            raise AssertionError("initial allocation has duplicate claims")
        owner = {t: r["agent"] for t, r in init_records.items()}
        init_score = sum(by_task[t].task_value * math.exp(-by_task[t].discount * (r["start"] - by_task[t].start_time))
                         for t, r in init_records.items())
        init_makespan = max((r["end"] for r in init_records.values()), default=0.0)

        trial_rows, winner_rows = [], []
        for mode in cond["failure_modes"]:
            events = choose_failures(config, agents, tasks, owner, size, seed, mode)
            all_failed = [a for event in events for a in event]
            fail_time = 0.0
            if cond["failure_time"] == "mid":
                lo, hi = MID_FAIL_FRACTION
                fail_time = random.Random(f"time-{trial_seed(size, seed)}").uniform(lo, hi) * init_makespan

            for method in methods:
                # Robot states at the failure time (identical for every method).
                if fail_time > 0:
                    states, done, running, plan_p, plan_t = advance(
                        agents, tasks, init_paths, init_times, fail_time)
                else:
                    states, done, running = copy.deepcopy(agents), {}, {}
                    plan_p, plan_t = copy.deepcopy(init_paths), copy.deepcopy(init_times)
                locked = dict(done)  # finished work, plus work survivors are executing
                locked.update({t: r for t, r in running.items() if r["agent"] not in all_failed})
                cur_owner = {t: a for t, a in owner.items() if t not in locked}
                stats, info, affected_total, affected_shared = empty_stats(), {}, 0, 0
                dead = set()
                for event in events:
                    dead |= set(event)
                    open_tasks = [t for t in tasks if t.task_id not in locked]
                    affected_now = [t for t, a in cur_owner.items() if a in event]
                    affected_total += len(affected_now)
                    affected_shared += sum(by_task[t].task_type == shared_type for t in affected_now)
                    live_states = [s for s in states if s.agent_id not in dead - set(event)]
                    plan_p = {a: p for a, p in plan_p.items() if a not in dead}
                    plan_t = {a: p for a, p in plan_t.items() if a not in dead}
                    paths, times, s, info = reauction(
                        config, live_states, open_tasks, world, cur_owner, event, method,
                        plan_p, plan_t, cond["comms"])
                    add_stats(stats, s)
                    cur_owner = {t: a for a, p in paths.items() for t in p}
                    plan_p, plan_t = paths, times
                survivors = [s for s in states if s.agent_id not in dead]
                new_records, duplicates = evaluate(
                    config, survivors, [t for t in tasks if t.task_id not in locked], plan_p, plan_t)
                records = dict(locked)
                records.update(new_records)
                score = sum(by_task[t].task_value * math.exp(-by_task[t].discount * (r["start"] - by_task[t].start_time))
                            for t, r in records.items())
                ends = [r["end"] for r in records.values()]
                graph_ok, diameter, lam2 = True, "", ""
                if info.get("comm_range") is not None:
                    graph_ok, diameter, lam2 = graph_stats(adjacency(
                        [(s.x, s.y) for s in survivors], info["comm_range"]))
                    lam2 = round(lam2, 4)
                won = {t: records[t]["agent_type"] if t in records else None for t in shared_ids}
                trial_rows.append(dict(
                    condition=condition, size=size, seed=seed, failure_mode=mode, method=method,
                    n_agents=len(agents),
                    n_air=sum(type_name(a.agent_type) == "air" for a in agents),
                    n_ground=sum(type_name(a.agent_type) == "ground" for a in agents),
                    n_tasks=len(tasks), initial_assigned=len(init_records),
                    initial_score=round(init_score, 4), initial_rounds=init_stats["rounds"],
                    initial_broadcasts=init_stats["broadcasts"],
                    initial_makespan_s=round(init_makespan, 3), fail_time_s=round(fail_time, 3),
                    done_before_failure=len(done), n_failed=len(all_failed),
                    failed_agents=";".join(map(str, all_failed)),
                    failed_types=";".join(type_name(agents[a].agent_type) for a in all_failed),
                    affected_tasks=affected_total, affected_shared=affected_shared,
                    comm_range_m=(round(info["comm_range"], 3)
                                  if info.get("comm_range") is not None else ""),
                    graph_diameter=diameter, lambda2=lam2,
                    scope=info["scope"], fallback_reason=info["fallback_reason"],
                    participants=info["participants"], auction_tasks=info["auction_tasks"],
                    broadcasts=stats["broadcasts"],
                    broadcasts_to_converge=stats["broadcasts_to_converge"],
                    broadcasts_per_affected=(round(stats["broadcasts"] / affected_total, 4)
                                             if affected_total else ""),
                    rounds=stats["rounds"], rounds_to_converge=stats["rounds_to_converge"],
                    cpu_s=round(stats["cpu_s"], 5), wall_s=round(stats["wall_s"], 5),
                    consensus_ok=int(stats["consensus_ok"]), duplicate_tasks=duplicates,
                    assigned_tasks=len(records), assigned_rate=round(len(records) / len(tasks), 5),
                    score=round(score, 4), makespan_s=round(max(ends, default=0.0), 3),
                    mean_finish_s=round(sum(ends) / len(ends), 3) if ends else "",
                    shared_busy_s=round(sum(records[t]["end"] - records[t]["start"]
                                            for t in shared_ids if t in records), 3),
                    changed_owners=sum(1 for t, a in owner.items() if a not in all_failed
                                       and t in records and records[t]["agent"] != a),
                    shared_total=len(shared_ids),
                    shared_won_air=sum(1 for w in won.values() if w is not None and type_name(w) == "air"),
                    shared_won_ground=sum(1 for w in won.values() if w is not None and type_name(w) == "ground"),
                    shared_unassigned=sum(1 for w in won.values() if w is None),
                    termination=stats["termination"]))
                for task_id, winner_type in won.items():
                    task = by_task[task_id]
                    def nearest(kind):
                        d = [math.dist((s.x, s.y), (task.x, task.y)) for s in survivors
                             if type_name(s.agent_type) == kind]
                        return round(min(d), 3) if d else ""
                    winner_rows.append(dict(
                        condition=condition, size=size, seed=seed, failure_mode=mode,
                        method=method, task_id=task_id,
                        initial_winner_type=(type_name(init_records[task_id]["agent_type"])
                                             if task_id in init_records else ""),
                        winner_type=type_name(winner_type) if winner_type is not None else "",
                        nearest_air_m=nearest("air"), nearest_ground_m=nearest("ground")))
        return dict(key=(condition, size, seed), trials=trial_rows, winners=winner_rows, error=None)
    except Exception:  # keep long runs alive; errors are reported and fail the smoke test
        return dict(key=(condition, size, seed), trials=[], winners=[], error=traceback.format_exc())


# ---------------------------------------------------------------- driver
def git_revision():
    try:
        rev = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT,
                             capture_output=True, text=True).stdout.strip()
        dirty = subprocess.run(["git", "status", "--porcelain", "--", "lib", "test"], cwd=ROOT,
                               capture_output=True, text=True).stdout.strip()
        return (rev or "unknown") + ("-dirty" if dirty else "")
    except OSError:
        return "unknown"


def done_keys(path):
    if not path.exists():
        return set()
    with path.open() as file:
        return {(int(r["size"]), int(r["seed"])) for r in csv.DictReader(file)}


def append_rows(path, fields, rows):
    new = not path.exists()
    with path.open("a", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fields, lineterminator="\n")
        if new:
            writer.writeheader()
        writer.writerows(rows)


def main(argv=None):
    config = load_config()
    exp = config["EXPERIMENT"]
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--conditions", nargs="+", default=["baseline"],
                        choices=list(CONDITIONS) + ["all"])
    parser.add_argument("--sizes", type=int, nargs="+", default=exp["TEAM_SIZES"])
    parser.add_argument("--seeds", type=int, default=exp["SEEDS"], help="number of seeds")
    parser.add_argument("--seed-start", type=int, default=0)
    parser.add_argument("--methods", nargs="+", default=list(METHODS), choices=METHODS)
    parser.add_argument("--jobs", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    parser.add_argument("--out-root", type=Path, default=ROOT / "results" / "exp3_shared")
    parser.add_argument("--resume", action="store_true", help="skip (size, seed) already written")
    parser.add_argument("--smoke", action="store_true",
                        help="2 seeds, fresh output, exit non-zero on any error")
    args = parser.parse_args(argv)
    conditions = list(CONDITIONS) if "all" in args.conditions else args.conditions
    if args.smoke:
        args.seeds, args.resume = 2, False

    jobs, metas = [], {}
    for condition in conditions:
        out = args.out_root / condition
        out.mkdir(parents=True, exist_ok=True)
        if not args.resume:
            for name in ("trials.csv", "shared_winners.csv", "errors.jsonl"):
                (out / name).unlink(missing_ok=True)
        skip = done_keys(out / "trials.csv") if args.resume else set()
        pending = [(condition, size, seed, tuple(args.methods), str(CONFIG_PATH))
                   for size in args.sizes
                   for seed in range(args.seed_start, args.seed_start + args.seeds)
                   if (size, seed) not in skip]
        jobs += pending
        metas[condition] = dict(
            condition=condition, settings=CONDITIONS[condition], started=time.strftime("%Y-%m-%d %H:%M:%S"),
            host=platform.node(), cpus=os.cpu_count(), jobs=args.jobs,
            python=platform.python_version(), git=git_revision(),
            argv=sys.argv[1:] if argv is None else argv, pending_jobs=len(pending),
            skipped_jobs=len(skip), experiment=exp, errors=0, cpu_s_by_size={})
        (out / "run_meta.json").write_text(json.dumps(metas[condition], indent=2, default=str))
    jobs.sort(key=lambda job: -job[1])  # largest teams first for better load balance
    print(f"{len(jobs)} jobs over {len(conditions)} condition(s) on {args.jobs} processes "
          f"-> {args.out_root}", flush=True)

    start = time.perf_counter()
    with mp.get_context("spawn").Pool(args.jobs) as pool:
        for n, result in enumerate(pool.imap_unordered(run_job, jobs), 1):
            condition, size, seed = result["key"]
            out, meta = args.out_root / condition, metas[condition]
            if result["error"]:
                meta["errors"] += 1
                with (out / "errors.jsonl").open("a") as file:
                    file.write(json.dumps(dict(size=size, seed=seed, error=result["error"])) + "\n")
                print(f"[{n}/{len(jobs)}] {condition} size={size} seed={seed} ERROR", flush=True)
                continue
            append_rows(out / "trials.csv", TRIAL_FIELDS, result["trials"])
            append_rows(out / "shared_winners.csv", WINNER_FIELDS, result["winners"])
            cpu = sum(r["cpu_s"] for r in result["trials"])
            meta["cpu_s_by_size"].setdefault(str(size), []).append(round(cpu, 3))
            if n % 10 == 0 or n == len(jobs):
                print(f"[{n}/{len(jobs)}] {condition} size={size} seed={seed} cpu={cpu:.1f}s "
                      f"elapsed={time.perf_counter() - start:.0f}s", flush=True)

    total_errors = 0
    for condition, meta in metas.items():
        meta.update(finished=time.strftime("%Y-%m-%d %H:%M:%S"),
                    elapsed_s=round(time.perf_counter() - start, 1))
        total_errors += meta["errors"]
        (args.out_root / condition / "run_meta.json").write_text(json.dumps(meta, indent=2, default=str))
    print(json.dumps({c: m["errors"] for c, m in metas.items()}), "errors;",
          f"elapsed {time.perf_counter() - start:.1f}s")
    return 1 if total_errors else 0


if __name__ == "__main__":
    sys.exit(main())
