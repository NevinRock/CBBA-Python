#!/usr/bin/env python3
"""Summarise and plot Experiment 3 results written by run_exp3_shared.py.

Writes summary.md (tables with 95% CIs, paired differences, Wilson intervals) and
one PNG per measure (mean +/- 95% CI vs team size, one line per method, one panel per
failure mode) into the results directory.
"""

import argparse
import csv
import math
import statistics
import sys
from collections import defaultdict
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
METHOD_ORDER = ["global_cbba", "global_ed", "scoped_ed"]
METHOD_LABEL = {"global_cbba": "Standard CBBA", "global_ed": "ED-CBBA",
                "scoped_ed": "Scoped ED-CBBA (40 m)"}
# Validated categorical slots (light surface): blue, orange, aqua. Markers add a
# second encoding so identity never depends on colour alone.
METHOD_STYLE = {"global_cbba": ("#2a78d6", "o"), "global_ed": ("#eb6834", "s"),
                "scoped_ed": ("#1baf7a", "^")}
TYPE_COLOR = {"air": "#6250d6", "ground": "#eda100"}
INK, MUTED, GRID = "#0b0b0b", "#52514e", "#e4e3df"

MEASURES = [  # column, title, y label
    ("broadcasts_to_converge", "Post-failure broadcasts until the allocation stops changing",
     "broadcasts"),
    ("broadcasts", "Post-failure broadcasts incl. quiet rounds of the stopping rule", "broadcasts"),
    ("broadcasts_per_affected", "Broadcasts per affected task (incl. quiet rounds)",
     "broadcasts / affected task"),
    ("rounds_to_converge", "Consensus rounds until the allocation stops changing", "rounds"),
    ("rounds", "Consensus rounds incl. quiet rounds", "rounds"),
    ("cpu_s", "Re-auction runtime (CPU)", "seconds"),
    ("assigned_rate", "Assigned-task rate", "fraction of tasks assigned"),
    ("score", "Assignment score", "score"),
    ("makespan_s", "Mission completion time (last task finishes)", "seconds"),
    ("shared_busy_s", "Total robot time spent on shared tasks", "seconds"),
    ("changed_owners", "Surviving robots' tasks that changed owner", "tasks"),
]
MODE_ORDER = ["random", "targeted_shared", "random_pair", "ground_pair", "cascade"]
REASONS = ["too_many_affected_tasks", "no_nearby_capable_robot", "local_group_disconnected",
           "local_capacity_or_schedule_infeasible", "nothing_affected"]
T95 = {1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447, 7: 2.365, 8: 2.306,
       9: 2.262, 10: 2.228, 15: 2.131, 20: 2.086, 25: 2.060, 29: 2.045, 30: 2.042,
       40: 2.021, 60: 2.000, 120: 1.980}


def t_crit(df):
    if df <= 0:
        return float("nan")
    keys = [k for k in sorted(T95) if k <= df]
    return T95[keys[-1]] if df < 120 else 1.96


def mean_ci(values):
    values = [v for v in values if v is not None]
    if not values:
        return float("nan"), float("nan"), 0
    m = statistics.fmean(values)
    if len(values) < 2:
        return m, float("nan"), len(values)
    return m, t_crit(len(values) - 1) * statistics.stdev(values) / math.sqrt(len(values)), len(values)


def wilson(k, n, z=1.96):
    if n == 0:
        return float("nan"), float("nan"), float("nan")
    p = k / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return p, max(0.0, centre - half), min(1.0, centre + half)


def num(value):
    return None if value in ("", None) else float(value)


def load(path):
    with path.open() as file:
        return list(csv.DictReader(file))


def fmt(m, h, digits=2):
    if math.isnan(m):
        return "-"
    return f"{m:.{digits}f} ± {h:.{digits}f}" if not math.isnan(h) else f"{m:.{digits}f}"


def place_end_labels(fig, ax, ends, min_gap_px=13):
    """Direct-label line ends, nudging labels apart so they never overlap."""
    fig.canvas.draw()
    to_px = ax.transData.transform
    items = sorted((to_px((x, y))[1], x, y, label) for y, x, label in ends)
    placed = []
    for py, x, y, label in items:
        py_label = max(py, placed[-1] + min_gap_px) if placed else py
        placed.append(py_label)
        ax.annotate(label, (x, y), xytext=(8, py_label - py), textcoords="offset points",
                    va="center", fontsize=8, color=INK)


def plot_measure(rows, column, title, ylabel, sizes, modes, out):
    fig, axes = plt.subplots(1, len(modes), figsize=(5.2 * len(modes), 3.8), sharey=True,
                             squeeze=False)
    for ax, mode in zip(axes[0], modes):
        ends = []
        for method in METHOD_ORDER:
            color, marker = METHOD_STYLE[method]
            stats = [mean_ci(num(r[column]) for r in rows if r["method"] == method
                             and r["failure_mode"] == mode and int(r["size"]) == s) for s in sizes]
            xs = [s for s, (m, _, n) in zip(sizes, stats) if n]
            if not xs:
                continue
            ms = [m for m, _, n in stats if n]
            hs = [0 if math.isnan(h) else h for _, h, n in stats if n]
            ax.errorbar(xs, ms, yerr=hs, color=color, marker=marker, markersize=8,
                        linewidth=2, capsize=4, label=METHOD_LABEL[method])
            ends.append((ms[-1], xs[-1], METHOD_LABEL[method]))
        place_end_labels(fig, ax, ends)
        ax.set_title(f"failure: {mode}", fontsize=10, color=MUTED)
        ax.set_xticks(sizes)
        ax.set_xlim(min(sizes) - 2, max(sizes) * 1.35)
        ax.set_xlabel("robots", color=MUTED)
        ax.grid(axis="y", color=GRID, linewidth=0.8)
        for spine in ("top", "right"):
            ax.spines[spine].set_visible(False)
        ax.tick_params(colors=MUTED)
    axes[0][0].set_ylabel(ylabel, color=MUTED)
    axes[0][0].legend(frameon=False, fontsize=8, loc="upper left")
    fig.suptitle(f"{title} (mean ± 95% CI)", color=INK)
    fig.tight_layout()
    fig.savefig(out, dpi=150)
    plt.close(fig)


def plot_shared_winners(winners, sizes, modes, out):
    fig, axes = plt.subplots(1, len(modes), figsize=(5.2 * len(modes), 3.8), sharey=True,
                             squeeze=False)
    width = 0.26
    for ax, mode in zip(axes[0], modes):
        for j, method in enumerate(METHOD_ORDER):
            for i, size in enumerate(sizes):
                sub = [w for w in winners if w["method"] == method and w["failure_mode"] == mode
                       and int(w["size"]) == size]
                if not sub:
                    continue
                ground = sum(w["winner_type"] == "ground" for w in sub) / len(sub)
                air = sum(w["winner_type"] == "air" for w in sub) / len(sub)
                x = i + (j - 1) * (width + 0.02)
                ax.bar(x, ground, width, color=TYPE_COLOR["ground"], edgecolor="white", linewidth=2)
                ax.bar(x, air, width, bottom=ground, color=TYPE_COLOR["air"], edgecolor="white",
                       linewidth=2)
                ax.text(x, 1.02, "CES"[j], ha="center", fontsize=7, color=MUTED)
        ax.set_xticks(range(len(sizes)), [f"{s} robots" for s in sizes])
        ax.set_ylim(0, 1.1)
        ax.set_title(f"failure: {mode}", fontsize=10, color=MUTED)
        ax.grid(axis="y", color=GRID, linewidth=0.8)
        for spine in ("top", "right"):
            ax.spines[spine].set_visible(False)
    axes[0][0].set_ylabel("share of shared tasks won", color=MUTED)
    handles = [plt.Rectangle((0, 0), 1, 1, color=TYPE_COLOR[t]) for t in ("ground", "air")]
    fig.legend(handles, ["ground robot (5 s per shared task)", "air robot (10 s)"],
               frameon=False, fontsize=8, loc="lower center", ncol=2)
    fig.suptitle("Who wins shared tasks after re-auction  (C = CBBA, E = ED-CBBA, S = scoped)",
                 color=INK)
    fig.tight_layout(rect=(0, 0.07, 1, 1))
    fig.savefig(out, dpi=150)
    plt.close(fig)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("results_dir", type=Path, nargs="?",
                        default=ROOT / "results" / "exp3_shared" / "baseline")
    args = parser.parse_args(argv)
    rows = load(args.results_dir / "trials.csv")
    winners = load(args.results_dir / "shared_winners.csv")
    sizes = sorted({int(r["size"]) for r in rows})
    modes = [m for m in MODE_ORDER if any(r["failure_mode"] == m for r in rows)]
    fig_dir = args.results_dir / "figures"
    fig_dir.mkdir(exist_ok=True)

    condition = rows[0].get("condition", args.results_dir.name) if rows else args.results_dir.name
    lines = [f"# Experiment 3 (shared capabilities): {condition}", "",
             f"Source: `{args.results_dir.relative_to(ROOT) if args.results_dir.is_relative_to(ROOT) else args.results_dir}`. "
             f"{len({(r['size'], r['seed']) for r in rows})} missions, {len(rows)} re-auction runs. "
             "Values are mean ± 95% CI half-width (t-distribution) over seeds.", ""]

    for column, title, ylabel in MEASURES:
        plot_measure(rows, column, title, ylabel, sizes, modes, fig_dir / f"{column}.png")
        lines += [f"## {title}", "", f"![{title}](figures/{column}.png)", "",
                  "| failure | robots | " + " | ".join(METHOD_LABEL[m] for m in METHOD_ORDER) + " |",
                  "| --- | ---: | " + " | ".join("---:" for _ in METHOD_ORDER) + " |"]
        digits = 4 if column in ("cpu_s", "assigned_rate") else 2
        for mode in modes:
            for size in sizes:
                cells = [fmt(*mean_ci(num(r[column]) for r in rows if r["method"] == m and
                                      r["failure_mode"] == mode and int(r["size"]) == size)[:2],
                             digits=digits) for m in METHOD_ORDER]
                lines.append(f"| {mode} | {size} | " + " | ".join(cells) + " |")
        lines.append("")

    # Paired differences against standard CBBA, same mission and failed robot.
    lines += ["## Paired differences vs standard CBBA", "",
              "Per mission: method minus standard CBBA on the same mission and failed robot.", "",
              "| failure | robots | method | Δ broadcasts | broadcast reduction | Δ score | Δ assigned tasks |",
              "| --- | ---: | --- | ---: | ---: | ---: | ---: |"]
    index = {(r["size"], r["seed"], r["failure_mode"], r["method"]): r for r in rows}
    for mode in modes:
        for size in sizes:
            for method in METHOD_ORDER[1:]:
                pairs = [(index[(k[0], k[1], k[2], method)], base) for k, base in index.items()
                         if k[3] == "global_cbba" and k[2] == mode and int(k[0]) == size
                         and (k[0], k[1], k[2], method) in index]
                if not pairs:
                    continue
                db = mean_ci(float(a["broadcasts"]) - float(b["broadcasts"]) for a, b in pairs)
                red = mean_ci(1 - float(a["broadcasts"]) / float(b["broadcasts"]) for a, b in pairs
                              if float(b["broadcasts"]) > 0)
                ds = mean_ci(float(a["score"]) - float(b["score"]) for a, b in pairs)
                da = mean_ci(float(a["assigned_tasks"]) - float(b["assigned_tasks"]) for a, b in pairs)
                lines.append(f"| {mode} | {size} | {METHOD_LABEL[method]} | {fmt(*db[:2], 1)} | "
                             f"{fmt(100 * red[0], 100 * red[1], 1)}% | {fmt(*ds[:2], 2)} | {fmt(*da[:2], 2)} |")
    lines.append("")

    # Local recovery (scoped method only).
    lines += ["## Local recovery rate (scoped ED-CBBA)", "",
              "| failure | robots | local / runs | rate [95% Wilson] | "
              + " | ".join(r.replace("_", " ") for r in REASONS) + " |",
              "| --- | ---: | ---: | --- | " + " | ".join("---:" for _ in REASONS) + " |"]
    for mode in modes:
        for size in sizes:
            sub = [r for r in rows if r["method"] == "scoped_ed" and r["failure_mode"] == mode
                   and int(r["size"]) == size]
            if not sub:
                continue
            k = sum(r["scope"] == "local" for r in sub)
            p, lo, hi = wilson(k, len(sub))
            reasons = [sum(r["fallback_reason"] == reason for r in sub) for reason in REASONS]
            lines.append(f"| {mode} | {size} | {k}/{len(sub)} | {p:.2f} [{lo:.2f}, {hi:.2f}] | "
                         + " | ".join(map(str, reasons)) + " |")
    lines.append("")

    # Consistency: every robot holds the same winner list; no task claimed twice.
    lines += ["## Consistency", "",
              "| failure | robots | method | consensus reached [95% Wilson] | runs with duplicate claims |",
              "| --- | ---: | --- | --- | ---: |"]
    for mode in modes:
        for size in sizes:
            for method in METHOD_ORDER:
                sub = [r for r in rows if r["method"] == method and r["failure_mode"] == mode
                       and int(r["size"]) == size]
                if not sub:
                    continue
                p, lo, hi = wilson(sum(r["consensus_ok"] == "1" for r in sub), len(sub))
                dup = sum(int(r["duplicate_tasks"]) > 0 for r in sub)
                lines.append(f"| {mode} | {size} | {METHOD_LABEL[method]} | {p:.2f} [{lo:.2f}, {hi:.2f}] | {dup} |")
    lines.append("")

    # Shared-task winners.
    plot_shared_winners(winners, sizes, modes, fig_dir / "shared_winners.png")
    lines += ["## Shared-task winners", "", "![Shared winners](figures/shared_winners.png)", "",
              "Ground robots take 5 s on a shared task and air robots 10 s, at equal speed.", "",
              "| failure | robots | method | ground share | air share | unassigned | "
              "won by farther type |",
              "| --- | ---: | --- | ---: | ---: | ---: | ---: |"]
    for mode in modes:
        for size in sizes:
            for method in METHOD_ORDER:
                sub = [w for w in winners if w["method"] == method and w["failure_mode"] == mode
                       and int(w["size"]) == size]
                if not sub:
                    continue
                g = sum(w["winner_type"] == "ground" for w in sub) / len(sub)
                a = sum(w["winner_type"] == "air" for w in sub) / len(sub)
                u = sum(w["winner_type"] == "" for w in sub) / len(sub)
                farther = [w for w in sub if w["winner_type"] and w["nearest_air_m"] and w["nearest_ground_m"]]
                far = sum((w["winner_type"] == "air") == (float(w["nearest_air_m"]) > float(w["nearest_ground_m"]))
                          for w in farther) / max(1, len(farther))
                lines.append(f"| {mode} | {size} | {METHOD_LABEL[method]} | {g:.2f} | {a:.2f} | {u:.2f} | {far:.2f} |")
    lines += ["", "*won by farther type*: the winner's type has no robot closer to the task than "
              "the nearest robot of the other type.", ""]

    (args.results_dir / "summary.md").write_text("\n".join(lines))
    print(f"wrote {args.results_dir / 'summary.md'} and {len(MEASURES) + 1} figures")
    return 0


if __name__ == "__main__":
    sys.exit(main())
