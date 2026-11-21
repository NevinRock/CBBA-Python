#!/usr/bin/env python3
"""Paired, pre-execution failure replanning. Default CLI runs nine smoke trials.

The existing CBBA implementation is unchanged. Spatial scope follows
run_spatial_reauction_experiment.py, with explicit per-auction diagnostics.
"""
import argparse
import copy
import csv
import hashlib
import json
import math
import platform
import random
import statistics
import subprocess
import sys
import time
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "lib")]
from Agent import Agent
from CBBA import CBBA
from Task import Task
from WorldInfo import WorldInfo

METHODS = ("Standard CBBA", "ED-CBBA", "Distance-Scoped ED-CBBA")
TIMING_FIELDS = {"runtime_seconds", "local_runtime_seconds", "global_runtime_seconds",
                 "auction_runtime_seconds", "controller_validation_seconds"}


def json_default(value):
    if hasattr(value, "item"):
        return value.item()
    raise TypeError(f"Cannot serialize {type(value)}")


def canonical(value):
    # Normalize integer mapping keys to JSON string keys before sorting. This
    # makes a saved snapshot independently hashable after a JSON round trip.
    normalized = json.loads(json.dumps(value, default=json_default, allow_nan=False))
    return json.dumps(normalized, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def load_config(path=None):
    return json.loads(Path(path or ROOT / "config_homogeneous_scenario.json").read_text(encoding="utf-8"))


def build_scenario(num_robots, seed, config=None):
    config = copy.deepcopy(config or load_config())
    spec = config["EXPERIMENT"]
    if str(num_robots) not in spec["SCALES"] or seed not in spec["SEEDS"]:
        raise ValueError("Use a configured robot scale and seed 0..29")
    rng = random.Random(seed)
    size = spec["MAP_SIZE"]
    agents = [Agent(agent_id=i, agent_type=0, nom_velocity=spec["VELOCITY"],
                    x=rng.uniform(0, size), y=rng.uniform(0, size))
              for i in range(num_robots)]
    defaults = config["TASK_DEFAULTS"]["task"]
    tasks = [Task(task_id=j, task_type=0, task_value=spec["TASK_VALUE"],
                  start_time=defaults["START_TIME"], end_time=defaults["END_TIME"],
                  duration=defaults["DURATION"], discount=spec["DISCOUNT"],
                  x=rng.uniform(0, size), y=rng.uniform(0, size))
             for j in range(spec["SCALES"][str(num_robots)])]
    return config, agents, tasks, WorldInfo([0, size], [0, size], [0, 0])


def validate_schedule(config, agents, tasks, paths, times, failed_agent=None):
    """Validate returned schedules independently; incompleteness is reported separately."""
    errors = []
    by_agent = {a.agent_id: a for a in agents}
    by_task = {t.task_id: t for t in tasks}
    counts = Counter(t for path in paths.values() for t in path)
    if any(count > 1 for count in counts.values()):
        errors.append("duplicate_task_ownership")
    if paths.get(failed_agent):
        errors.append("failed_agent_assigned")
    score = 0.0
    for agent_id, path in paths.items():
        if agent_id not in by_agent:
            errors.append(f"unknown_agent:{agent_id}")
            continue
        agent = by_agent[agent_id]
        starts = times.get(agent_id, [])
        if len(path) > config["EXPERIMENT"]["MAX_DEPTH"]:
            errors.append(f"capacity:{agent_id}")
        if len(path) != len(starts):
            errors.append(f"schedule_length:{agent_id}")
        previous_end, position = agent.availability, (agent.x, agent.y, agent.z)
        for task_id, start in zip(path, starts):
            if task_id not in by_task:
                errors.append(f"unknown_task:{task_id}")
                continue
            task = by_task[task_id]
            compatible = config["TASK_TYPES"][task.task_type] in config["COMPATIBILITY"][
                config["AGENT_TYPES"][agent.agent_type]]
            if not compatible:
                errors.append(f"incompatible:{agent_id}:{task_id}")
            target = (task.x, task.y, task.z)
            arrival = previous_end + math.dist(position, target) / agent.nom_velocity
            if not math.isfinite(start):
                errors.append(f"nonfinite_start:{task_id}")
            elif not task.start_time - 1e-7 <= start <= task.end_time + 1e-7:
                errors.append(f"time_window:{task_id}")
            if start + 1e-7 < arrival:
                errors.append(f"travel_time:{task_id}")
            if math.isfinite(start):
                score += task.task_value * math.exp(-task.discount * (start - task.start_time))
            previous_end, position = start + task.duration, target
    assigned = set(counts) & set(by_task)
    return {"valid": not errors, "complete": assigned == set(by_task),
            "errors": errors, "unassigned_task_ids": sorted(set(by_task) - assigned),
            "assigned_tasks": len(assigned), "duplicate_tasks": sum(c > 1 for c in counts.values()),
            "assigned_task_rate": len(assigned) / len(tasks) if tasks else 0.0,
            "assignment_score": score if not errors else None}


def assess_consensus(solver):
    """Check agreement, path ownership AND recorded winning bids against path bids."""
    errors = []
    winners, bids = solver.winners_list, solver.winner_bid_list
    if any(row != winners[0] for row in winners):
        errors.append("winner_disagreement")
    if any(not math.isclose(float(value), float(bids[0][j]), abs_tol=1e-5, rel_tol=0)
           for row in bids for j, value in enumerate(row)):
        errors.append("bid_disagreement")
    owners = {t.task_id: [] for t in solver.TaskList}
    path_bids = {}
    for agent, path, scores in zip(solver.AgentList, solver.path_list, solver.scores_list):
        if len(path) != len(scores):
            errors.append("path_bid_length")
        for task_id, score in zip(path, scores):
            if task_id not in owners:
                errors.append(f"unknown_path_task:{task_id}")
                continue
            owners[task_id].append(agent.agent_id)
            path_bids[task_id] = score
    for j, task in enumerate(solver.TaskList):
        task_owners = owners[task.task_id]
        expected = task_owners[0] if len(task_owners) == 1 else -1
        expected_bid = path_bids[task.task_id] if len(task_owners) == 1 else -1
        if len(task_owners) > 1 or any(row[j] != expected for row in winners):
            errors.append(f"winner_path_mismatch:{task.task_id}")
        if any(not math.isclose(float(row[j]), float(expected_bid), abs_tol=1e-5, rel_tol=0)
               for row in bids):
            errors.append(f"bid_path_mismatch:{task.task_id}")
    return {"valid": not errors, "errors": errors}


class AuctionRoundLimit(RuntimeError):
    pass


class AuditedCBBA(CBBA):
    """External watchdog only; does not change bidding or the legacy stopping rule."""
    def __init__(self, config):
        super().__init__(config)
        self.audit_round_limit = config["EXPERIMENT"]["AUCTION_ROUND_LIMIT"]

    def communicate(self, time_mat, iter_idx):
        if iter_idx > self.audit_round_limit:
            raise AuctionRoundLimit(f"Exceeded {self.audit_round_limit} rounds")
        return super().communicate(time_mat, iter_idx)


def run_auction(config, agents, tasks, world, owner, participant_ids, task_ids,
                scope, event_triggered=True, affected_ids=(), radius=None):
    """Same remapping, scope and eligibility policy as the existing spatial helper."""
    started = time.perf_counter()
    participant_ids, task_ids = sorted(participant_ids), sorted(task_ids)
    if not participant_ids or not task_ids:
        raise ValueError("An actual auction needs nonempty participants and tasks")
    by_agent = {a.agent_id: a for a in agents}
    by_task = {t.task_id: t for t in tasks}
    local_id = {a: i for i, a in enumerate(participant_ids)}
    local_agents = [copy.deepcopy(by_agent[a]) for a in participant_ids]
    for i, agent in enumerate(local_agents):
        agent.agent_id = i
    local_tasks = [copy.deepcopy(by_task[t]) for t in task_ids]
    incumbents = {t: local_id[a] for t, a in owner.items() if t in task_ids and a in local_id}
    affected = set(affected_ids)
    eligibility = None if radius is None else [
        [t.task_id not in affected or math.dist((a.x, a.y), (t.x, t.y)) <= radius
         for t in local_tasks] for a in local_agents]
    solver = AuditedCBBA(config)
    exception = ""
    try:
        paths, times = solver.solve(
            local_agents, local_tasks, copy.deepcopy(world),
            max_depth=config["EXPERIMENT"]["MAX_DEPTH"], time_window_flag=True,
            event_triggered=event_triggered, incumbent_owners=incumbents,
            incumbency_bonus=config["EXPERIMENT"]["INCUMBENCY_BONUS"],
            agent_task_eligibility=eligibility)
    except Exception as exc:
        exception = f"{type(exc).__name__}: {exc}"
        paths, times = [[] for _ in local_agents], [[] for _ in local_agents]
    runtime = time.perf_counter() - started
    mapped_paths = dict(zip(participant_ids, paths))
    mapped_times = dict(zip(participant_ids, times))
    schedule = validate_schedule(config, agents, [by_task[t] for t in task_ids], mapped_paths, mapped_times)
    consensus = assess_consensus(solver) if not exception else {"valid": False, "errors": [exception]}
    errors = list(schedule["errors"]) + list(consensus["errors"])
    if solver.total_broadcasts != sum(solver.broadcast_history):
        errors.append("broadcast_accounting")
    rounds = len(solver.broadcast_history)
    if not exception and solver.iterations != rounds:
        errors.append("round_accounting")
    if eligibility is not None:
        for a, path in zip(local_agents, paths):
            for task_id in path:
                if not eligibility[a.agent_id][task_ids.index(task_id)]:
                    errors.append(f"radius_eligibility:{a.agent_id}:{task_id}")
    return {"scope": scope, "participant_ids": participant_ids, "task_ids": task_ids,
            "affected_task_ids": sorted(affected), "radius": radius,
            "eligibility": eligibility, "event_triggered": event_triggered,
            "paths": mapped_paths, "times": mapped_times,
            "broadcasts": solver.total_broadcasts, "rounds": rounds,
            "runtime_seconds": runtime, "termination_reason": solver.termination_reason,
            "exception": exception, "valid": not errors, "complete": schedule["complete"],
            "errors": errors, "schedule_check": schedule, "consensus_check": consensus,
            "broadcast_history": solver.broadcast_history,
            "broadcast_agents_history": [[participant_ids[i] for i in row]
                                         for row in solver.broadcast_agents_history],
            "winner_id_mapping": participant_ids, "winner_records_use_local_ids": True,
            "winners": solver.winners_list, "winning_bids": solver.winner_bid_list,
            "path_bids": solver.scores_list,
            "partial_internal_paths_on_exception": solver.path_list if exception else None}


@dataclass
class PreparedTrial:
    seed: int
    config: dict
    agents: list
    tasks: list
    world: WorldInfo
    owner: dict
    failed_agent: int | None
    initial_paths: dict
    initial_times: dict
    initial_auction: dict


def trial_snapshot(trial):
    return {"seed": trial.seed, "config": trial.config,
            "agents": [asdict(a) for a in trial.agents],
            "tasks": [asdict(t) for t in trial.tasks], "world": asdict(trial.world),
            "owner": trial.owner, "failed_agent": trial.failed_agent,
            "initial_paths": trial.initial_paths, "initial_times": trial.initial_times}


def prepare_trial(num_robots, seed, config=None):
    config, agents, tasks, world = build_scenario(num_robots, seed, config)
    initial = run_auction(config, agents, tasks, world, {}, [a.agent_id for a in agents],
                          [t.task_id for t in tasks], "initial", event_triggered=True)
    owner = {t: a for a, path in initial["paths"].items() for t in path}
    working = sorted(a for a, path in initial["paths"].items() if path)
    # Independent RNG: failure choice does not depend on method or solver RNG use.
    rng = random.Random(config["EXPERIMENT"]["FAILURE_SEED_OFFSET"] + seed)
    failed = rng.choice(working) if working else None
    return PreparedTrial(seed, config, agents, tasks, world, owner, failed,
                         initial["paths"], initial["times"], initial)


def local_candidates(trial, affected):
    radius = trial.config["EXPERIMENT"]["LOCAL_RADIUS"]
    by_task = {t.task_id: t for t in trial.tasks}
    candidates = {}
    for task_id in sorted(affected):
        task = by_task[task_id]
        candidates[task_id] = sorted(a.agent_id for a in trial.agents
            if a.agent_id != trial.failed_agent
            and trial.config["TASK_TYPES"][task.task_type] in trial.config["COMPATIBILITY"][
                trial.config["AGENT_TYPES"][a.agent_type]]
            and math.dist((a.x, a.y), (task.x, task.y)) <= radius)
    return candidates


def run_method(prepared, method):
    if method not in METHODS:
        raise ValueError(f"Unknown method: {method}")
    trial = copy.deepcopy(prepared)
    fingerprint = digest(trial_snapshot(trial))
    started = time.perf_counter()
    active = sorted(a.agent_id for a in trial.agents if a.agent_id != trial.failed_agent)
    affected = sorted(t for t, a in trial.owner.items() if a == trial.failed_agent)
    episodes, candidates, reason = [], {}, ""
    paths, times = {}, {}
    local_success = None if method != METHODS[2] else False
    initial_ok = trial.initial_auction["valid"] and trial.initial_auction["complete"] and affected
    if initial_ok:
        if method == METHODS[2]:
            if len(affected) > trial.config["EXPERIMENT"]["MAX_LOCAL_AFFECTED"]:
                reason = "too_many_affected_tasks"
            else:
                candidates = local_candidates(trial, affected)
                if any(not value for value in candidates.values()):
                    reason = "no_nearby_capable_robot"
                else:
                    participants = sorted({a for values in candidates.values() for a in values})
                    scoped = set(affected) | {t for t, a in trial.owner.items() if a in participants}
                    local = run_auction(trial.config, trial.agents, trial.tasks, trial.world,
                        trial.owner, participants, scoped, "local", affected_ids=affected,
                        radius=trial.config["EXPERIMENT"]["LOCAL_RADIUS"])
                    episodes.append(local)
                    if local["valid"] and local["complete"]:
                        paths = {a: copy.deepcopy(trial.initial_paths[a]) for a in active}
                        times = {a: copy.deepcopy(trial.initial_times[a]) for a in active}
                        paths.update(local["paths"])
                        times.update(local["times"])
                        local_success = True
                    else:
                        reason = ("local_capacity_or_schedule_infeasible" if local["valid"]
                                  else "local_invalid_or_solver_error")
        if not local_success:
            global_result = run_auction(trial.config, trial.agents, trial.tasks, trial.world,
                trial.owner, active, [t.task_id for t in trial.tasks], "global",
                event_triggered=method != METHODS[0])
            episodes.append(global_result)
            paths, times = global_result["paths"], global_result["times"]
    final_check = validate_schedule(trial.config, trial.agents, trial.tasks,
                                    paths, times, trial.failed_agent)
    unchanged = True
    if local_success:
        outsiders = set(active) - set(episodes[0]["participant_ids"])
        unchanged = all(paths[a] == trial.initial_paths[a] and times[a] == trial.initial_times[a]
                        for a in outsiders)
        if not unchanged:
            final_check["errors"].append("nonparticipant_schedule_changed")
            final_check["valid"] = False
    runtime = time.perf_counter() - started
    local_episodes = [e for e in episodes if e["scope"] == "local"]
    global_episodes = [e for e in episodes if e["scope"] == "global"]
    total = lambda group, key: sum(e[key] for e in group)
    broadcasts = total(episodes, "broadcasts")
    valid = bool(initial_ok and final_check["valid"] and episodes and episodes[-1]["valid"])
    diagnostic_errors = [err for e in episodes for err in e["errors"]]
    status = ("initial_invalid_or_incomplete" if not initial_ok else
              "invalid" if not valid else "incomplete" if not final_check["complete"] else
              "recovered_with_diagnostics" if diagnostic_errors else "ok")
    row = {"seed": trial.seed, "num_robots": len(trial.agents), "num_tasks": len(trial.tasks),
           "method": method, "failed_agent": trial.failed_agent, "affected_tasks": len(affected),
           "input_fingerprint": fingerprint, "post_failure_broadcasts": broadcasts,
           "broadcasts_per_affected_task": broadcasts / len(affected) if affected else None,
           "runtime_seconds": runtime, "consensus_rounds": total(episodes, "rounds"),
           "assigned_task_rate": final_check["assigned_task_rate"],
           "assignment_score": final_check["assignment_score"],
           "local_recovery_success": local_success, "fallback_reason": reason,
           "auction_scope": "local" if local_success else "global" if episodes else "none",
           "local_broadcasts": total(local_episodes, "broadcasts"),
           "global_broadcasts": total(global_episodes, "broadcasts"),
           "local_rounds": total(local_episodes, "rounds"),
           "global_rounds": total(global_episodes, "rounds"),
           "local_runtime_seconds": total(local_episodes, "runtime_seconds"),
           "global_runtime_seconds": total(global_episodes, "runtime_seconds"),
           "auction_runtime_seconds": total(episodes, "runtime_seconds"),
           "controller_validation_seconds": runtime - total(episodes, "runtime_seconds"),
           "local_attempted": bool(local_episodes), "post_failure_auctions": len(episodes),
           "initial_broadcasts": trial.initial_auction["broadcasts"],
           "initial_rounds": trial.initial_auction["rounds"],
           "assigned_tasks": final_check["assigned_tasks"], "duplicate_tasks": final_check["duplicate_tasks"],
           "valid_assignment": valid, "complete": final_check["complete"],
           "nonparticipants_unchanged": unchanged, "diagnostic_error_count": len(diagnostic_errors),
           "status": status}
    assert digest(trial_snapshot(trial)) == fingerprint, "Method mutated paired input"
    return row, {"input_fingerprint": fingerprint, "method": method, "episodes": episodes,
                 "candidates_by_affected_task": candidates, "final_paths": paths,
                 "final_times": times, "final_check": final_check, "row": row}


def run_paired_trial(num_robots, seed, config=None):
    prepared = prepare_trial(num_robots, seed, config)
    fingerprint = digest(trial_snapshot(prepared))
    results = [run_method(prepared, method) for method in METHODS]
    assert all(row["input_fingerprint"] == fingerprint for row, _ in results)
    assert digest(trial_snapshot(prepared)) == fingerprint
    return prepared, [r for r, _ in results], [d for _, d in results]


def summarize(rows):
    summary = []
    metrics = ["post_failure_broadcasts", "broadcasts_per_affected_task", "runtime_seconds",
               "consensus_rounds", "assigned_task_rate", "assignment_score"]
    for scale in sorted({r["num_robots"] for r in rows}):
        for method in METHODS:
            sample = [r for r in rows if r["num_robots"] == scale and r["method"] == method]
            item = {"num_robots": scale, "method": method, "runs": len(sample),
                    "valid_complete_runs": sum(r["valid_assignment"] and r["complete"] for r in sample),
                    "issue_runs": sum(r["status"] != "ok" for r in sample),
                    "local_recovery_rate": (statistics.mean(r["local_recovery_success"] for r in sample)
                                            if method == METHODS[2] else None)}
            for metric in metrics:
                values = [r[metric] for r in sample if r[metric] is not None]
                item[f"{metric}_available"] = len(values)
                item[f"{metric}_mean"] = statistics.mean(values) if values else None
                item[f"{metric}_std"] = statistics.stdev(values) if len(values) > 1 else 0.0 if values else None
            item["fallback_counts"] = dict(Counter(r["fallback_reason"] for r in sample if r["fallback_reason"]))
            summary.append(item)
    return summary


def analyze(rows, details):
    pairs = {(r["num_robots"], r["seed"]) for r in rows}
    pairing = all(len(group := [r for r in rows if (r["num_robots"], r["seed"]) == pair]) == 3
                  and {r["method"] for r in group} == set(METHODS)
                  and len({r["input_fingerprint"] for r in group}) == 1 for pair in pairs)
    accounting = all(r["post_failure_broadcasts"] == r["local_broadcasts"] + r["global_broadcasts"]
                     and r["consensus_rounds"] == r["local_rounds"] + r["global_rounds"]
                     and math.isclose(r["auction_runtime_seconds"], r["local_runtime_seconds"] + r["global_runtime_seconds"])
                     for r in rows)
    control_differences = []
    for pair in sorted(pairs):
        controls = [d for d in details if (d["row"]["num_robots"], d["row"]["seed"]) == pair
                    and d["method"] in METHODS[:2]]
        if len(controls) == 2 and (controls[0]["final_paths"] != controls[1]["final_paths"]
                                  or controls[0]["final_times"] != controls[1]["final_times"]):
            control_differences.append(pair)
    radius_checks = []
    for detail in details:
        for episode in detail["episodes"]:
            if episode["scope"] == "local":
                candidates = detail["candidates_by_affected_task"]
                radius_checks.append(episode["radius"] == 40 and all(
                    a in candidates[t] for a, path in episode["paths"].items()
                    for t in path if t in episode["affected_task_ids"]))
    slow = []
    for scale in sorted({r["num_robots"] for r in rows}):
        group = [r for r in rows if r["num_robots"] == scale]
        median = statistics.median(r["runtime_seconds"] for r in group)
        slow.extend({"num_robots": scale, "seed": r["seed"], "method": r["method"],
                     "runtime_seconds": r["runtime_seconds"]} for r in group
                    if r["runtime_seconds"] > max(5.0, 10 * median))
    return {"rows": len(rows), "paired_trials": len(pairs), "pairing_valid": pairing,
            "cost_accounting_valid": accounting, "local_radius_valid": all(radius_checks),
            "valid_complete_rows": sum(r["valid_assignment"] and r["complete"] for r in rows),
            "unassigned_rows": sum(r["assigned_task_rate"] < 1 for r in rows),
            "duplicate_rows": sum(r["duplicate_tasks"] > 0 for r in rows),
            "diagnostic_rows": sum(r["diagnostic_error_count"] > 0 for r in rows),
            "global_control_schedule_differences": control_differences,
            "slow_runtime_rule": "runtime > max(5 seconds, 10 x same-scale median)",
            "slow_runs": slow, "non_ok_rows": [r for r in rows if r["status"] != "ok"]}


def write_csv(path, rows):
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: "N/A" if v is None else canonical(v) if isinstance(v, (dict, list)) else v
                             for k, v in row.items()})


def write_outputs(output, rows, details, summary, analysis, mode, manifest):
    write_csv(output / "trials.csv", rows)
    write_csv(output / "summary.csv", summary)
    for name, value in (("analysis.json", analysis), ("manifest.json", manifest)):
        (output / name).write_text(json.dumps(value, indent=2, default=json_default, allow_nan=False), encoding="utf-8")
    metrics = [("post_failure_broadcasts", "Post-failure broadcasts"),
               ("broadcasts_per_affected_task", "Broadcasts per affected task"),
               ("runtime_seconds", "Runtime (seconds)"), ("consensus_rounds", "Consensus rounds"),
               ("assigned_task_rate", "Assigned-task rate"), ("assignment_score", "Assignment score")]
    fig, axes = plt.subplots(2, 3, figsize=(15, 8), constrained_layout=True)
    for ax, (metric, label) in zip(axes.flat, metrics):
        for method in METHODS:
            group = [s for s in summary if s["method"] == method]
            ax.errorbar([s["num_robots"] for s in group],
                        [float("nan") if s[f"{metric}_mean"] is None else s[f"{metric}_mean"] for s in group],
                        yerr=[0 if s[f"{metric}_std"] is None else s[f"{metric}_std"] for s in group],
                        marker="o", capsize=3, label=method)
        ax.set(xlabel="Number of robots", ylabel=label, xticks=sorted({r["num_robots"] for r in rows}))
        if metric == "assigned_task_rate":
            ax.set_ylim(0, 1.05)
        ax.grid(alpha=.25)
    axes[0, 0].legend(fontsize=8)
    fig.suptitle(f"Homogeneous — {mode}; mean ± sample SD (descriptive)")
    fig.savefig(output / "metrics.png", dpi=180)
    plt.close(fig)
    local = [s for s in summary if s["method"] == METHODS[2]]
    fig, ax = plt.subplots(figsize=(6, 4), constrained_layout=True)
    ax.plot([s["num_robots"] for s in local], [s["local_recovery_rate"] for s in local], "o-")
    ax.set(xlabel="Number of robots", ylabel="Local recovery rate", ylim=(0, 1.05),
           xticks=[s["num_robots"] for s in local], title=f"Distance-Scoped ED-CBBA — {mode}")
    ax.grid(alpha=.25)
    fig.savefig(output / "local_recovery.png", dpi=180)
    plt.close(fig)
    lines = ["# Experiment 1 — Homogeneous", "", f"Run type: **{mode}**.", "",
        "This run is descriptive validation, not a final experimental conclusion."
        if mode != "formal" else "This report describes the configured 30-seed paired experiment.", "",
        "## Protocol", "",
        "Each scale/seed generates one mission: robot positions followed by task positions, "
        "with independent uniform x/y coordinates in [0,100] m from Python Random(seed). "
        "One initial ED-CBBA allocation is shared by all methods. A separate Random(100000+seed) "
        "selects one robot from sorted assigned robot IDs to fail before execution. "
        "Methods receive deep copies; input fingerprints and initial solver records are retained.", "",
        "There is one fully compatible robot/task type. The scales are 6/18, 12/36 and 24/72 "
        "robots/tasks. Capacity is 4, speed 5 m/s, task value 100, duration 8 s and start window "
        "[0,240] s. Discount 0.02 and incumbent bid bonus 10% are explicit additional settings, "
        "matching the existing spatial experiment, rather than parameters mandated by the assignment.", "",
        "Standard CBBA and ED-CBBA globally re-auction all tasks among survivors. The distance "
        "method uses ED-CBBA and a 40 m inclusive affected-task eligibility rule. Candidates are "
        "the union across affected tasks; their existing tasks enter the local auction. Outsiders "
        "retain both paths and planned times. More than four affected tasks or a task without a "
        "candidate skips local bidding. An incomplete/invalid local result triggers global ED-CBBA. "
        "A failed greedy local attempt is not a proof that no feasible local schedule exists.", "",
        "## Metrics and audit", "",
        "Post-failure broadcasts count sending robots once per round, summed across actual local "
        "and global auctions. Broadcasts per affected task divide that sum by the failed robot's "
        "original task count. Skipped auctions have zero cost. Consensus rounds are the sum of "
        "actual solver communication rounds, including the legacy participant-count-dependent "
        "quiet tail, not a certified convergence time. Per-auction rounds, termination reason, "
        "sender histories, paths, winners and bids are retained in diagnostics.", "",
        "Runtime uses perf_counter for the entire post-failure controller through final validation. "
        "It includes scope selection, auction setup/solve and validation; it excludes common initial "
        "allocation, input copy/fingerprint and export/plotting. Per-auction runtime separately "
        "covers setup/solve; local/global runtime sums and controller/validation overhead are retained. "
        "The fixed method order is recorded; timing can be affected by cache/system noise.", "",
        "Assigned-task rate is final unique assigned tasks divided by all original tasks. "
        "Assignment score is sum(100 * exp(-0.02 * (planned_start - release))) over assigned tasks, "
        "without incumbent bonuses. Local recovery rate is successful local recoveries divided by "
        "all distance-method trials; global controls are N/A. Invalid/incomplete rows are retained. "
        "Summary fields report available-value counts; unavailable scores are N/A, not zero.", "",
        "Independent checks cover uniqueness, compatibility, capacity, travel, start windows, "
        "failed-robot exclusion, per-task radius eligibility, unchanged outsiders, winner/bid "
        "agreement and agreement with owning paths and recorded path bids. An external 10000-round "
        "watchdog records an error rather than claiming convergence; it does not change normal bidding.", "",
        "## Results", "",
        "| Robots | Method | Runs | Valid + complete | Broadcasts | Broadcasts / affected | Runtime s | Rounds | Assigned rate | Score | Local recovery |",
        "| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for s in summary:
        def fmt(key, precision=3):
            return "N/A" if s[key] is None else f"{s[key]:.{precision}f}"
        lines.append(f"| {s['num_robots']} | {s['method']} | {s['runs']} | {s['valid_complete_runs']} | "
                     f"{fmt('post_failure_broadcasts_mean')} | {fmt('broadcasts_per_affected_task_mean')} | "
                     f"{fmt('runtime_seconds_mean', 6)} | {fmt('consensus_rounds_mean')} | "
                     f"{fmt('assigned_task_rate_mean')} | {fmt('assignment_score_mean')} | "
                     f"{fmt('local_recovery_rate')} |")
    lines += ["", "Values are arithmetic means; figures show sample standard deviations, not confidence intervals.", "",
              "![Six metrics](metrics.png)", "", "![Local recovery](local_recovery.png)", "",
              "### Fallback audit", ""]
    for s in local:
        lines.append(f"- {s['num_robots']} robots: {json.dumps(s['fallback_counts'])}")
    lines += ["", "```json", json.dumps(analysis, indent=2, default=json_default), "```", "",
        "## Limits and reproduction", "",
        "This is static replanning with a complete communication graph inside each auction. "
        "40 m restricts bids, not radio range. Failure detection, heartbeat and scope-coordination "
        "traffic are excluded. Small samples do not establish statistical superiority. The existing "
        "legacy quiet stopping rule is retained; final consistency checks are necessary. "
        "No failed sample is resampled or deleted. Initial allocation failures remain explicit rows. "
        "Rows with recovered diagnostics also remain flagged and cause a nonzero CLI exit.", "",
        "Run from the repository root with the robots/seeds in manifest.json and a fresh output directory. "
        "The default CLI uses seeds 0,1,2; the full experiment requires --full and a distinct directory. "
        "See manifest.json for exact config, environment, source hashes and timing definitions; "
        "trials.csv and summary.csv retain unrounded values. paired_inputs/ and diagnostics/ "
        "retain each mission, common initial allocation and every post-failure auction.", ""]
    (output / "report.md").write_text("\n".join(lines), encoding="utf-8")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path)
    parser.add_argument("--robots", type=int, nargs="+", default=[6, 12, 24])
    parser.add_argument("--seeds", type=int, nargs="+", default=[0, 1, 2])
    parser.add_argument("--full", action="store_true", help="Explicitly opt into all 270 method results")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "outputs/homogeneous_smoke")
    args = parser.parse_args(argv)
    config_path = (args.config or ROOT / "config_homogeneous_scenario.json").resolve()
    config = load_config(config_path)
    if args.full:
        if args.output_dir == ROOT / "outputs/homogeneous_smoke":
            parser.error("--full requires a distinct --output-dir")
        args.robots, args.seeds = [6, 12, 24], list(range(30))
    if len(set(args.robots)) != len(args.robots) or len(set(args.seeds)) != len(args.seeds):
        parser.error("Duplicate scales/seeds are not allowed")
    if any(str(n) not in config["EXPERIMENT"]["SCALES"] for n in args.robots) or any(
            seed not in config["EXPERIMENT"]["SEEDS"] for seed in args.seeds):
        parser.error("Invalid scale or seed")
    count = len(args.robots) * len(args.seeds) * len(METHODS)
    if count >= 270 and not args.full:
        parser.error("Use --full to explicitly request the full experiment")
    output = args.output_dir.resolve()
    if output.exists() and any(output.iterdir()):
        parser.error("Output directory must be empty; never overwrite an existing run")
    output.mkdir(parents=True, exist_ok=True)
    (output / "paired_inputs").mkdir()
    (output / "diagnostics").mkdir()
    mode = "formal" if args.full else "smoke-test (not final conclusions)"
    import numpy
    manifest = {"mode": mode, "config": config, "robots": args.robots, "seeds": args.seeds,
                "expected_method_rows": count, "python": sys.version, "platform": platform.platform(),
                "numpy": numpy.__version__, "matplotlib": matplotlib.__version__,
                "config_path": str(config_path),
                "config_sha256": hashlib.sha256(config_path.read_bytes()).hexdigest(),
                "position_rule": "random.Random(seed); independent U(0,100) x/y; agents then tasks",
                "failure_rule": "Random(100000+seed).choice(sorted assigned robot IDs)",
                "runtime_definition": "perf_counter; post-failure scope selection, auctions and validation; excludes input deepcopy/fingerprinting, initial allocation and export",
                "round_definition": "Actual solver communication rounds, including legacy quiet tail; sum local and global",
                "communication_model": "fully connected inside each auction; one sender = one broadcast; excludes detection/coordination/heartbeats",
                "method_order": list(METHODS),
                "source_sha256": {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                                  for p in [ROOT / "lib/CBBA.py", Path(__file__), ROOT / "config_homogeneous_scenario.json"]}}
    try:
        manifest["git_commit"] = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    except (OSError, subprocess.CalledProcessError):
        manifest["git_commit"] = None
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    rows, details = [], []
    for scale in args.robots:
        for seed in args.seeds:
            prepared, trial_rows, trial_details = run_paired_trial(scale, seed, config)
            payload = {"snapshot": trial_snapshot(prepared), "initial_auction": prepared.initial_auction,
                       "input_fingerprint": digest(trial_snapshot(prepared))}
            (output / f"paired_inputs/n{scale}_seed{seed}.json").write_text(
                json.dumps(payload, indent=2, default=json_default, allow_nan=False), encoding="utf-8")
            for index, detail in enumerate(trial_details):
                (output / f"diagnostics/n{scale}_seed{seed}_method{index}.json").write_text(
                    json.dumps(detail, indent=2, default=json_default, allow_nan=False), encoding="utf-8")
            rows.extend(trial_rows)
            details.extend(trial_details)
            # Checkpoint completed trials, including invalid/incomplete results; never resample.
            write_csv(output / "trials.csv", rows)
            print(f"n={scale} seed={seed}: " + "; ".join(
                f"{r['method']}: {r['status']}, {r['post_failure_broadcasts']} broadcasts, {r['consensus_rounds']} rounds"
                for r in trial_rows), flush=True)
    summary, analysis = summarize(rows), analyze(rows, details)
    write_outputs(output, rows, details, summary, analysis, mode, manifest)
    print(json.dumps(analysis, indent=2, default=json_default))
    print(f"Saved {len(rows)} method rows to {output}")
    return 0 if all(r["status"] == "ok" for r in rows) and analysis["pairing_valid"] and analysis["cost_accounting_valid"] and analysis["local_radius_valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
