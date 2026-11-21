# 0006: Stress conditions

**Status:** Accepted, 2026-11-20

Each condition changes **one** factor from the baseline (`CONDITIONS` in
`test/run_exp3_shared.py`). Missions use the same seeds, so conditions that do not change
the mission (`mid_mission`, `range_limited`, `double_failure`, `cascading`) run on exactly
the baseline missions.

| Condition | Change from baseline |
| --- | --- |
| `baseline` | spec: uniform positions, half air / half ground, everyone hears everyone, failure before execution |
| `mid_mission` | failure at 20–60% of the initial completion time |
| `range_limited` | robots hear only robots within R = 1.2 × the smallest range that keeps the graph connected; scoped falls back if its local group is disconnected |
| `clustered` | tasks in 3 hotspots (σ = 8 m); robots uniform |
| `imbalanced` | one quarter ground robots (6→2, 12→3, 24→6) |
| `double_failure` | two robots fail at once (random pair; ground pair) |
| `cascading` | two failures in sequence |

Not selected for now: tight time windows, packet loss, β = 0, other radii.
