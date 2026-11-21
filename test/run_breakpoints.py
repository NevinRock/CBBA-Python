#!/usr/bin/env python3
"""Experiment 3B: breaking points of CBBA re-auction after robot failure.

Each sweep pushes ONE stressor step by step on Experiment 3 missions (shared
capabilities, balanced air/ground teams). Per mission: one common initial ED-CBBA
allocation with full communication, then failure(s) and a re-auction under the stressor.
Every method sees the same mission, failed robots, radio range, packet-loss draws and
inform times at each level.

Sweeps
  split         fixed radio range R; a failure can split the survivors into groups
  loss_sparse   packet loss x radio range (1.0x, 1.5x connectivity threshold, full)
  mass_failure  1 robot ... 60% of the team fail at once
  stale_never   only a fraction of survivors ever learn of the failure
  stale_delay   half learn at once, the rest only after d rounds

A run SUCCEEDS when (a) all live robots agree on the winner of every task (consensus),
(b) no task is claimed by two robots, (c) the auction ended by itself (not the round cap),
and (d) no task is left unassigned while a capable robot still has a free slot (time
never binds in these missions, so free slots per type bound the assignable tasks).
"Consistent" means (a)-(c) only.

Outputs per sweep in <out-root>/<sweep>/: runs.csv, errors.jsonl, run_meta.json.
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
import sys
import time
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "lib"))

from test.run_exp3_shared import (CONFIG_PATH, adjacency, auction, build_mission,  # noqa: E402
                                  connect_threshold, evaluate, git_revision, graph_stats,
                                  load_config, reauction, trial_seed)

ALL4 = ("global_cbba", "global_ed", "global_ed_refresh", "scoped_ed")
WARM3 = ("global_cbba", "global_ed", "global_ed_refresh")
LOSSES = (0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6)
SWEEPS = {
    # level order = increasing stress
    "split": dict(levels=["full", 80, 60, 50, 40, 35, 30, 25, 20, 15], methods=ALL4),
    "loss_sparse": dict(levels=[(rf, p) for rf in ("full", 1.5, 1.0) for p in LOSSES], methods=ALL4),
    "mass_failure": dict(levels=["one", 0.1, 0.25, 0.4, 0.5, 0.6], methods=ALL4),
    "stale_never": dict(levels=[1.0, 0.9, 0.75, 0.5, 0.25], methods=WARM3),
    "stale_delay": dict(levels=[1, 2, 5, 10, 20], methods=WARM3),
}
REFRESH_INTERVAL = 5
MAX_ROUNDS = 500

FIELDS = [
    "sweep", "level", "size", "seed", "method", "n_failed", "failed_types", "affected_tasks",
    "comm_range_m", "groups", "graph_diameter", "packet_loss", "informed_fraction",
    "inform_delay", "scope", "fallback_reason", "consensus", "duplicates", "capped",
    "assigned", "n_tasks", "capacity_bound", "avoidable_loss", "unavoidable_loss",
    "consistent", "success", "broadcasts", "broadcasts_to_converge", "rounds",
    "rounds_to_converge", "cpu_s", "score", "termination",
]


def level_label(level):
    if isinstance(level, tuple):
        return f"{level[0]}x/p{level[1]}" if level[0] != "full" else f"full/p{level[1]}"
    return str(level)


def n_groups(points, comm_range):
    if comm_range is None:
        return 1
    graph = adjacency(points, comm_range)
    seen, groups = set(), 0
    for start in range(len(points)):
        if start in seen:
            continue
        groups += 1
        stack = [start]
        seen.add(start)
        while stack:
            u = stack.pop()
            for v in range(len(points)):
                if graph[u][v] and v not in seen:
                    seen.add(v)
                    stack.append(v)
    return groups


def capacity_bound(config, agents, tasks, dead, max_depth):
    """Most tasks the survivors could take: slots per type; shared tasks fill leftovers."""
    air, ground = config["AGENT_TYPES"].index("air"), config["AGENT_TYPES"].index("ground")
    kinds = config["TASK_TYPES"]
    a = sum(1 for x in agents if x.agent_id not in dead and x.agent_type == air) * max_depth
    g = sum(1 for x in agents if x.agent_id not in dead and x.agent_type == ground) * max_depth
    n_air = sum(t.task_type == kinds.index("air_only") for t in tasks)
    n_ground = sum(t.task_type == kinds.index("ground_only") for t in tasks)
    n_shared = sum(t.task_type == kinds.index("shared") for t in tasks)
    ea, eg = min(n_air, a), min(n_ground, g)
    return ea + eg + min(n_shared, a - ea + g - eg)


def stale_reauction(config, agents, tasks, world, init_solver, dead, method, inform_round):
    """Warm-started re-auction: robots keep their beliefs and plans; each robot releases
    the failed robot's tasks only when it learns of the failure (inform_round)."""
    exp = config["EXPERIMENT"]
    n = len(agents)
    warm = dict(winners=init_solver.winners_list, bids=init_solver.winner_bid_list,
                bundles=init_solver.bundle_list, paths=init_solver.path_list,
                times=init_solver.times_list, scores=init_solver.scores_list)
    from CBBA import CBBA
    solver = CBBA(config)
    cpu0, wall0 = time.process_time(), time.perf_counter()
    paths, times = solver.solve(
        copy.deepcopy(agents), copy.deepcopy(tasks), world, max_depth=int(exp["MAX_DEPTH"]),
        time_window_flag=True, event_triggered=(method != "global_cbba"),
        refresh_interval=REFRESH_INTERVAL if method == "global_ed_refresh" else None,
        failed_agents=set(dead), warm_start=copy.deepcopy(warm), inform_round=inform_round,
        max_rounds=MAX_ROUNDS)
    live = [i for i in range(n) if i not in dead]
    converged = solver.last_change_round
    stats = dict(broadcasts=solver.total_broadcasts,
                 broadcasts_to_converge=sum(solver.broadcast_history[:converged]),
                 rounds=solver.iterations, rounds_to_converge=converged,
                 cpu_s=time.process_time() - cpu0, wall_s=time.perf_counter() - wall0,
                 consensus_ok=all(solver.winners_list[i] == solver.winners_list[live[0]] for i in live),
                 termination=solver.termination_reason or "")
    paths = {i: [t for t in paths[i] if t != -1] for i in live}
    times = {i: list(times[i][:len(paths[i])]) for i in live}
    return paths, times, stats


def run_job(args):
    sweep, size, seed, config_path = args
    config = load_config(config_path)
    exp = config["EXPERIMENT"]
    spec = SWEEPS[sweep]
    try:
        agents, tasks, world = build_mission(config, size, seed)
        by_task = {t.task_id: t for t in tasks}
        all_ids = [a.agent_id for a in agents]
        init_paths, init_times, init_stats = auction(
            config, agents, tasks, world, all_ids, {t.task_id for t in tasks}, event_triggered=True)
        records, dup = evaluate(config, agents, tasks, init_paths, init_times)
        if dup:
            raise AssertionError("initial allocation has duplicate claims")
        owner = {t: r["agent"] for t, r in records.items()}
        working = sorted(set(owner.values()))
        rng = random.Random(f"bp-{trial_seed(size, seed)}")
        single = rng.choice(working)
        survivors_order = [a for a in all_ids if a != single]
        rng.shuffle(survivors_order)  # who learns of the failure first (stale sweeps)
        rows = []
        for level in spec["levels"]:
            dead, comm_rule, loss, informed_fraction, delay = {single}, "full", 0.0, "", ""
            inform_round = None
            if sweep == "split":
                comm_rule = "full" if level == "full" else ("fixed", level)
            elif sweep == "loss_sparse":
                factor, loss = level
                comm_rule = "full" if factor == "full" else ("factor", factor)
            elif sweep == "mass_failure":
                k = 1 if level == "one" else max(1, round(level * size))
                dead = set(random.Random(f"mass-{trial_seed(size, seed)}").sample(working, min(k, len(working))))
            elif sweep == "stale_never":
                informed_fraction = level
                k = round(level * len(survivors_order))
                inform_round = {a: (1 if i < k else None) for i, a in enumerate(survivors_order)}
            elif sweep == "stale_delay":
                delay = level
                half = len(survivors_order) // 2
                inform_round = {a: (1 if i < half else level) for i, a in enumerate(survivors_order)}

            survivors = [a for a in agents if a.agent_id not in dead]
            for method in spec["methods"]:
                if sweep.startswith("stale"):
                    paths, times, stats = stale_reauction(
                        config, agents, tasks, world, init_stats["solver"], dead, method, inform_round)
                    info = dict(scope="global", fallback_reason="", comm_range=None)
                else:
                    paths, times, stats, info = reauction(
                        config, agents, tasks, world, owner, sorted(dead), method,
                        copy.deepcopy(init_paths), copy.deepcopy(init_times), comm_rule,
                        refresh_interval=REFRESH_INTERVAL, packet_loss_probability=loss,
                        communication_seed=seed, max_rounds=MAX_ROUNDS)
                new_records, duplicates = evaluate(config, survivors, tasks, paths, times)
                bound = capacity_bound(config, agents, tasks, dead, int(exp["MAX_DEPTH"]))
                avoidable = max(0, bound - len(new_records))
                capped = "max_rounds" in stats["termination"]
                consistent = stats["consensus_ok"] and duplicates == 0 and not capped
                comm_range = info.get("comm_range")
                points = [(a.x, a.y) for a in survivors]
                groups = n_groups(points, comm_range)
                diameter = ""
                if comm_range is not None and groups == 1:
                    diameter = graph_stats(adjacency(points, comm_range))[1]
                score = sum(by_task[t].task_value * math.exp(-by_task[t].discount *
                                                             (r["start"] - by_task[t].start_time))
                            for t, r in new_records.items())
                rows.append(dict(
                    sweep=sweep, level=level_label(level), size=size, seed=seed, method=method,
                    n_failed=len(dead),
                    failed_types=";".join(config["AGENT_TYPES"][agents[a].agent_type] for a in sorted(dead)),
                    affected_tasks=sum(1 for a in owner.values() if a in dead),
                    comm_range_m=round(comm_range, 3) if comm_range is not None else "",
                    groups=groups, graph_diameter=diameter, packet_loss=loss,
                    informed_fraction=informed_fraction, inform_delay=delay,
                    scope=info["scope"], fallback_reason=info["fallback_reason"],
                    consensus=int(stats["consensus_ok"]), duplicates=duplicates, capped=int(capped),
                    assigned=len(new_records), n_tasks=len(tasks), capacity_bound=bound,
                    avoidable_loss=avoidable, unavoidable_loss=len(tasks) - bound,
                    consistent=int(consistent), success=int(consistent and avoidable == 0),
                    broadcasts=stats["broadcasts"],
                    broadcasts_to_converge=stats["broadcasts_to_converge"],
                    rounds=stats["rounds"], rounds_to_converge=stats["rounds_to_converge"],
                    cpu_s=round(stats["cpu_s"], 5), score=round(score, 4),
                    termination=stats["termination"]))
        return dict(key=(sweep, size, seed), rows=rows, error=None)
    except Exception:
        return dict(key=(sweep, size, seed), rows=[], error=traceback.format_exc())


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--sweeps", nargs="+", default=list(SWEEPS), choices=list(SWEEPS))
    parser.add_argument("--sizes", type=int, nargs="+", default=[6, 12, 24])
    parser.add_argument("--seeds", type=int, default=50)
    parser.add_argument("--jobs", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    parser.add_argument("--out-root", type=Path, default=ROOT / "results" / "breakpoints")
    parser.add_argument("--smoke", action="store_true", help="2 seeds; exit non-zero on any error")
    args = parser.parse_args(argv)
    if args.smoke:
        args.seeds = 2

    metas, jobs = {}, []
    for sweep in args.sweeps:
        out = args.out_root / sweep
        out.mkdir(parents=True, exist_ok=True)
        for name in ("runs.csv", "errors.jsonl"):
            (out / name).unlink(missing_ok=True)
        jobs += [(sweep, size, seed, str(CONFIG_PATH)) for size in args.sizes for seed in range(args.seeds)]
        metas[sweep] = dict(sweep=sweep, levels=[level_label(x) for x in SWEEPS[sweep]["levels"]],
                            methods=SWEEPS[sweep]["methods"], sizes=args.sizes, seeds=args.seeds,
                            refresh_interval=REFRESH_INTERVAL, max_rounds=MAX_ROUNDS,
                            started=time.strftime("%Y-%m-%d %H:%M:%S"), host=platform.node(),
                            cpus=os.cpu_count(), jobs=args.jobs, python=platform.python_version(),
                            git=git_revision(), errors=0)
    jobs.sort(key=lambda job: -job[1])
    print(f"{len(jobs)} jobs over {len(args.sweeps)} sweep(s) on {args.jobs} processes", flush=True)
    start = time.perf_counter()
    with mp.get_context("spawn").Pool(args.jobs) as pool:
        for n, result in enumerate(pool.imap_unordered(run_job, jobs), 1):
            sweep, size, seed = result["key"]
            out = args.out_root / sweep
            if result["error"]:
                metas[sweep]["errors"] += 1
                with (out / "errors.jsonl").open("a") as file:
                    file.write(json.dumps(dict(size=size, seed=seed, error=result["error"])) + "\n")
                print(f"[{n}/{len(jobs)}] {sweep} size={size} seed={seed} ERROR", flush=True)
                continue
            path = out / "runs.csv"
            new = not path.exists()
            with path.open("a", newline="") as file:
                writer = csv.DictWriter(file, fieldnames=FIELDS, lineterminator="\n")
                if new:
                    writer.writeheader()
                writer.writerows(result["rows"])
            if n % 25 == 0 or n == len(jobs):
                print(f"[{n}/{len(jobs)}] elapsed={time.perf_counter() - start:.0f}s", flush=True)
    errors = 0
    for sweep, meta in metas.items():
        meta.update(finished=time.strftime("%Y-%m-%d %H:%M:%S"),
                    elapsed_s=round(time.perf_counter() - start, 1))
        errors += meta["errors"]
        (args.out_root / sweep / "run_meta.json").write_text(json.dumps(meta, indent=2, default=str))
    print(json.dumps({s: m["errors"] for s, m in metas.items()}), "errors;",
          f"elapsed {time.perf_counter() - start:.1f}s")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
