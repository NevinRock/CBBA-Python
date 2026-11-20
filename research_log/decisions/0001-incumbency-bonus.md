# 0001: Keep the +10% incumbency bonus in Experiment 3

**Status:** Accepted, 2026-11-20

**Context.** The spec does not mention an incumbency bonus. The existing spatial re-auction
experiment multiplies a robot's bid on a task it already holds by 1.10, in both local
and global re-auctions.

**Decision.** Keep +10% for all three methods in every Experiment 3 condition.

**Why.** Results stay comparable with `doc/spatial_reauction_*`. It applies equally to
every method, so it does not favour one of them.

**Alternatives.** 0% (pure re-auction). Planned as a later sweep.

**Caveat.** The bonus inflates bids, not the true score: reported scores are recomputed
without it (`evaluate()` in `test/run_exp3_shared.py`).
