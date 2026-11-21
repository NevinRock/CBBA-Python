#!/usr/bin/env python3
"""Regenerate formal statistics, figures and report from immutable raw results.

Does not import or execute the experiment/CBBA. Requires a passing independent
audit and checks raw file hashes before and after analysis.
"""
import argparse
import csv
import hashlib
import json
import math
import statistics
import sys
from collections import Counter
from pathlib import Path
from statistics import NormalDist

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from test.homogeneous_artifacts import evidence_directory

METHODS = ("Standard CBBA", "ED-CBBA", "Distance-Scoped ED-CBBA")
LABELS = {METHODS[0]: "Standard CBBA", METHODS[1]: "Global ED-CBBA", METHODS[2]: "Distance-Scoped ED-CBBA"}
COLORS = {METHODS[0]: "#2474a8", METHODS[1]: "#d67a13", METHODS[2]: "#218c53"}
METRICS = {"post_failure_broadcasts": "Post-failure broadcasts",
           "broadcasts_per_affected_task": "Broadcasts per affected task",
           "runtime_seconds": "Runtime (s)", "consensus_rounds": "Consensus rounds",
           "assigned_task_rate": "Assigned-task rate", "assignment_score": "Assignment score",
           "local_recovery_success": "Local recovery rate"}
SCALES = (6, 12, 24)
COMPARISONS = ((METHODS[1], METHODS[0]), (METHODS[2], METHODS[1]), (METHODS[2], METHODS[0]))
BOOTSTRAP_REPLICATES = 20000
BOOTSTRAP_SEED = 20261120


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False), encoding="utf-8")


def write_csv(path, rows):
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: "N/A" if v is None else v for k, v in row.items()})


def percentile_interval(values):
    lo, hi = np.quantile(values, [.025, .975], method="linear")
    return float(lo), float(hi)


def wilson(successes, n):
    z = NormalDist().inv_cdf(.975)
    denominator = 1 + z * z / n
    centre = (successes / n + z * z / (2 * n)) / denominator
    half = z * math.sqrt(successes / n * (1 - successes / n) / n + z * z / (4 * n * n)) / denominator
    return max(0.0, centre - half), min(1.0, centre + half)


def describe(values, indices=None, proportion=False):
    values = np.asarray(values, dtype=float)
    if not len(values):
        return {k: None for k in ("mean", "std", "median", "minimum", "maximum", "ci95_low", "ci95_high")} | {"n": 0}
    ci = wilson(int(values.sum()), len(values)) if proportion else percentile_interval(values[indices].mean(axis=1))
    return {"n": len(values), "mean": float(values.mean()), "std": float(values.std(ddof=1)),
            "median": float(np.median(values)), "minimum": float(values.min()), "maximum": float(values.max()),
            "ci95_low": ci[0], "ci95_high": ci[1]}


def build_statistics(details):
    rows = {(d["row"]["num_robots"], d["row"]["seed"], d["method"]): d["row"] for d in details}
    summaries, comparisons, per_seed = [], [], []
    for scale in SCALES:
        # One common seed-resampling field preserves every method pair at this scale.
        indices = np.random.default_rng(BOOTSTRAP_SEED + scale).integers(0, 30, (BOOTSTRAP_REPLICATES, 30))
        for method in METHODS:
            for metric in METRICS:
                values = [rows[scale, seed, method][metric] for seed in range(30)
                          if rows[scale, seed, method][metric] is not None]
                item = {"num_robots": scale, "method": method, "metric": metric, "requested_n": 30,
                        "applicable": not (metric == "local_recovery_success" and method != METHODS[2]),
                        **describe(values, indices, proportion=metric == "local_recovery_success"),
                        "interval": "N/A" if not values else "95% Wilson proportion" if metric == "local_recovery_success"
                        else "95% seed-bootstrap percentile mean"}
                summaries.append(item)
        for target, reference in COMPARISONS:
            for metric in list(METRICS)[:-1]:
                a = np.array([rows[scale, seed, target][metric] for seed in range(30)], dtype=float)
                b = np.array([rows[scale, seed, reference][metric] for seed in range(30)], dtype=float)
                delta = a - b
                boot_delta = delta[indices].mean(axis=1)
                ci = percentile_interval(boot_delta)
                relative = 100 * delta / b if np.all(b != 0) else None
                relative_ci = percentile_interval(relative[indices].mean(axis=1)) if relative is not None else (None, None)
                am, bm = a[indices].mean(axis=1), b[indices].mean(axis=1)
                reduction_ci = percentile_interval(100 * (bm - am) / bm) if np.all(bm != 0) else (None, None)
                comparisons.append({"num_robots": scale, "target": target, "reference": reference,
                    "metric": metric, "n_pairs": 30, "target_mean": float(a.mean()), "reference_mean": float(b.mean()),
                    "mean_difference_target_minus_reference": float(delta.mean()),
                    "std_paired_difference": float(delta.std(ddof=1)), "median_paired_difference": float(np.median(delta)),
                    "minimum_paired_difference": float(delta.min()), "maximum_paired_difference": float(delta.max()),
                    "difference_ci95_low": ci[0], "difference_ci95_high": ci[1],
                    "mean_saving_reference_minus_target": float(-delta.mean()),
                    "saving_ci95_low": -ci[1], "saving_ci95_high": -ci[0],
                    "mean_seed_relative_change_percent": None if relative is None else float(relative.mean()),
                    "seed_relative_change_ci95_low": relative_ci[0], "seed_relative_change_ci95_high": relative_ci[1],
                    "reduction_of_means_percent": float(100 * (b.mean() - a.mean()) / b.mean()) if b.mean() else None,
                    "reduction_of_means_ci95_low": reduction_ci[0], "reduction_of_means_ci95_high": reduction_ci[1],
                    "target_lower_count": int((delta < -1e-9).sum()), "ties_count": int((np.abs(delta) <= 1e-9).sum()),
                    "target_higher_count": int((delta > 1e-9).sum()),
                    "interval": "Paired-seed percentile bootstrap, 20000 replicates, unadjusted exploratory 95%"})
                for seed in range(30):
                    per_seed.append({"num_robots": scale, "seed": seed, "target": target, "reference": reference,
                        "metric": metric, "target_value": float(a[seed]), "reference_value": float(b[seed]),
                        "difference_target_minus_reference": float(delta[seed]),
                        "saving_reference_minus_target": float(-delta[seed]),
                        "relative_change_percent": None if relative is None else float(relative[seed])})
    return rows, summaries, comparisons, per_seed


def fallback_statistics(rows, details):
    index = {(d["row"]["num_robots"], d["row"]["seed"], d["method"]): d for d in details}
    summaries, failures = [], []
    for scale in SCALES:
        local = [rows[scale, seed, METHODS[2]] for seed in range(30)]
        reasons = Counter(r["fallback_reason"] for r in local if r["fallback_reason"])
        failed = [r for r in local if r["local_attempted"] and not r["local_recovery_success"]]
        for r in failed:
            base = rows[scale, r["seed"], METHODS[1]]
            d = index[scale, r["seed"], METHODS[2]]
            global_detail = index[scale, r["seed"], METHODS[1]]
            global_episode = d["episodes"][-1]
            control_episode = global_detail["episodes"][0]
            fields = ("participant_ids", "task_ids", "paths", "times", "broadcasts", "rounds", "winners", "winning_bids")
            failures.append({"num_robots": scale, "seed": r["seed"], "reason": r["fallback_reason"],
                "local_broadcasts": r["local_broadcasts"], "global_broadcasts": r["global_broadcasts"],
                "total_broadcasts": r["post_failure_broadcasts"], "global_ed_broadcasts": base["post_failure_broadcasts"],
                "excess_broadcasts_vs_global_ed": r["post_failure_broadcasts"] - base["post_failure_broadcasts"],
                "local_rounds": r["local_rounds"], "global_rounds": r["global_rounds"],
                "local_runtime_seconds": r["local_runtime_seconds"], "global_runtime_seconds": r["global_runtime_seconds"],
                "total_runtime_seconds": r["runtime_seconds"],
                "fallback_equals_standalone_global_ed_except_timing": all(global_episode[k] == control_episode[k] for k in fields)})
        successes = sum(r["local_recovery_success"] for r in local)
        ci = wilson(successes, 30)
        successful_savings = sum(rows[scale, r["seed"], METHODS[1]]["post_failure_broadcasts"] - r["post_failure_broadcasts"]
                                 for r in local if r["local_recovery_success"])
        failed_extra = sum(r["local_broadcasts"] for r in failed)
        net_saving = sum(rows[scale, r["seed"], METHODS[1]]["post_failure_broadcasts"] - r["post_failure_broadcasts"] for r in local)
        assert successful_savings - failed_extra == net_saving
        summaries.append({"num_robots": scale, "n": 30, "local_successes": successes,
            "local_recovery_rate": successes / 30, "local_rate_ci95_low": ci[0], "local_rate_ci95_high": ci[1],
            "local_attempts": sum(r["local_attempted"] for r in local), "failed_local_attempts": len(failed),
            "precheck_no_candidate": reasons["no_nearby_capable_robot"],
            "precheck_too_many_affected": reasons["too_many_affected_tasks"],
            "capacity_or_schedule_fallbacks": reasons["local_capacity_or_schedule_infeasible"],
            "invalid_or_solver_error_fallbacks": reasons["local_invalid_or_solver_error"],
            "failed_attempt_extra_broadcasts_total": sum(r["local_broadcasts"] for r in failed),
            "successful_local_broadcast_savings_total": successful_savings,
            "net_broadcast_savings_vs_global_ed_total": net_saving,
            "failed_attempt_extra_broadcasts_mean_per_trial": sum(r["local_broadcasts"] for r in failed) / 30,
            "failed_attempt_extra_rounds_total": sum(r["local_rounds"] for r in failed),
            "failed_attempt_runtime_seconds_total": sum(r["local_runtime_seconds"] for r in failed),
            "higher_broadcast_cost_than_global_ed": sum(r["post_failure_broadcasts"] > rows[scale,r["seed"],METHODS[1]]["post_failure_broadcasts"] for r in local),
            "tied_broadcast_cost_with_global_ed": sum(r["post_failure_broadcasts"] == rows[scale,r["seed"],METHODS[1]]["post_failure_broadcasts"] for r in local)})
    return summaries, failures


def plot_all(output, summary, comparisons, fallbacks, rows, compact=False):
    figures = output / "figures"
    figures.mkdir(exist_ok=True)
    grouped = {(r["num_robots"], r["method"], r["metric"]): r for r in summary}
    plt.rcParams.update({"font.size": 10, "axes.titlesize": 11, "axes.labelsize": 10,
                         "savefig.dpi": 180, "axes.spines.top": False, "axes.spines.right": False})
    fig, axes = plt.subplots(2, 4, figsize=(18, 8), constrained_layout=True)
    def draw(ax, metric, legend=False):
        methods = (METHODS[2],) if metric == "local_recovery_success" else METHODS
        for method in methods:
            sample = [grouped[n, method, metric] for n in SCALES]
            means = np.array([r["mean"] for r in sample])
            low, high = np.array([r["ci95_low"] for r in sample]), np.array([r["ci95_high"] for r in sample])
            marker, size, style = {METHODS[0]: ("s", 8, "--"), METHODS[1]: ("^", 7, "-."), METHODS[2]: ("o", 5, "-")}[method]
            ax.errorbar(SCALES, means, yerr=[np.maximum(0, means-low), np.maximum(0, high-means)],
                        color=COLORS[method], marker=marker, markersize=size, linestyle=style,
                        markerfacecolor="none" if method != METHODS[2] else COLORS[method],
                        capsize=4, linewidth=1.8, label=LABELS[method])
        ax.set(xlabel="Number of robots", ylabel=METRICS[metric], xticks=SCALES)
        ax.grid(alpha=.22)
        if metric in ("assigned_task_rate", "local_recovery_success"):
            ax.set_ylim(-.02, 1.07)
        if metric == "local_recovery_success":
            ax.text(.03, .96, "Global methods: N/A", transform=ax.transAxes, va="top", fontsize=8)
        if legend:
            ax.legend(fontsize=8)
    for ax, metric in zip(axes.flat, METRICS):
        draw(ax, metric)
    axes.flat[-1].axis("off")
    handles = [plt.Line2D([], [], color=COLORS[m], marker=marker, linestyle=style,
                         markerfacecolor="none" if m != METHODS[2] else COLORS[m], label=LABELS[m])
               for m, marker, style in zip(METHODS, ("s", "^", "o"), ("--", "-.", "-"))]
    axes.flat[-1].legend(handles=handles, loc="upper left", frameon=False)
    axes.flat[-1].text(.02, .60, "30 paired seeds per scale\nMeans with 95% intervals\n\nContinuous metrics: seed-bootstrap mean CI\nLocal recovery: Wilson proportion CI\nIntervals are exploratory and unadjusted\n\nRounds include legacy quiet stopping tail",
                        transform=axes.flat[-1].transAxes, va="top", fontsize=10, linespacing=1.5)
    fig.suptitle("Experiment 1: Homogeneous | all seven required measures", fontsize=16)
    fig.savefig(figures / "all_seven_metrics.png")
    plt.close(fig)
    for metric in (() if compact else METRICS):
        fig, ax = plt.subplots(figsize=(7.6, 4.8), constrained_layout=True)
        draw(ax, metric, legend=True)
        ax.set_title("Homogeneous | " + ("95% Wilson intervals" if metric == "local_recovery_success" else "95% seed-bootstrap mean intervals"))
        fig.savefig(figures / f"{metric}.png")
        plt.close(fig)
    fig, ax = plt.subplots(figsize=(8, 4.8), constrained_layout=True)
    for target, reference in ((METHODS[1], METHODS[0]), (METHODS[2], METHODS[1])):
        sample = [r for r in comparisons if r["target"] == target and r["reference"] == reference and r["metric"] == "post_failure_broadcasts"]
        means = np.array([r["mean_saving_reference_minus_target"] for r in sample])
        low, high = np.array([r["saving_ci95_low"] for r in sample]), np.array([r["saving_ci95_high"] for r in sample])
        ax.errorbar(SCALES, means, yerr=[means-low, high-means], marker="o", capsize=4,
                    color=COLORS[target], label=f"{LABELS[target]} vs {LABELS[reference]}")
    ax.axhline(0, color="#555555", linewidth=1)
    ax.set(xlabel="Number of robots", ylabel="Mean paired broadcast saving (reference - target)", xticks=SCALES,
           title="Paired savings with 95% seed-bootstrap intervals")
    ax.legend(fontsize=8)
    ax.grid(alpha=.22)
    fig.savefig(figures / "paired_broadcast_savings.png")
    plt.close(fig)
    fig, ax = plt.subplots(figsize=(8, 4.8), constrained_layout=True)
    sample = [r for r in comparisons if r["target"] == METHODS[2] and r["reference"] == METHODS[1]
              and r["metric"] == "post_failure_broadcasts"]
    means = np.array([r["mean_saving_reference_minus_target"] for r in sample])
    low, high = np.array([r["saving_ci95_low"] for r in sample]), np.array([r["saving_ci95_high"] for r in sample])
    ax.errorbar(SCALES, means, yerr=[means-low, high-means], marker="o", capsize=5, color=COLORS[METHODS[2]])
    ax.axhline(0, color="#555555", linewidth=1)
    ax.set(xticks=SCALES, xlabel="Number of robots", ylabel="Mean paired broadcast saving (Global ED - Distance ED)",
           title="Extra benefit of spatial scope: paired 95% seed-bootstrap intervals")
    ax.grid(alpha=.22)
    fig.savefig(figures / "paired_local_broadcast_savings.png")
    plt.close(fig)
    fig, ax = plt.subplots(figsize=(8, 4.8), constrained_layout=True)
    x, bottom = np.arange(3), np.zeros(3)
    for field, label, color in (("local_successes", "Local recovery", COLORS[METHODS[2]]),
                                ("precheck_no_candidate", "No nearby candidate (skip local)", "#9ba7b3"),
                                ("failed_local_attempts", "Failed local attempt + global", "#ae4b50")):
        counts = np.array([r[field] for r in fallbacks])
        ax.bar(x, counts, bottom=bottom, color=color, label=label)
        for xx, count, base in zip(x, counts, bottom):
            if count:
                ax.text(xx, base + count/2, str(count), ha="center", va="center", color="white", weight="bold")
        bottom += counts
    ax.set(xticks=x, xticklabels=SCALES, xlabel="Number of robots", ylabel="Trials out of 30",
           ylim=(0, 36), title="Distance-Scoped ED-CBBA: recovery / fallback outcomes")
    ax.legend(fontsize=8, loc="upper left", ncol=1)
    fig.savefig(figures / "local_recovery_fallback_breakdown.png")
    plt.close(fig)
    fig, ax = plt.subplots(figsize=(8, 4.8), constrained_layout=True)
    for i, n in enumerate(SCALES):
        saving = [rows[n, s, METHODS[1]]["post_failure_broadcasts"] - rows[n, s, METHODS[2]]["post_failure_broadcasts"] for s in range(30)]
        # Deterministic display offsets; no data values are changed.
        ax.scatter(np.full(30, n) + np.linspace(-.35, .35, 30), saving, color=COLORS[METHODS[2]], alpha=.75, s=28)
    ax.axhline(0, color="#555555", linewidth=1)
    ax.set(xticks=SCALES, xlabel="Number of robots", ylabel="Paired broadcast saving (Global ED - Distance ED)",
           title="All 90 paired outcomes; negative values retain fallback penalties")
    ax.grid(alpha=.22)
    fig.savefig(figures / "all_paired_local_savings.png")
    plt.close(fig)
    fig, ax = plt.subplots(figsize=(8, 4.8), constrained_layout=True)
    for target, reference in COMPARISONS[:2]:
        sample = [r for r in comparisons if r["target"] == target and r["reference"] == reference and r["metric"] == "assignment_score"]
        means = np.array([r["mean_difference_target_minus_reference"] for r in sample])
        low, high = np.array([r["difference_ci95_low"] for r in sample]), np.array([r["difference_ci95_high"] for r in sample])
        ax.errorbar(SCALES, means, yerr=[means-low, high-means], marker="o", capsize=4,
                    color=COLORS[target], label=f"{LABELS[target]} vs {LABELS[reference]}")
    ax.axhline(0, color="#555555", linewidth=1)
    ax.set(xlabel="Number of robots", ylabel="Mean paired score change (target - reference)", xticks=SCALES,
           title="Unbonused assignment score: paired 95% seed-bootstrap intervals")
    ax.legend(fontsize=8, loc="upper right")
    ax.grid(alpha=.22)
    fig.savefig(figures / "paired_assignment_score_change.png")
    plt.close(fig)
    fig, ax = plt.subplots(figsize=(8, 4.8), constrained_layout=True)
    x = np.arange(3)
    ax.bar(x-.22, [f["successful_local_broadcast_savings_total"] for f in fallbacks], width=.22,
           label="Savings from local successes", color=COLORS[METHODS[2]])
    ax.bar(x, [-f["failed_attempt_extra_broadcasts_total"] for f in fallbacks], width=.22,
           label="Failed-attempt penalty", color="#ae4b50")
    ax.bar(x+.22, [f["net_broadcast_savings_vs_global_ed_total"] for f in fallbacks], width=.22,
           label="Net saving", color=COLORS[METHODS[1]])
    ax.axhline(0, color="#555555", linewidth=1)
    ax.set(xticks=x, xticklabels=SCALES, xlabel="Number of robots", ylabel="Total broadcasts saved across 30 seeds",
           title="Local success savings minus all failed-attempt costs")
    ax.legend(fontsize=8)
    ax.grid(axis="y", alpha=.22)
    fig.savefig(figures / "local_cost_decomposition.png")
    plt.close(fig)


def fmt(value, decimals=3):
    return "N/A" if value is None else f"{value:.{decimals}f}"


def english_numbers(values):
    words = [f"{value:,}" for value in values]
    return ", ".join(words[:-1]) + ", and " + words[-1] if len(words) > 2 else " and ".join(words)


def write_report(output, rows, summary, comparisons, fallbacks, failures, audit, metadata):
    group = {(r["num_robots"], r["method"], r["metric"]): r for r in summary}
    pair = {(r["num_robots"], r["target"], r["reference"], r["metric"]): r for r in comparisons}
    lines = ["# Experiment 1: Homogeneous - Formal Paired Evaluation", "",
        "## 1. Objective", "",
        "Compare Standard CBBA, global event-driven CBBA (ED-CBBA), and Distance-Scoped ED-CBBA "
        "as the team grows, measuring only re-auction after one assigned robot fails before execution. "
        "The complete formal dataset contains **270 method results from 90 shared initial missions**.", "",
        "## 2. Experimental Setup", "",
        "| Parameter | Setting |", "| --- | --- |",
        "| Robots / tasks | 6/18, 12/36, 24/72 |", "| Seeds | Exactly 0-29 at each scale; 30 paired trials, 90 method outcomes per scale |",
        "| Types / compatibility | One robot type, one task type; fully compatible |",
        "| Map / positions | 100 x 100 m, z=0; independent uniform coordinates |",
        "| Robot speed / capacity | 5 m/s / four tasks |", "| Task value / duration / start window | 100 / 8 s / [0,240] s |",
        "| Local radius / affected-task limit | Inclusive 40 m / at most four affected tasks |",
        "| Discount / incumbent bid bonus | 0.02 / 10%; explicit project assumptions, not mandated requirements |", "",
        "Each mission uses Random(seed), generating robot positions then task positions in ID order. "
        "One initial ED-CBBA assignment is computed and reused. Random(100000+seed) chooses one robot "
        "from sorted assigned IDs to fail. Deep copies and SHA-256 input fingerprints enforce pairing. "
        "Coordinates, original ownership, paths, planned times, failure ID and initial auction records "
        "are saved once per mission. No input is resampled or changed to improve outcomes. "
        "The complete parameter settings are defined in config_homogeneous_scenario.json.", "",
        "## 3. Compared Methods", "",
        "**Standard CBBA** re-auctions every task globally among all survivors and broadcasts every round. "
        "**Global ED-CBBA** uses identical bidding, incumbency and scope, but broadcasts only when winner "
        "or winning-bid lists differ from the last sent state. **Distance-Scoped ED-CBBA** first uses ED-CBBA "
        "among the union of surviving, compatible robots within 40 m of affected tasks. Affected-task "
        "eligibility is enforced separately for each task. Existing tasks of participants enter the local "
        "scope; outsiders retain owners, paths and times. Local bidding is skipped for an uncovered "
        "affected task or more than four affected tasks. Incomplete/invalid local results cause a fresh "
        "global ED auction. Costs from an actual failed local attempt are retained. No extra optimization was added.", "",
        "Bidding and consensus use the existing repository CBBA solver without changing its algorithm. "
        "Independent audit and offline analysis read saved results without executing the solver.", "",
        "## 4. Metrics and Statistical Methods", "",
        "Broadcasts count sending robots, once per round, irrespective of recipients. Post-failure "
        "broadcasts and consensus rounds sum every actual local and global auction; initial allocation "
        "is excluded. Broadcasts per affected task divide each trial's total by its failed robot's original "
        "task count, before averaging. Assigned-task rate is unique final assigned tasks / all original tasks. "
        "Unbonused score is J=sum(value * exp(-discount * (planned_start-release))). Local recovery rate "
        "is successful local recoveries / all 30 distance-method trials; global methods are N/A.", "",
        "Runtime uses perf_counter over post-failure scope selection, auction preparation/solve and "
        "validation, excluding common initial allocation, method-input copying/fingerprinting and export. "
        "Each auction's setup/solve time is separately retained; controller/validation overhead completes "
        "the total. Execution was serial after tests, in fixed Standard, Global ED, Distance ED order.", "",
        "summary_statistics.csv records n, mean, sample SD (ddof=1), median, minimum and maximum for "
        "all seven metrics, with N/A rows for nonapplicable local rates. Continuous-mean intervals and "
        "paired-difference intervals use a paired-seed percentile bootstrap: 20,000 resamples of 30 "
        "seed indices, NumPy PCG64 default_rng(20261120+robot_count), linear 2.5/97.5% quantiles. "
        "The same resampling indices are used for every method and metric at a given scale. Local-rate "
        "intervals are 95% Wilson intervals. Zero empirical variance gives a degenerate bootstrap interval; "
        "it does not prove universal certainty.", "",
        "Paired differences are target minus reference; a negative cost difference is beneficial. "
        "Mean per-seed relative change is mean(100*(target-reference)/reference). Headline reduction "
        "percentages instead use 100*(mean(reference)-mean(target))/mean(reference); both are exported "
        "and must not be confused. Intervals are exploratory, unadjusted for multiple comparisons, "
        "and conditional on these seeded missions and assumptions. Scale-wise analyses do not treat "
        "the same seed across scales as independent pooled observations.", "",
        "## 5. Results", "",
        "### Seven required metrics", "",
        "All values below are arithmetic means; n=30 per method/scale. Full dispersion and extrema are in summary_statistics.csv.", "",
        "| Robots | Method | Broadcasts | Broadcasts/affected | Runtime s | Rounds | Assigned rate | Score | Local recovery |",
        "| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for n in SCALES:
        for method in METHODS:
            vals = [group[n, method, metric]["mean"] for metric in METRICS]
            text = [fmt(v, 6 if metric == "runtime_seconds" else 3) for metric, v in zip(METRICS, vals)]
            lines.append(f"| {n} | {LABELS[method]} | " + " | ".join(text) + " |")
    lines += ["", "![All seven metrics](figures/all_seven_metrics.png)", "",
        "### Recovery, fallback and retained penalties", "",
        "| Robots | Local recovery | 95% Wilson CI | No candidate: skip | Failed local + global | Extra broadcasts from failed attempts | Local cost > Global ED |",
        "| ---: | ---: | --- | ---: | ---: | ---: | ---: |"]
    for f in fallbacks:
        lines.append(f"| {f['num_robots']} | {f['local_successes']}/30 ({100*f['local_recovery_rate']:.1f}%) | "
            f"[{100*f['local_rate_ci95_low']:.1f}%, {100*f['local_rate_ci95_high']:.1f}%] | {f['precheck_no_candidate']} | "
            f"{f['failed_local_attempts']} | {f['failed_attempt_extra_broadcasts_total']} | {f['higher_broadcast_cost_than_global_ed']}/30 |")
    lines += ["", "There were no task-count-limit or solver-error fallback cases. The affected-task limit "
        "cannot be exceeded in a valid capacity-four initial mission; its defensive branch was tested "
        "by unit tests. Failed local auctions are not removed; every fallback record is in fallback_attempts.csv. "
        "All fallback global paths, bids, broadcasts and rounds match the corresponding standalone Global ED "
        "control (runtime is allowed to differ). A failed greedy local auction does not prove mathematical infeasibility.", "",
        "![Recovery and fallback](figures/local_recovery_fallback_breakdown.png)", "",
        f"Savings from successful local recoveries total {english_numbers(f['successful_local_broadcast_savings_total'] for f in fallbacks)} "
        "broadcasts for 6, 12, and 24 robots, respectively. "
        f"Failed local attempts add {english_numbers(f['failed_attempt_extra_broadcasts_total'] for f in fallbacks)} "
        f"broadcasts, respectively, leaving net savings of {english_numbers(f['net_broadcast_savings_vs_global_ed_total'] for f in fallbacks)} "
        "across each scale's 30 paired missions. Negative net savings represent extra cost.", "",
        "![Success savings and failure penalties](figures/local_cost_decomposition.png)", "",
        "## 6. Paired Comparisons", "",
        "### Broadcasts", "",
        "Positive savings mean fewer broadcasts for the target. Intervals describe the mean paired absolute saving. "
        "Reduction percentages are ratios of sample means.", "",
        "| Robots | Target vs reference | Mean saving | Paired 95% CI | Reduction of means |",
        "| ---: | --- | ---: | --- | ---: |"]
    for n in SCALES:
        for target, reference in COMPARISONS:
            p = pair[n, target, reference, "post_failure_broadcasts"]
            lines.append(f"| {n} | {LABELS[target]} vs {LABELS[reference]} | {p['mean_saving_reference_minus_target']:.3f} | "
                f"[{p['saving_ci95_low']:.3f}, {p['saving_ci95_high']:.3f}] | {p['reduction_of_means_percent']:.2f}% |")
    lines += ["", "![Paired savings](figures/paired_broadcast_savings.png)", "",
              "![Extra spatial-scope savings](figures/paired_local_broadcast_savings.png)", "",
              "![All paired local savings](figures/all_paired_local_savings.png)", "",
        "### Assignment score, rounds and runtime", "",
        "| Robots | Target vs reference | Score change (paired 95% CI) | Score reduction | Rounds change | Runtime change s |",
        "| ---: | --- | --- | ---: | ---: | ---: |"]
    for n in SCALES:
        for target, reference in COMPARISONS[:2]:
            score = pair[n, target, reference, "assignment_score"]
            rounds = pair[n, target, reference, "consensus_rounds"]
            runtime = pair[n, target, reference, "runtime_seconds"]
            lines.append(f"| {n} | {LABELS[target]} vs {LABELS[reference]} | "
                f"{score['mean_difference_target_minus_reference']:.3f} [{score['difference_ci95_low']:.3f}, {score['difference_ci95_high']:.3f}] | "
                f"{score['reduction_of_means_percent']:.4f}% | {rounds['mean_difference_target_minus_reference']:.3f} | "
                f"{runtime['mean_difference_target_minus_reference']:.6f} |")
    lines += ["", "All six comparable metrics and all three method pairs, including runtime/round confidence "
        "intervals and both relative-change definitions, are in paired_comparisons.csv. Seed-level differences "
        "are in paired_seed_differences.csv. Assigned-task-rate differences are exactly zero for every pair.", "",
        "![Paired assignment score change](figures/paired_assignment_score_change.png)", "",
        "## 7. Discussion", "",
        "### Observations", ""]
    ed_percent, local_percent = [], []
    for n in SCALES:
        ed = pair[n, METHODS[1], METHODS[0], "post_failure_broadcasts"]
        local = pair[n, METHODS[2], METHODS[1], "post_failure_broadcasts"]
        ed_percent.append(f"{ed['reduction_of_means_percent']:.2f}%")
        local_percent.append(f"{local['reduction_of_means_percent']:.2f}%")
    lines += [f"Global ED reduces mean broadcasts relative to Standard by {', '.join(ed_percent)} at 6, 12, and 24 robots, respectively. "
        "The paired absolute-saving intervals exclude zero at every scale, and the observed percentage "
        "reduction grows with team size. Standard and Global ED have identical final paths, start times, "
        "scores and total rounds in every one of the 90 shared missions.", "",
        f"Distance ED's mean broadcast reductions relative to Global ED are {', '.join(local_percent)} at 6, 12, and 24 robots, respectively; "
        "a negative percentage is an increase. Local recovery rises from 20.0% to 56.7% to 93.3%. "
        "At six robots, failed-attempt penalties outweigh average local communication savings. At 12 robots "
        "the mean favors local scope, but its paired saving interval includes zero; these samples do not "
        "establish a reliable extra broadcast benefit there. At 24 robots the local broadcast saving is "
        "large and its paired interval excludes zero. Local scope is therefore not uniformly beneficial.", "",
        "All methods assign 100% of tasks in all 270 outcomes. The distance policy changes scores slightly "
        "relative to Global ED; the table above quantifies those paired changes instead of treating reduced "
        "communication as free. No task was dropped to obtain these results. Raw scores increase across "
        "scales partly because there are more tasks; scores should also be read against their corresponding "
        "maximum values 1,800, 3,600, and 7,200, rather than compared as identical workloads.", "",
        "Broadcast savings do not translate one-for-one to runtime or rounds. ED suppresses messages while "
        "retaining the same rounds. At 6 robots distance scope has slightly more broadcasts and more rounds "
        "on average, despite a small runtime decrease. At 12 robots the round decrease is small; at 24 both "
        "rounds and runtime decrease substantially. Runtime comparisons remain descriptive because the "
        "method order was fixed and no independent timing replication was performed.", "",
        "### Interpretation (inference, not a separately tested cause)", "",
        "More robots in the same map plausibly provide more nearby eligible bidders and spare local "
        "capacity. This is consistent with higher observed local recovery, but the experiment does not "
        "independently isolate density from other scale effects. The unchanged Standard/ED paths are "
        "consistent with changing transmission policy rather than bidding. Legacy quiet tails and the "
        "number of participant/task loops plausibly explain part of the mismatch between rounds, runtime "
        "and broadcasts; the data do not quantify each causal contribution.", "",
        "## 8. Limitations", "",
        "- Consensus rounds include the original participant-count-dependent quiet stopping tail; they are not certified convergence times.",
        "- Runtime includes audit/controller overhead and depends on system load, fixed method order, and hardware. A single timed run per seed does not establish a universal speedup.",
        "- 40 m is spatial bidding eligibility, not a radio range; each actual auction assumes a complete communication graph.",
        "- There is no physical robot execution or realistic communication network simulation, packet delay, bandwidth contention, or mobility during execution.",
        "- Broadcast counts are sending events, not bytes, packet payload size, or measured network traffic.",
        "- Failure detection, heartbeat and scope-coordination/dissemination communication are excluded.",
        "- Every actual auction's participants agree on winners/bids and paths. Local results compose that consensus with frozen outsider schedules; mission-wide belief synchronization to nonparticipants is not simulated or verified.",
        "- Discount 0.02, 10% incumbent bonus, uniform positions and the failure-selection rule are explicit project assumptions.",
        "- Local greedy CBBA is not a global optimum solver; an unsuccessful local attempt does not establish true local infeasibility.",
        "- Thirty paired seeds per scale and exploratory unadjusted intervals do not establish generality beyond the tested configuration. No equivalence margin was prespecified for score differences.", "",
        "## 9. Reproducibility and Independent Audit", "",
        f"The independent auditor executed **{audit['checks_executed']:,} checks** with zero errors. "
        "It reads saved CSV/snapshots/raw solver records without importing the experiment or solver, "
        "reconstructs positions and the failure rule, recomputes physical feasibility and unbonused "
        "scores, checks every participant's winner/bid records, validates all cost sums and verifies source "
        "and raw-data hashes. Five deliberately corrupted in-memory negative controls were detected. "
        "All 90 snapshots and 270 diagnostics are retained in audit_evidence.jsonl.gz. All 28 tests available "
        "at experiment execution passed before the serial run. The compact evidence expands only into a "
        "temporary directory during audit; CSV alone would not establish schedule or consensus validity.", "",
        f"The baseline repository commit was `{metadata['run_base_commit']}`. "
        "Experiment files were uncommitted at execution time. The exact executed source witnesses and "
        "their SHA-256 values are retained in the compressed audit evidence, alongside preflight metadata, "
        "configuration, interpreter and dependency versions. run_provenance.json distinguishes execution-time "
        "source hashes from the delivered audit/analysis scripts. Subsequent report-wording and artifact-loading "
        "changes do not alter bidding, experiment parameters, or numerical observations.", "",
        "```powershell",
        ".\\.venv\\Scripts\\python.exe -m unittest discover -s test -p 'test_*.py' -v",
        ".\\.venv\\Scripts\\python.exe test/run_homogeneous_experiment.py --full --output-dir outputs/homogeneous_reproduction",
        ".\\.venv\\Scripts\\python.exe test/audit_homogeneous_results.py --output-dir doc/homogeneous",
        ".\\.venv\\Scripts\\python.exe test/analyze_homogeneous_results.py --output-dir doc/homogeneous",
        "```", "",
        "The experiment command requires a new empty output directory and must not overwrite this run. "
        "The last two commands audit and regenerate the committed results without rerunning auctions. "
        "Full local raw outputs remain separate from this compact results directory. "
        "trials.csv and all evidence bytes remain unchanged.", "",
        "Key files: final_report.md; summary_statistics.csv; paired_comparisons.csv; paired_seed_differences.csv; "
        "fallback_summary.csv; fallback_attempts.csv; independent_audit.json; audit_evidence.jsonl.gz; "
        "run_provenance.json; environment-freeze.txt; analysis_statistics.json; README.md.", ""]
    (output / "final_report.md").write_text("\n".join(lines), encoding="utf-8")


def analyze_saved(data, output):
    hashes = read_json(data / "raw_files_sha256.json")
    if not all(sha(data / name) == h for name, h in hashes.items()):
        raise RuntimeError("Raw data hash mismatch; refusing analysis")
    audit = read_json(output / "independent_audit.json")
    if not audit["audit_passed"]:
        raise RuntimeError("Independent audit failed; retain evidence and diagnose")
    details = [read_json(p) for p in sorted((data / "diagnostics").glob("*.json"))]
    rows, summary, comparisons, per_seed = build_statistics(details)
    fallbacks, failures = fallback_statistics(rows, details)
    assert len(rows) == 270 and len(summary) == 63 and len(comparisons) == 54 and len(per_seed) == 1620
    assert all(r["n"] == (0 if not r["applicable"] else 30) for r in summary)
    assert all(f["fallback_equals_standalone_global_ed_except_timing"] for f in failures)
    # Independent arithmetic cross-checks, without resampling or rerunning experiments.
    for item in summary:
        values = [rows[item["num_robots"], seed, item["method"]][item["metric"]] for seed in range(30)]
        values = [v for v in values if v is not None]
        if values:
            assert math.isclose(item["mean"], statistics.mean(values), rel_tol=1e-12, abs_tol=1e-12)
            assert math.isclose(item["std"], statistics.stdev(values), rel_tol=1e-12, abs_tol=1e-12)
    write_csv(output / "summary_statistics.csv", summary)
    write_csv(output / "paired_comparisons.csv", comparisons)
    write_csv(output / "paired_seed_differences.csv", per_seed)
    write_csv(output / "fallback_summary.csv", fallbacks)
    write_csv(output / "fallback_attempts.csv", failures)
    plot_all(output, summary, comparisons, fallbacks, rows, compact=data != output)
    metadata = {"source_sha256": sha(Path(__file__)), "numpy": np.__version__, "matplotlib": matplotlib.__version__,
        "run_base_commit": read_json(data / "preflight.json")["git_commit"],
        "bootstrap_replicates": BOOTSTRAP_REPLICATES, "bootstrap_seed_rule": "20261120 + num_robots",
        "bootstrap_rng": "NumPy default_rng / PCG64", "quantile_method": "linear percentile 2.5%,97.5%",
        "ci_interpretation": "Exploratory unadjusted intervals; paired resampling within each scale",
        "summary_rows": len(summary), "comparison_rows": len(comparisons), "seed_difference_rows": len(per_seed),
        "fallback_summary": fallbacks, "full_data_audit_passed": audit["audit_passed"],
        "raw_files_unchanged": True, "statistical_cross_checks_passed": True}
    write_report(output, rows, summary, comparisons, fallbacks, failures, audit, metadata)
    assert all(sha(data / name) == h for name, h in hashes.items()), "Analysis changed raw evidence"
    write_json(output / "analysis_statistics.json", metadata)
    print(json.dumps({"analysis_complete": True, "summary_rows": len(summary), "comparison_rows": len(comparisons),
                      "fallback_summary": fallbacks, "raw_files_unchanged": True}, indent=2))
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    output = args.output_dir.resolve()
    with evidence_directory(output) as data:
        return analyze_saved(data, output)


if __name__ == "__main__":
    raise SystemExit(main())
