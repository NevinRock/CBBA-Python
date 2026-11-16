#!/usr/bin/env python3
"""Paired packet-erasure experiment; writes CSV, Markdown, and a PNG figure."""

import argparse
import copy
import csv
import json
import math
import platform
import statistics
import sys
from collections import Counter
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from test.run_ed_cbba_example import CBBA, make_scenario

METHODS = ("CBBA", "ED-CBBA", "ED-CBBA + refresh")
LOSS_RATES = (0.0, 0.05, 0.10, 0.20, 0.30)


def assess_assignment(solver):
    """Check final local beliefs against actual paths, without repairing them."""
    owners = {task.task_id: [] for task in solver.TaskList}
    for agent, path in zip(solver.AgentList, solver.path_list):
        for task_id in path:
            owners[task_id].append(agent.agent_id)
    counts = Counter(task for path in solver.path_list for task in path)
    duplicates = sum(count > 1 for count in counts.values())
    covered = sum(bool(value) for value in owners.values())
    winners_agree = all(row == solver.winners_list[0]
                        for row in solver.winners_list)
    bids_agree = all(np.allclose(row, solver.winner_bid_list[0], rtol=0, atol=1e-5)
                     for row in solver.winner_bid_list)
    paths_consistent = all(
        row[j] == (owners[task.task_id][0] if len(owners[task.task_id]) == 1 else -1)
        for row in solver.winners_list for j, task in enumerate(solver.TaskList))
    valid = (duplicates == 0 and winners_agree and bids_agree and paths_consistent
             and all(len(path) <= solver.max_depth for path in solver.path_list))
    return {"covered_tasks": covered, "duplicate_tasks": duplicates,
            "winners_agree": winners_agree, "bids_agree": bids_agree,
            "paths_consistent": paths_consistent,
            "valid_assignment": valid,
            "success": valid and covered == solver.num_tasks}


def run_trial(seed, loss_probability, config, rounds=100, refresh_interval=5):
    world, agents, tasks, graph = make_scenario(seed=seed)
    rows = []
    solvers = []
    for method in METHODS:
        solver = CBBA(config)
        solver.solve(copy.deepcopy(agents), copy.deepcopy(tasks), world,
                     max_depth=3, time_window_flag=False,
                     event_triggered=method != "CBBA", communication_graph=graph,
                     packet_loss_probability=loss_probability,
                     communication_seed=100_000 + seed,
                     refresh_interval=refresh_interval if method == METHODS[2] else None,
                     round_budget=rounds)
        rows.append({"seed": seed, "communication_seed": 100_000 + seed,
                     "loss_probability": loss_probability, "method": method,
                     "rounds": solver.iterations, "refresh_interval": refresh_interval
                     if method == METHODS[2] else 0,
                     **assess_assignment(solver),
                     "broadcasts": solver.total_broadcasts,
                     "packet_attempts": solver.total_packet_attempts,
                     "packets_delivered": solver.total_packets_delivered,
                     "packets_dropped": solver.total_packets_dropped})
        solvers.append(solver)
    return rows, solvers


def wilson_interval(successes, n):
    z = 1.96
    denominator = 1 + z * z / n
    centre = (successes / n + z * z / (2 * n)) / denominator
    half = z * math.sqrt(successes / n * (1 - successes / n) / n
                         + z * z / (4 * n * n)) / denominator
    return max(0, centre - half), min(1, centre + half)


def write_results(rows, output, rounds, refresh_interval):
    output.mkdir(parents=True, exist_ok=True)
    with (output / "packet_loss_trials.csv").open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    rates = sorted({row["loss_probability"] for row in rows})
    summary = []
    for rate in rates:
        for method in METHODS:
            group = [r for r in rows if r["loss_probability"] == rate and r["method"] == method]
            n = len(group)
            successes = sum(r["success"] for r in group)
            lo, hi = wilson_interval(successes, n)
            summary.append({"loss_probability": rate, "method": method, "runs": n,
                            "successes": successes, "success_rate": successes / n,
                            "ci_low": lo, "ci_high": hi,
                            "duplicate_runs": sum(r["duplicate_tasks"] > 0 for r in group),
                            "mean_coverage": statistics.mean(r["covered_tasks"] for r in group),
                            "mean_broadcasts": statistics.mean(r["broadcasts"] for r in group),
                            "mean_packets": statistics.mean(r["packet_attempts"] for r in group)})
    lines = ["# Packet loss: fixed-budget CBBA robustness experiment", "",
             "## Method", "",
             f"Each loss rate uses {summary[0]['runs']} paired missions (seeds 0 onward), "
             "10 homogeneous robots, 20 tasks, bundle capacity 3, and a 100 m × 100 m map. "
             "The connected, undirected 10 m-range graph and task generator are reused "
             "from `run_ed_cbba_example.py`. Tasks have no time windows.", "",
             "Each attempted sender-to-neighbour delivery is independently erased with "
             "probability p. This is receiver-specific packet loss: a broadcast can reach "
             "some neighbours and miss others. There is no delay, reordering, ACK, or retry queue. "
             "The ED sender records its state as sent even when delivery fails. A separate seeded "
             "random generator draws every ordered pair every round, including silent senders; "
             "methods therefore share potential erasures at the same round/sender/receiver. "
             "Their realised dropped-packet counts can differ because they send different messages.", "",
             f"All methods run exactly **{rounds} consensus rounds**; the existing quiet stopping "
             f"rule is disabled. Refresh forces every ED agent to broadcast every **{refresh_interval} "
             "rounds**, in addition to change-triggered broadcasts. These are proposed "
             "robustness modifications to evaluate, not an implementation of asynchronous CBBA.", "",
             "Success means all 20 tasks occur in exactly one robot path, capacity is respected, "
             "all robots agree on every winner and bid (absolute bid tolerance 1e-5), and winner "
             "beliefs match path ownership. It is a final-state check, not a convergence-time "
             "measurement or a guarantee that no transient conflicts occurred.", "",
             "One broadcast counts one sending robot; packet attempts count its outgoing graph "
             "edges. Dropped packets still count as attempts. All traffic across the common "
             "round budget is included, even after assignments stabilise. Thus the communication "
             "comparison describes a fixed monitoring horizon, not traffic to a certified stopping time.", "",
             "## Results", "",
             "Success intervals are marginal 95% Wilson intervals across missions.", "",
             "| Loss | Method | Success | 95% interval | Runs with duplicate ownership | Mean covered / 20 | Mean broadcasts | Mean packet attempts |",
             "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for s in summary:
        lines.append(f"| {s['loss_probability']:.0%} | {s['method']} | {s['successes']}/{s['runs']} | "
                     f"{s['ci_low']:.1%}–{s['ci_high']:.1%} | {s['duplicate_runs']} | "
                     f"{s['mean_coverage']:.2f} | {s['mean_broadcasts']:.1f} | {s['mean_packets']:.1f} |")
    lines += ["", "![Packet loss results](packet_loss_comparison.png)", "",
              "## Paired refresh effect", "",
              "Positive differences mean refresh improved final success over unmodified ED-CBBA. "
              "These paired differences are descriptive; the Wilson intervals above quantify "
              "uncertainty in each method's marginal success rate, not in their paired difference.", "",
              "| Loss | Refresh rescued / regressed trials | Success difference (percentage points) |",
              "| --- | ---: | ---: |"]
    for rate in rates:
        event = {r["seed"]: r for r in rows if r["loss_probability"] == rate and r["method"] == METHODS[1]}
        refresh = {r["seed"]: r for r in rows if r["loss_probability"] == rate and r["method"] == METHODS[2]}
        differences = [int(refresh[s]["success"]) - int(event[s]["success"]) for s in event]
        mean = statistics.mean(differences)
        lines.append(f"| {rate:.0%} | {differences.count(1)} / {differences.count(-1)} | "
                     f"{100*mean:.1f} |")
    highest = [s for s in summary if s["loss_probability"] == max(rates)]
    standard, event, refreshed = highest
    lines += ["", f"At the highest tested loss rate ({max(rates):.0%}), standard CBBA succeeded "
              f"in {standard['successes']}/{standard['runs']} missions, plain ED-CBBA in "
              f"{event['successes']}/{event['runs']}, and refreshed ED-CBBA in "
              f"{refreshed['successes']}/{refreshed['runs']}. Refreshed ED-CBBA used "
              f"{refreshed['mean_broadcasts']:.1f} mean broadcasts versus "
              f"{standard['mean_broadcasts']:.1f} for standard CBBA "
              f"({100*(1-refreshed['mean_broadcasts']/standard['mean_broadcasts']):.1f}% fewer), "
              f"but more than plain ED-CBBA ({event['mean_broadcasts']:.1f}). "
              "All counts cover the same fixed horizon."]
    lines += ["", "## Interpretation and limits", "",
              "A dropped state update can leave a neighbour with stale winner information. "
              "Change-triggered transmission alone need not resend an unchanged state. Periodic "
              "refresh creates additional delivery opportunities, at the cost of ongoing traffic. "
              "The tables measure whether that mechanism helps in these trials; they do not "
              "establish eventual convergence for arbitrary packet loss.", "",
              "This is a synchronous, static allocation stress test. It excludes execution, "
              "robot failures, deadlines, bandwidth contention, burst loss, and partitions. "
              "Covered tasks can include conflicting assignments and must be read with success "
              "and duplicate ownership. No optimality or execution-completion claim is made. "
              "The refresh period and round budget are fixed design choices, not tuned optima. "
              "Larger paired samples, multiple horizons, and burst-loss models are follow-up studies.", "",
              "## Reproduction", "", "Run from the repository root:", "", "```powershell",
              f".\\.venv\\Scripts\\python.exe test/run_packet_loss_experiment.py --trials {summary[0]['runs']} "
              f"--rounds {rounds} --refresh-interval {refresh_interval} --loss-rates "
              + " ".join(str(rate) for rate in rates), "```", "",
              "Outputs: `packet_loss_trials.csv`, `packet_loss_summary.md`, and "
              "`packet_loss_comparison.png`. The CSV includes the mission and communication seeds "
              "and attempted, delivered, and dropped packet counts.", "",
              f"Environment: Python {platform.python_version()}, NumPy {np.__version__}, "
              f"Matplotlib {matplotlib.__version__}; {platform.system()}.", ""]
    (output / "packet_loss_summary.md").write_text("\n".join(lines), encoding="utf-8")
    fig, axes = plt.subplots(1, 3, figsize=(15, 4.5), constrained_layout=True)
    styles = {"CBBA": dict(marker="s", linestyle="--", markersize=8,
                           markerfacecolor="none", zorder=3),
              "ED-CBBA": dict(marker="o", linestyle="-", markersize=6),
              "ED-CBBA + refresh": dict(marker="^", linestyle=":", markersize=6)}
    for method in METHODS:
        group = [s for s in summary if s["method"] == method]
        x = [100 * s["loss_probability"] for s in group]
        y = [100 * s["success_rate"] for s in group]
        axes[0].errorbar(x, y, yerr=[[max(0, value-100*s["ci_low"]) for value, s in zip(y, group)],
                                   [max(0, 100*s["ci_high"]-value) for value, s in zip(y, group)]],
                         capsize=3, label=method, **styles[method])
        axes[1].plot(x, [100*s["duplicate_runs"]/s["runs"] for s in group], label=method, **styles[method])
        axes[2].plot(x, [s["mean_broadcasts"] for s in group], label=method, **styles[method])
    for ax, label in zip(axes, ("Successful final assignments (%)",
                                "Runs with duplicate ownership (%)", "Mean broadcasts")):
        ax.set_xlabel("Per-link packet loss probability (%)")
        ax.set_ylabel(label)
        ax.grid(alpha=.25)
    axes[0].set_ylim(-3, 103)
    axes[1].set_ylim(-3, 103)
    axes[2].legend(fontsize=8)
    fig.suptitle(f"Packet erasures: {summary[0]['runs']} paired missions, {rounds} rounds; refresh every {refresh_interval} rounds")
    fig.savefig(output / "packet_loss_comparison.png", dpi=180)
    plt.close(fig)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trials", type=int, default=30)
    parser.add_argument("--rounds", type=int, default=100)
    parser.add_argument("--refresh-interval", type=int, default=5)
    parser.add_argument("--loss-rates", type=float, nargs="+", default=LOSS_RATES)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "doc")
    args = parser.parse_args()
    if min(args.trials, args.rounds, args.refresh_interval) < 1:
        parser.error("trials, rounds, and refresh interval must be positive")
    if any(not 0 <= p <= 1 for p in args.loss_rates) or len(set(args.loss_rates)) != len(args.loss_rates):
        parser.error("loss rates must be distinct values in [0, 1]")
    with (ROOT / "config_example_03.json").open() as file:
        config = json.load(file)
    rows = []
    for seed in range(args.trials):
        for rate in sorted(args.loss_rates):
            trial_rows, _ = run_trial(seed, rate, config, args.rounds, args.refresh_interval)
            rows.extend(trial_rows)
        print(f"Completed paired mission {seed+1}/{args.trials}", flush=True)
    for summary in write_results(rows, args.output_dir, args.rounds, args.refresh_interval):
        print(f"loss={summary['loss_probability']:.0%} {summary['method']}: "
              f"success={summary['successes']}/{summary['runs']}, "
              f"broadcasts={summary['mean_broadcasts']:.1f}")
    print("Saved results:", args.output_dir.resolve())


if __name__ == "__main__":
    main()
