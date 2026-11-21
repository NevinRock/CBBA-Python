# Research log

Decisions and run logs for the CBBA experiments.

- `decisions/NNNN-short-name.md`: context, decision, reasons, alternatives. Numbered in the
  order made; a superseded decision stays, marked *Superseded by NNNN*.
- `findings/`: what the results show, with the numbers behind each claim.
- `logs/YYYY-MM-DD-short-name.md`: what was run, where, on which code, how long it took,
  where the output is, what was noticed.

## Decisions

| # | Decision |
| --- | --- |
| [0001](decisions/0001-incumbency-bonus.md) | Keep the +10% incumbency bonus |
| [0002](decisions/0002-time-window.md) | Every task may start anywhere in [0, 240] s |
| [0003](decisions/0003-failure-selection.md) | Which robots fail, and when |
| [0004](decisions/0004-methods-and-fairness.md) | Methods, and the bias fixes that keep them fair |
| [0005](decisions/0005-type-dependent-duration.md) | Type-dependent task duration |
| [0006](decisions/0006-stress-conditions.md) | Stress conditions, one factor at a time |
| [0007](decisions/0007-compute.md) | Run on `vanilla`, CPU multiprocessing |
| [0008](decisions/0008-breaking-point-sweeps.md) | Breaking-point sweeps and the stale-belief model |

## Logs

| Date | Log |
| --- | --- |
| 2026-11-20 | [Experiment 3 setup and local smoke test](logs/2026-11-20-exp3-setup-and-smoke.md) |
| 2026-11-20 | [Experiment 3 full run, all conditions](logs/2026-11-20-exp3-full-run.md) |
| 2026-11-20 | [Experiment 3B breaking-point run](logs/2026-11-20-exp3b-breakpoints-run.md) |

## Findings

- [Experiment 3: baseline and stress conditions](findings/exp3-baseline-and-stress.md)
- [Experiment 3: where the algorithms break (exploratory probes)](findings/exp3-breaking-points-probe.md), superseded by:
- [Experiment 3B: breaking points of failure re-auction](findings/exp3b-breaking-points.md)
