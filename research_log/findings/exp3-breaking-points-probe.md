# Experiment 3: where the algorithms break (exploratory probes)

**Status:** exploratory, 10–20 seeds per cell, run locally on 2026-11-20. Scripts:
`research_log/probes/probe_break.py`, `research_log/probes/probe_loss_sparse.py`.
To be repeated as formal 30-seed conditions before any claim is made.

Setup: Experiment 3 missions (balanced air/ground, shared tasks), one common initial
ED-CBBA allocation with full communication, one random assigned robot fails, then a
global re-auction among survivors under the probed condition.

## Hard break 1: a failure that splits the network
Fixed radio range for every robot; after the failure the survivors may form several
groups that cannot hear each other. Each group allocates on its own.

| Robots | Range | Mean groups | Robots agree | Runs with a task claimed twice | Tasks lost despite capacity |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 12 | 15 m | 7.8 | 0/10 | 10/10 | 4.6 |
| 12 | 30 m | 3.3 | 0/10 | 10/10 | 2.2 |
| 12 | 40 m | 1.4 | 6/10 | 4/10 | 0.6 |
| 24 | 20 m | 6.3 | 0/10 | 10/10 | 3.6 |
| 24 | 30 m | 2.4 | 4/10 | 6/10 | 0.6 |
| 24 | 40 m | 1.0 | 10/10 | 0/10 | 0.0 |

## Hard break 2: packet loss on a sparse network (ED-CBBA)
Range = 1.0× or 1.2× the smallest range that keeps survivors connected. Independent
loss per sender→receiver message. 20 seeds.

| Robots | Range | Loss | CBBA agree | ED-CBBA agree (dup runs) | ED + refresh/5 agree (dup runs) |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 12 | 1.0× | 0.1 | 20/20 | 11/20 (5) | 19/20 (0) |
| 12 | 1.0× | 0.3 | 20/20 | 7/20 (10) | 16/20 (3) |
| 12 | 1.0× | 0.5 | 18/20 | 2/20 (15) | 6/20 (10) |
| 24 | 1.0× | 0.3 | 20/20 | 5/20 (7) | 18/20 (0) |
| 24 | 1.0× | 0.5 | 20/20 | 2/20 (16) | 14/20 (1) |
| 24 | 1.2× | 0.5 | 20/20 | 4/20 (5) | 20/20 (0) |

Broadcasts at 24 robots, 1.0×: CBBA 767–872, ED 232–240, ED + refresh 341–393.
With **full** communication, loss up to 0.5 broke nothing (10/10 everywhere): every
robot hears everyone directly, so a lost message is almost always relayed by others.

## Soft breaks
- **Many failures at once** (24 robots): 25% failed → 2.6 tasks lost per run despite
  capacity (type-blind greedy bidding); 50% → capacity is the limit, no avoidable loss.
- **Overload** (2–3× tasks per robot): every slot is filled; degrades gracefully.
- **Team size:** simulated re-auction CPU grows steeply: 24 → 48 → 96 robots takes
  0.5 → 4 → 51 s (CBBA) and 0.4 → 1.9 → 17 s (ED). Rounds until agreement stay at ~4.
  Message size grows with the number of tasks (two lists per broadcast).

## Not yet tested
- **Stale ("zombie") bids:** robots that learn of the failure late keep and relay the
  failed robot's winning bids. Needs the solver to start from robots' existing beliefs.
