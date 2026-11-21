# 2026-11-20: Experiment 3B breaking-point run

**Code changes before the run:** `lib/CBBA.py` gained `failed_agents`, `warm_start`,
`inform_round`, `max_rounds` (all off by default); `test/run_exp3_shared.py` gained the
`global_ed_refresh` method, general radio-range rules and solver-option passthrough;
new `test/run_breakpoints.py`, `test/analyse_breakpoints.py`, `test/test_breakpoints.py`,
`scripts/smoke_breakpoints.sh`. Tests: 36/36 pass.

**Smoke:** local (8 processes, 37.7 s) and vanilla (30 processes, 73.6 s): 1,068 rows,
0 errors.

**Full run (vanilla):**
`PYTHONPATH=.:lib:test .venv/bin/python test/run_breakpoints.py --seeds 50 --jobs 40 --out-root results/breakpoints`
started 19:33, 337 s wall, 750 missions, 26,700 re-auctions, 0 errors, 0 runs hit the
500-round cap. Log: `results/logs/breakpoints_full_20261120_1933.log`. Copied to
`results/breakpoints/`; analysed with `test/analyse_breakpoints.py results/breakpoints`.

**Checked by hand:** one inconsistent ED-CBBA run from `stale_delay` (d = 10). Late robots
held an outdated winner for all 4 of the failed robot's tasks; broadcasts stopped after
round 13. This corrected my first guess (that late robots would think the tasks unowned).

Findings: [`../findings/exp3b-breaking-points.md`](../findings/exp3b-breaking-points.md).
