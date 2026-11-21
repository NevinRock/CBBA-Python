# 2026-11-20: Experiment 3 setup and local smoke test

**Branch:** `exp3-Harmish` (uncommitted). **Machine:** local Mac, Python 3.13.15,
NumPy 2.5.5, Matplotlib 3.11.2 (`.venv`, created with `uv`).

## What was built
- Type-dependent duration in `lib/Task.py` and `lib/CBBA.py` (decision 0005).
- `lib/CBBA.py` records `last_change_round` (bookkeeping only; decision 0004).
- `config_exp3_shared.json`: robot/task types and every experiment parameter.
- `test/run_exp3_shared.py`: missions, failures, three re-auction methods, 7 conditions.
- `test/analyse_exp3.py`: per-condition summary and figures.
- `test/overview_exp3.py`: cross-condition table with breakdown flags.
- `scripts/smoke_exp3.sh`: unit tests → 2-seed run of every condition → analysis.

## Bugs caught before any real run
- Local recovery rebuilt untouched robots' paths in task-ID order, not execution order,
  producing infeasible schedules. Fixed; the schedule check caught it.
- Robot IDs grouped by type would have given CBBA's lower-ID tie-breaks to air robots.
  Fixed by shuffling IDs.

## Existing tests
Need `PYTHONPATH=.:lib:test`; without it `test_multitype_scenario` fails to import
(a pre-existing issue). With it: 30/30 pass (13 original + 17 new).

## Smoke run
`scripts/smoke_exp3.sh .venv/bin/python 6`: 42 missions, 234 re-auction runs, 0 errors,
18.7 s. Output: `results/exp3_shared_smoke/` (2 seeds; not for conclusions).

Early signals to check at 30 seeds:
- Removing the stopping rule's quiet rounds shrinks ED-CBBA's saving over standard CBBA
  at 24 robots from ~85% (620 → 92 broadcasts) to ~20% (115 → 92).
- Scoped recovery rarely stays local at 6 robots; under `range_limited` its local group
  is sometimes disconnected.
- `imbalanced` and multi-failure conditions leave tasks unassigned for every method.
- Shared tasks split roughly evenly between air and ground robots despite ground being
  twice as fast on them.
