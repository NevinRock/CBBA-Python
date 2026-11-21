# Experiment 3B: breaking points of failure re-auction

50 paired seeds per cell, 6/12/24 robots, 26,700 re-auctions, 0 errors (design: decision
0008). Tables: `results/breakpoints/breakpoints.md`; per-sweep tables and figures:
`results/breakpoints/<sweep>/summary.md`. "Consistent" = robots agree, no task claimed
twice, auction ended by itself. "Success" = consistent and no task lost while capacity
remained.

## Headline: the algorithms fail silently
No run in any sweep hit the 500-round cap. Every failure below is an auction that
stopped and reported a finished allocation while robots disagreed, a task was claimed
twice, or a task was dropped. Nothing in CBBA or ED-CBBA signals the failure.

## Breaking points (first level below 90% / below 50%)

| Stressor | 6 robots | 12 robots | 24 robots | Which methods |
| --- | --- | --- | --- | --- |
| Radio range (network split), consistency | 60 m / 50 m | 40 m / 40 m | 35 m / 30 m | all four alike |
| Loss on a barely connected network, consistency | ED 0.1 / 0.3; refresh 0.2 / 0.4; CBBA 0.4 / never | ED 0.1 / 0.3; refresh 0.3 / 0.5; CBBA 0.6 / never | ED 0.1 / 0.2; refresh 0.4 / 0.6; CBBA never | ED and scoped worst |
| Loss with full communication, consistency | ED 0.5; refresh 0.6; CBBA never | scoped 0.4; others never | scoped 0.6; others never | small auctions only |
| Robots failing at once, success | 1 robot (already) | 25% of team / 25% | 25% / 25% | all alike |
| Robots never told of the failure, consistency | any (90% told → 0%) | any | any | all alike |
| Delay before half the team is told, consistency | ED 5 rounds; others never | ED 5; others never | ED 5; others never | ED only |

## 1. A failure that splits the network breaks every method equally
Consistency (ED-CBBA) vs fixed radio range; mean number of disconnected groups in brackets.

| Robots | 60 m | 50 m | 40 m | 35 m | 30 m | 25 m | 20 m |
| ---: | --- | --- | --- | --- | --- | --- | --- |
| 6 | 0.68 (1.3) | 0.40 (1.7) | 0.06 (2.5) | 0.06 (2.7) | 0.02 (3.1) | 0.00 | 0.00 |
| 12 | 1.00 (1.0) | 0.92 (1.1) | 0.44 (1.7) | 0.18 (2.4) | 0.06 (3.3) | 0.02 | 0.00 |
| 24 | 1.00 (1.0) | 1.00 (1.0) | 0.96 (1.0) | 0.78 (1.3) | 0.38 (1.9) | 0.10 | 0.00 |

Every inconsistent run had tasks done twice (10.1 on average) and 86% also left tasks
unassigned although capacity remained. Each group allocates every task it hears of.
Bigger teams tolerate shorter ranges only because they are denser. Scoped ED-CBBA looks
slightly better, but only because its consistency covers just its local group.

## 2. Lost messages break ED-CBBA as soon as the network is sparse
Barely connected network (range = connectivity threshold), 24 robots. Consistency /
mean broadcasts:

| Loss | Standard CBBA | ED-CBBA | ED + refresh/5 | Scoped ED |
| ---: | --- | --- | --- | --- |
| 0.0 | 1.00 / 762 | 1.00 / 234 | 1.00 / 335 | 1.00 / 194 |
| 0.1 | 1.00 / 779 | 0.76 / 231 | 1.00 / 339 | 0.76 / 190 |
| 0.2 | 1.00 / 802 | 0.46 / 237 | 1.00 / 356 | 0.54 / 200 |
| 0.3 | 1.00 / 828 | 0.22 / 237 | 0.98 / 369 | 0.30 / 202 |
| 0.4 | 1.00 / 863 | 0.06 / 244 | 0.82 / 391 | 0.16 / 207 |
| 0.6 | 1.00 / 971 | 0.02 / 232 | 0.42 / 457 | 0.04 / 207 |

ED-CBBA sends nothing once its lists stop changing, so a lost message is never repaired.
Its broadcast count stays flat as loss rises, which is the failure. A refresh every 5
rounds holds to 30% loss at ~45% of standard CBBA's broadcasts. Standard CBBA never broke
at 24 robots. With full communication only small auctions break (6 robots at 50% loss;
the scoped method's small local groups at 40–60%).

## 3. Mass failure: tasks lost exactly when capacity is tight
Tasks lost although capacity remained, after a quarter of the team fails: 1.4 per run at
12 robots (success 0.28) and 2.4 at 24 (success 0.16). At 40–60% failed, capacity is the
limit and CBBA fills it (success ~1.0). The cause is the type-blind greedy bidding found in
Experiment 3: robots fill slots with shared tasks that another type could do, stranding
type-only tasks. Scoped recovery is never local once ≥ 10% of the team fails (more than
4 affected tasks).

## 4. Late or missing failure news
- **Never told** (any fraction < 1): consistency 0% at every team size. No duplicate work,
  but 37% of those runs leave a task unassigned although capacity remained.
- **Told late** (half the team after d rounds): standard CBBA and ED + refresh always
  recover, taking about d + 2 rounds. ED-CBBA fails in 14–18% of runs once d ≥ 5. The
  late robots keep an outdated winner for the failed robot's tasks (a robot that briefly
  claimed one during the early re-auction). The robots that know the final winner no
  longer change their lists, so ED-CBBA never re-sends it. 88% of these runs had tasks
  claimed twice. Cost of waiting at d = 20, 24 robots: CBBA 995 broadcasts, ED 101,
  ED + refresh 275.

## What this means for the proposal
- Periodic refresh is necessary for ED-CBBA under both packet loss and delayed failure
  news. Refresh every 5 rounds costs 1.4–2.7× ED's broadcasts (24 robots) but stays at
  28–47% of standard CBBA's.
- No method survives a network split: partition detection or merge-time reconciliation
  is needed, which none of the methods has.
- Successful termination says nothing about correctness here; a consistency check
  (e.g. a final hash exchange) would turn silent failures into detected ones.
- Type-blind bidding loses tasks precisely when capacity is tight: a capability-aware bid
  (penalise using a scarce type on a task another type could do) is a concrete fix to test.

## Caveats
- Initial allocation always uses full communication, isolating the re-auction.
- Stale sweeps use an orphan-release re-auction from existing beliefs; the other sweeps use
  a full reset with +10% incumbency bonus. Broadcast counts are not comparable across them.
- "Never told" is a worst case: no failure detector at all for those robots.
