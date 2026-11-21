#!/usr/bin/env python3
"""Cross-condition overview for Experiment 3: where does each method break down?

Reads <root>/<condition>/trials.csv for every condition present and writes
<root>/overview.md: one row per condition x team size x method with the key measures,
plus flags that mark a breakdown. Within a condition, methods are paired.
"""

import argparse
import csv
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from test.analyse_exp3 import METHOD_LABEL, METHOD_ORDER, wilson  # noqa: E402
from test.run_exp3_shared import CONDITIONS  # noqa: E402

# A flag is raised when a method's mean, in one cell, crosses these lines.
SCORE_LOSS_VS_BEST = 0.01   # >1% below the best method on the same missions
LOCAL_RATE_LOW = 0.5        # scoped method recovers locally in under half the runs


def mean(rows, column):
    values = [float(r[column]) for r in rows if r[column] not in ("", None)]
    return statistics.fmean(values) if values else float("nan")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("root", type=Path, nargs="?", default=ROOT / "results" / "exp3_shared")
    args = parser.parse_args(argv)

    lines = ["# Experiment 3 stress overview", "",
             "Each condition changes one factor from the baseline. Means over seeds and failure "
             "modes. Broadcasts count rounds until the allocation stops changing; the total with "
             "the stopping rule's quiet rounds is in each condition's summary.", "",
             "Flags: **unassigned** assigned-task rate < 1; **no-consensus** some run ended without "
             "all robots agreeing; **duplicates** a task claimed twice; **score-loss** mean score "
             f"> {SCORE_LOSS_VS_BEST:.0%} below the best method; **rarely-local** scoped method "
             f"recovers locally in < {LOCAL_RATE_LOW:.0%} of runs.", "",
             "| condition | robots | method | broadcasts | rounds | assigned | score | makespan s | "
             "shared busy s | local rate | consensus | flags |",
             "| --- | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |"]
    found = 0
    for condition in CONDITIONS:
        path = args.root / condition / "trials.csv"
        if not path.exists():
            continue
        found += 1
        with path.open() as file:
            rows = list(csv.DictReader(file))
        for size in sorted({int(r["size"]) for r in rows}):
            cell = {m: [r for r in rows if r["method"] == m and int(r["size"]) == size]
                    for m in METHOD_ORDER}
            best_score = max(mean(v, "score") for v in cell.values() if v)
            for method in METHOD_ORDER:
                sub = cell[method]
                if not sub:
                    continue
                flags = []
                if mean(sub, "assigned_rate") < 1 - 1e-9:
                    flags.append("unassigned")
                consensus = sum(r["consensus_ok"] == "1" for r in sub) / len(sub)
                if consensus < 1:
                    flags.append("no-consensus")
                if any(int(r["duplicate_tasks"]) for r in sub):
                    flags.append("duplicates")
                if mean(sub, "score") < (1 - SCORE_LOSS_VS_BEST) * best_score:
                    flags.append("score-loss")
                local = "-"
                if method == "scoped_ed":
                    k = sum(r["scope"] == "local" for r in sub)
                    p, lo, hi = wilson(k, len(sub))
                    local = f"{p:.2f} [{lo:.2f}, {hi:.2f}]"
                    if p < LOCAL_RATE_LOW:
                        flags.append("rarely-local")
                lines.append(
                    f"| {condition} | {size} | {METHOD_LABEL[method]} | "
                    f"{mean(sub, 'broadcasts_to_converge'):.1f} | {mean(sub, 'rounds_to_converge'):.1f} | "
                    f"{mean(sub, 'assigned_rate'):.3f} | {mean(sub, 'score'):.1f} | "
                    f"{mean(sub, 'makespan_s'):.1f} | {mean(sub, 'shared_busy_s'):.1f} | {local} | "
                    f"{consensus:.2f} | {', '.join(flags) or '-'} |")
    if not found:
        print(f"no condition results under {args.root}")
        return 1
    (args.root / "overview.md").write_text("\n".join(lines) + "\n")
    print(f"wrote {args.root / 'overview.md'} ({found} conditions)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
