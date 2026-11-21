# Experiment 3 findings: baseline and stress conditions

30 paired seeds per condition × team size; 3 methods; full tables in
`results/exp3_shared/overview.md` and each `results/exp3_shared/<condition>/summary.md`.
In every run, all robots reached the same allocation and no task was claimed twice, so
the failures below are about cost and allocation quality, not consistency.

## 1. ED-CBBA's saving is mostly the stopping rule
Paired, baseline: broadcast reduction of ED-CBBA vs standard CBBA.

| Robots | Counting the stopping rule's quiet rounds | Until the allocation stops changing |
| ---: | ---: | ---: |
| 6 | 59% | 28% |
| 12 | 72% | 23% |
| 24 | 84% | 23% |

Most of the headline saving comes from standard CBBA re-broadcasting during the N quiet
rounds the simulator waits before stopping. The fair saving is ~23–28% and does not grow
with team size. Any comparison that only reports the first column overstates ED-CBBA.

## 2. CBBA wastes scarce robots' capacity: avoidable unassigned tasks
Time never binds here (4 tasks at maximum travel ≈ 150 s < 240 s window), so the number
of assignable tasks is set by free slots per type. Tasks left unassigned beyond that bound
are an algorithm failure. All three methods behave the same.

- `imbalanced` (one quarter ground robots): ground robots spend slots on shared tasks that
  air robots could do, so ground-only tasks go unassigned **even before any failure**.
  Over 30 seeds at 12 robots, ground robots held 75 shared tasks and exactly 75
  ground-only tasks were left unassigned (24 robots: 161 and 161). At 24 robots,
  4.5 tasks per run are lost avoidably after the failure, in 60/60 runs.
- After a failure in the balanced baseline at 6 robots, 0.65 tasks per run are lost
  avoidably (33/60 runs). Also seen with two failures at 6 and 12 robots.

Cause: CBBA bids on each robot's own marginal gain; nothing accounts for the fact that a
task only one type can do should get that type's limited capacity first.

## 3. Shared tasks: duration is nearly ignored
Ground robots take 5 s on a shared task, air robots 10 s, at equal speed. ED-CBBA gives
ground robots only 52–55% of shared tasks (balanced teams). Even when a ground robot is
the nearer one, an air robot wins about 20% of the time (41–52% in `imbalanced`). The
score depends on start time only, so a faster robot gains only through tasks queued
after it.

## 4. Scoped ED-CBBA: cheap when it works, rarely works under stress
Local recovery rate (scoped method):

| Condition | 6 robots | 12 | 24 |
| --- | ---: | ---: | ---: |
| baseline | 0.02 | 0.28 | 0.65 |
| mid_mission | 0.38 | 0.75 | 0.87 |
| range_limited | 0.02 | 0.18 | 0.55 |
| clustered | 0.05 | 0.38 | 0.73 |
| imbalanced | 0.20 | 0.30 | 0.42 |
| double_failure | 0.00 | 0.00 | 0.02 |
| cascading | 0.00 | 0.13 | 0.40 |

- Small teams: nobody capable within 40 m (84 of 180 baseline fallbacks).
- Two simultaneous failures: affected tasks exceed the 4-task local limit (174/180 runs),
  so the scoped method is just ED-CBBA.
- `range_limited`: 17 runs fell back because the local group could not talk to itself.
- When it falls back, its broadcasts include the wasted local attempt, so at 6 robots
  (baseline, clustered, cascading) it costs slightly *more* than plain ED-CBBA.
- Where local recovery is common (24 robots), it cuts broadcasts vs ED-CBBA by 35%
  (baseline: 82 → 54) to 63% (mid_mission: 59 → 22), for < 0.1% score loss and a
  mission that finishes ~1–1.5 s later.

## 5. Sparse communication multiplies cost
`range_limited` (R = 1.2 × the connectivity threshold; mean diameter 2.3 / 3.6 / 4.9 hops at
6 / 12 / 24 robots, up to 10): at 24
robots broadcasts more than double (CBBA 105 → 238, ED 82 → 181) and rounds go from ~5
to ~10. The relative saving of ED-CBBA is unchanged.

## Caveats
- Scoped recovery is charged nothing for knowing positions or for the failure
  announcement (no method is charged for the announcement).
- Cascading failures happen after the first re-auction converges, not during it.
- Runtime (`cpu_s`) is simulator CPU time for all robots together, not per robot.
