# 2026-11-20: Experiment 3 full run (all 7 conditions, 30 seeds)

**Command (on `vanilla`, from `~/cbba_exp3`):**
`PYTHONPATH=.:lib:test .venv/bin/python test/run_exp3_shared.py --conditions all --jobs 40 --out-root results/exp3_shared`

**Code:** branch `exp3-Harmish`, uncommitted on top of `41d1ceb` (copied with rsync).
**Machine:** vanilla.cs.ucl.ac.uk, 48 threads, load ~2 before start; Python 3.13.11,
NumPy 2.5.5. **Time:** 16:39:04–16:40:01, 56 s wall.
**Output:** 630 missions, 3,510 re-auction runs, 0 errors. Copied to `results/exp3_shared/`.
Remote log: `results/logs/exp3_full_*.log`.

**Reproducibility:** smoke results were byte-identical locally and on vanilla (excluding timings).

**Analysis:** `test/analyse_exp3.py results/exp3_shared/<condition>` → `summary.md` + `figures/`;
`test/overview_exp3.py results/exp3_shared` → `overview.md`. Findings:
[`../findings/exp3-baseline-and-stress.md`](../findings/exp3-baseline-and-stress.md).
