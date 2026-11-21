# 0002: Every task may start anywhere in [0, 240] s

**Status:** Accepted, 2026-11-20

**Context.** The spec says "a 0–240 s start window" without saying whether it is shared.

**Decision.** Every task has `start_time = 0`, `end_time = 240` (`end_time` is the latest
start in `CBBA.scoring_compute_score`). Score = 100 · e^(−0.02 · start).

**Why.** Time pressure then comes only from travel and task duration, so the effect of
robot-type durations is not mixed with random per-task windows.

**Consequence.** With 4 slots per robot and 3 tasks per robot, the window rarely binds.
Tight windows were offered as a stress condition and not selected.
