# 0003: Which robots fail, and when

**Status:** Accepted, 2026-11-20

**Decision.** Failure choices depend only on the mission, the common initial allocation
and the seed, never on the re-auction method, so methods stay paired.

| Failure mode | Who fails |
| --- | --- |
| `random` | one random robot that holds tasks (spec) |
| `targeted_shared` | the robot holding the most shared tasks (ties: most tasks, then random) |
| `random_pair` | two random robots holding tasks, at the same time |
| `ground_pair` | two ground robots (the faster type on shared tasks), at the same time |
| `cascade` | one random robot; after its re-auction finishes, a second one (chosen in advance) |

Timing: before execution (spec), or in `mid_mission` at a random time in 20–60% of the
initial plan's completion time. Robots then re-plan from where they are; finished tasks
and tasks survivors are executing are kept; the failed robot's in-progress task is lost.

**Limitation.** In `cascade` the second failure happens after the first re-auction has
converged, not during it: the solver cannot drop a robot mid-auction.
