#!/usr/bin/env python3
"""Summarise breaking-point sweeps written by run_breakpoints.py.

Per sweep: <root>/<sweep>/summary.md and figures/ (success rate, consistency rate,
broadcasts and rounds vs stress level; Wilson 95% intervals on rates). Across sweeps:
<root>/breakpoints.md with the first stress level at which each method's success rate
falls below 90% and below 50%.
"""

import argparse
import csv
import math
import statistics
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from test.analyse_exp3 import GRID, INK, MUTED, wilson  # noqa: E402
from test.run_breakpoints import SWEEPS, level_label  # noqa: E402

METHOD_ORDER = ["global_cbba", "global_ed", "global_ed_refresh", "scoped_ed"]
METHOD_LABEL = {"global_cbba": "Standard CBBA", "global_ed": "ED-CBBA",
                "global_ed_refresh": "ED-CBBA + refresh/5", "scoped_ed": "Scoped ED-CBBA (40 m)"}
# Validated categorical slots 1-4 (adjacent pairs pass); markers give a second encoding.
METHOD_STYLE = {"global_cbba": ("#2a78d6", "o"), "global_ed": ("#eb6834", "s"),
                "global_ed_refresh": ("#1baf7a", "D"), "scoped_ed": ("#eda100", "^")}
THRESHOLDS = (0.9, 0.5)
SWEEP_TITLE = {
    "split": "Fixed radio range (smaller range = more likely the failure splits the team)",
    "loss_sparse": "Packet loss on networks of different sparseness",
    "mass_failure": "Fraction of the team failing at once",
    "stale_never": "Fraction of survivors that ever learn of the failure",
    "stale_delay": "Rounds before the second half of the team learns of the failure",
}
X_LABEL = {"split": "radio range (m)", "loss_sparse": "packet loss probability",
           "mass_failure": "robots failing at once", "stale_never": "fraction informed",
           "stale_delay": "inform delay (rounds)"}


def load(path):
    with path.open() as file:
        return list(csv.DictReader(file))


def rate(rows, column):
    return wilson(sum(r[column] == "1" for r in rows), len(rows)) if rows else (math.nan,) * 3


def mean(rows, column):
    values = [float(r[column]) for r in rows if r[column] not in ("", None)]
    return statistics.fmean(values) if values else math.nan


def panels(sweep):
    """Groups of levels drawn as one line each: loss_sparse splits by radio range."""
    levels = SWEEPS[sweep]["levels"]
    if sweep == "loss_sparse":
        out = {}
        for factor, loss in levels:
            name = "full communication" if factor == "full" else f"range = {factor}x connectivity threshold"
            out.setdefault(name, []).append((level_label((factor, loss)), str(loss)))
        return out
    return {"": [(level_label(x), level_label(x)) for x in levels]}


def plot(rows, sweep, column, ylabel, out, is_rate):
    sizes = sorted({int(r["size"]) for r in rows})
    groups = panels(sweep)
    fig, axes = plt.subplots(len(groups), len(sizes), figsize=(4.6 * len(sizes), 3.3 * len(groups)),
                             squeeze=False, sharey=is_rate)
    for gi, (group, levels) in enumerate(groups.items()):
        for si, size in enumerate(sizes):
            ax = axes[gi][si]
            for method in METHOD_ORDER:
                sub = [r for r in rows if r["method"] == method and int(r["size"]) == size]
                if not sub:
                    continue
                color, marker = METHOD_STYLE[method]
                xs, ys, lo, hi = [], [], [], []
                for x, (label, _) in enumerate(levels):
                    cell = [r for r in sub if r["level"] == label]
                    if not cell:
                        continue
                    if is_rate:
                        p, low, high = rate(cell, column)
                        xs.append(x); ys.append(p); lo.append(p - low); hi.append(high - p)
                    else:
                        xs.append(x); ys.append(mean(cell, column)); lo.append(0); hi.append(0)
                ax.errorbar(xs, ys, yerr=[lo, hi] if is_rate else None, color=color, marker=marker,
                            markersize=6, linewidth=2, capsize=3, label=METHOD_LABEL[method])
            if is_rate:
                for t in THRESHOLDS:
                    ax.axhline(t, color=MUTED, linewidth=0.8, linestyle=":")
                ax.set_ylim(-0.03, 1.03)
            ax.set_xticks(range(len(levels)), [tick for _, tick in levels], fontsize=8)
            ax.set_title(f"{size} robots" + (f" · {group}" if group else ""), fontsize=9, color=MUTED)
            ax.grid(axis="y", color=GRID, linewidth=0.8)
            for spine in ("top", "right"):
                ax.spines[spine].set_visible(False)
            if si == 0:
                ax.set_ylabel(ylabel, color=MUTED)
            if gi == len(groups) - 1:
                ax.set_xlabel(X_LABEL[sweep] + "  (more stress →)", color=MUTED)
    handles, labels = axes[0][0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower center", ncol=len(labels), frameon=False, fontsize=8)
    fig.suptitle(f"{SWEEP_TITLE[sweep]}: {ylabel}", color=INK, fontsize=11)
    fig.tight_layout(rect=(0, 0.06, 1, 1))
    fig.savefig(out, dpi=150)
    plt.close(fig)


def first_break(rows, column, levels, threshold):
    """First level (in stress order) whose rate is below threshold; '-' if none."""
    for label, tick in levels:
        cell = [r for r in rows if r["level"] == label]
        if cell and sum(r[column] == "1" for r in cell) / len(cell) < threshold:
            return tick
    return "-"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("root", type=Path, nargs="?", default=ROOT / "results" / "breakpoints")
    args = parser.parse_args(argv)
    overview = ["# Breaking points", "",
                "First stress level at which a method's rate drops below 90% / below 50% of runs "
                "(`-` = never within the tested range). **Success** = robots agree, no task claimed "
                "twice, auction ended by itself, and no task lost while capacity remained. "
                "**Consistent** = the first three only.", ""]
    for sweep in SWEEPS:
        path = args.root / sweep / "runs.csv"
        if not path.exists():
            continue
        rows = load(path)
        fig_dir = args.root / sweep / "figures"
        fig_dir.mkdir(exist_ok=True)
        plot(rows, sweep, "success", "success rate", fig_dir / "success.png", True)
        plot(rows, sweep, "consistent", "consistency rate", fig_dir / "consistent.png", True)
        plot(rows, sweep, "broadcasts_to_converge", "broadcasts until stable",
             fig_dir / "broadcasts.png", False)
        plot(rows, sweep, "rounds_to_converge", "rounds until stable", fig_dir / "rounds.png", False)
        sizes = sorted({int(r["size"]) for r in rows})
        n_seeds = len({r["seed"] for r in rows})

        overview += [f"## {SWEEP_TITLE[sweep]}", "",
                     f"Levels in stress order: {', '.join(t for g in panels(sweep).values() for _, t in g)}. "
                     f"{n_seeds} seeds. Details: [`{sweep}/summary.md`]({sweep}/summary.md).", "",
                     "| group | robots | method | success <90% | success <50% | consistent <90% | consistent <50% |",
                     "| --- | ---: | --- | --- | --- | --- | --- |"]
        lines = [f"# {SWEEP_TITLE[sweep]}", "", f"{n_seeds} seeds per cell. Rates: value [Wilson 95%].", "",
                 "![success](figures/success.png)", "", "![consistent](figures/consistent.png)", "",
                 "![broadcasts](figures/broadcasts.png)", "", "![rounds](figures/rounds.png)", ""]
        for group, levels in panels(sweep).items():
            for size in sizes:
                for method in METHOD_ORDER:
                    sub = [r for r in rows if r["method"] == method and int(r["size"]) == size]
                    if not sub:
                        continue
                    cells = [first_break(sub, c, levels, t) for c in ("success", "consistent")
                             for t in THRESHOLDS]
                    overview.append(f"| {group or '-'} | {size} | {METHOD_LABEL[method]} | " + " | ".join(cells) + " |")
            lines += [f"## {group or 'All levels'}", "",
                      "| robots | level | method | success | consistent | avoidable loss | groups | "
                      "broadcasts | rounds | local rate |",
                      "| ---: | --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: |"]
            for size in sizes:
                for label, tick in levels:
                    for method in METHOD_ORDER:
                        cell = [r for r in rows if r["method"] == method and int(r["size"]) == size
                                and r["level"] == label]
                        if not cell:
                            continue
                        s, slo, shi = rate(cell, "success")
                        c, clo, chi = rate(cell, "consistent")
                        local = "-"
                        if method == "scoped_ed":
                            local = f"{sum(r['scope'] == 'local' for r in cell) / len(cell):.2f}"
                        lines.append(
                            f"| {size} | {tick} | {METHOD_LABEL[method]} | {s:.2f} [{slo:.2f}, {shi:.2f}] | "
                            f"{c:.2f} [{clo:.2f}, {chi:.2f}] | {mean(cell, 'avoidable_loss'):.2f} | "
                            f"{mean(cell, 'groups'):.1f} | {mean(cell, 'broadcasts_to_converge'):.0f} | "
                            f"{mean(cell, 'rounds_to_converge'):.1f} | {local} |")
            lines.append("")
        overview.append("")
        (args.root / sweep / "summary.md").write_text("\n".join(lines) + "\n")
    (args.root / "breakpoints.md").write_text("\n".join(overview) + "\n")
    print(f"wrote {args.root / 'breakpoints.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
