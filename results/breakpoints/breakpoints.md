# Breaking points

First stress level at which a method's rate drops below 90% / below 50% of runs (`-` = never within the tested range). **Success** = robots agree, no task claimed twice, auction ended by itself, and no task lost while capacity remained. **Consistent** = the first three only.

## Fixed radio range (smaller range = more likely the failure splits the team)

Levels in stress order: full, 80, 60, 50, 40, 35, 30, 25, 20, 15. 50 seeds. Details: [`split/summary.md`](split/summary.md).

| group | robots | method | success <90% | success <50% | consistent <90% | consistent <50% |
| --- | ---: | --- | --- | --- | --- | --- |
| - | 6 | Standard CBBA | full | 60 | 60 | 50 |
| - | 6 | ED-CBBA | full | 60 | 60 | 50 |
| - | 6 | ED-CBBA + refresh/5 | full | 60 | 60 | 50 |
| - | 6 | Scoped ED-CBBA (40 m) | full | 60 | 60 | 50 |
| - | 12 | Standard CBBA | 40 | 40 | 40 | 40 |
| - | 12 | ED-CBBA | 40 | 40 | 40 | 40 |
| - | 12 | ED-CBBA + refresh/5 | 40 | 40 | 40 | 40 |
| - | 12 | Scoped ED-CBBA (40 m) | 40 | 35 | 40 | 35 |
| - | 24 | Standard CBBA | 35 | 30 | 35 | 30 |
| - | 24 | ED-CBBA | 35 | 30 | 35 | 30 |
| - | 24 | ED-CBBA + refresh/5 | 35 | 30 | 35 | 30 |
| - | 24 | Scoped ED-CBBA (40 m) | 35 | 25 | 35 | 25 |

## Packet loss on networks of different sparseness

Levels in stress order: 0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6. 50 seeds. Details: [`loss_sparse/summary.md`](loss_sparse/summary.md).

| group | robots | method | success <90% | success <50% | consistent <90% | consistent <50% |
| --- | ---: | --- | --- | --- | --- | --- |
| full communication | 6 | Standard CBBA | 0.0 | - | - | - |
| full communication | 6 | ED-CBBA | 0.0 | 0.4 | 0.5 | - |
| full communication | 6 | ED-CBBA + refresh/5 | 0.0 | 0.6 | 0.6 | - |
| full communication | 6 | Scoped ED-CBBA (40 m) | 0.0 | 0.3 | 0.4 | - |
| full communication | 12 | Standard CBBA | - | - | - | - |
| full communication | 12 | ED-CBBA | - | - | - | - |
| full communication | 12 | ED-CBBA + refresh/5 | - | - | - | - |
| full communication | 12 | Scoped ED-CBBA (40 m) | 0.4 | - | 0.4 | - |
| full communication | 24 | Standard CBBA | - | - | - | - |
| full communication | 24 | ED-CBBA | - | - | - | - |
| full communication | 24 | ED-CBBA + refresh/5 | - | - | - | - |
| full communication | 24 | Scoped ED-CBBA (40 m) | 0.6 | - | 0.6 | - |
| range = 1.5x connectivity threshold | 6 | Standard CBBA | 0.0 | - | - | - |
| range = 1.5x connectivity threshold | 6 | ED-CBBA | 0.0 | 0.4 | 0.4 | 0.6 |
| range = 1.5x connectivity threshold | 6 | ED-CBBA + refresh/5 | 0.0 | 0.5 | 0.5 | - |
| range = 1.5x connectivity threshold | 6 | Scoped ED-CBBA (40 m) | 0.0 | 0.3 | 0.4 | 0.6 |
| range = 1.5x connectivity threshold | 12 | Standard CBBA | - | - | - | - |
| range = 1.5x connectivity threshold | 12 | ED-CBBA | 0.3 | - | 0.3 | - |
| range = 1.5x connectivity threshold | 12 | ED-CBBA + refresh/5 | 0.6 | - | 0.6 | - |
| range = 1.5x connectivity threshold | 12 | Scoped ED-CBBA (40 m) | 0.3 | 0.6 | 0.3 | 0.6 |
| range = 1.5x connectivity threshold | 24 | Standard CBBA | - | - | - | - |
| range = 1.5x connectivity threshold | 24 | ED-CBBA | 0.4 | 0.6 | 0.4 | 0.6 |
| range = 1.5x connectivity threshold | 24 | ED-CBBA + refresh/5 | - | - | - | - |
| range = 1.5x connectivity threshold | 24 | Scoped ED-CBBA (40 m) | 0.3 | 0.6 | 0.3 | 0.6 |
| range = 1.0x connectivity threshold | 6 | Standard CBBA | 0.0 | 0.4 | 0.4 | - |
| range = 1.0x connectivity threshold | 6 | ED-CBBA | 0.0 | 0.1 | 0.1 | 0.3 |
| range = 1.0x connectivity threshold | 6 | ED-CBBA + refresh/5 | 0.0 | 0.2 | 0.2 | 0.4 |
| range = 1.0x connectivity threshold | 6 | Scoped ED-CBBA (40 m) | 0.0 | 0.1 | 0.1 | 0.3 |
| range = 1.0x connectivity threshold | 12 | Standard CBBA | 0.6 | - | 0.6 | - |
| range = 1.0x connectivity threshold | 12 | ED-CBBA | 0.1 | 0.3 | 0.1 | 0.3 |
| range = 1.0x connectivity threshold | 12 | ED-CBBA + refresh/5 | 0.3 | 0.5 | 0.3 | 0.5 |
| range = 1.0x connectivity threshold | 12 | Scoped ED-CBBA (40 m) | 0.1 | 0.3 | 0.1 | 0.3 |
| range = 1.0x connectivity threshold | 24 | Standard CBBA | - | - | - | - |
| range = 1.0x connectivity threshold | 24 | ED-CBBA | 0.1 | 0.2 | 0.1 | 0.2 |
| range = 1.0x connectivity threshold | 24 | ED-CBBA + refresh/5 | 0.4 | 0.6 | 0.4 | 0.6 |
| range = 1.0x connectivity threshold | 24 | Scoped ED-CBBA (40 m) | 0.1 | 0.3 | 0.1 | 0.3 |

## Fraction of the team failing at once

Levels in stress order: one, 0.1, 0.25, 0.4, 0.5, 0.6. 50 seeds. Details: [`mass_failure/summary.md`](mass_failure/summary.md).

| group | robots | method | success <90% | success <50% | consistent <90% | consistent <50% |
| --- | ---: | --- | --- | --- | --- | --- |
| - | 6 | Standard CBBA | one | - | - | - |
| - | 6 | ED-CBBA | one | - | - | - |
| - | 6 | ED-CBBA + refresh/5 | one | - | - | - |
| - | 6 | Scoped ED-CBBA (40 m) | one | - | - | - |
| - | 12 | Standard CBBA | 0.25 | 0.25 | - | - |
| - | 12 | ED-CBBA | 0.25 | 0.25 | - | - |
| - | 12 | ED-CBBA + refresh/5 | 0.25 | 0.25 | - | - |
| - | 12 | Scoped ED-CBBA (40 m) | 0.25 | 0.25 | - | - |
| - | 24 | Standard CBBA | 0.25 | 0.25 | - | - |
| - | 24 | ED-CBBA | 0.25 | 0.25 | - | - |
| - | 24 | ED-CBBA + refresh/5 | 0.25 | 0.25 | - | - |
| - | 24 | Scoped ED-CBBA (40 m) | 0.25 | 0.25 | - | - |

## Fraction of survivors that ever learn of the failure

Levels in stress order: 1.0, 0.9, 0.75, 0.5, 0.25. 50 seeds. Details: [`stale_never/summary.md`](stale_never/summary.md).

| group | robots | method | success <90% | success <50% | consistent <90% | consistent <50% |
| --- | ---: | --- | --- | --- | --- | --- |
| - | 6 | Standard CBBA | 1.0 | 0.9 | 0.9 | 0.9 |
| - | 6 | ED-CBBA | 1.0 | 0.9 | 0.9 | 0.9 |
| - | 6 | ED-CBBA + refresh/5 | 1.0 | 0.9 | 0.9 | 0.9 |
| - | 12 | Standard CBBA | 0.9 | 0.9 | 0.9 | 0.9 |
| - | 12 | ED-CBBA | 0.9 | 0.9 | 0.9 | 0.9 |
| - | 12 | ED-CBBA + refresh/5 | 0.9 | 0.9 | 0.9 | 0.9 |
| - | 24 | Standard CBBA | 0.9 | 0.9 | 0.9 | 0.9 |
| - | 24 | ED-CBBA | 0.9 | 0.9 | 0.9 | 0.9 |
| - | 24 | ED-CBBA + refresh/5 | 0.9 | 0.9 | 0.9 | 0.9 |

## Rounds before the second half of the team learns of the failure

Levels in stress order: 1, 2, 5, 10, 20. 50 seeds. Details: [`stale_delay/summary.md`](stale_delay/summary.md).

| group | robots | method | success <90% | success <50% | consistent <90% | consistent <50% |
| --- | ---: | --- | --- | --- | --- | --- |
| - | 6 | Standard CBBA | 1 | - | - | - |
| - | 6 | ED-CBBA | 1 | 5 | 5 | - |
| - | 6 | ED-CBBA + refresh/5 | 1 | - | - | - |
| - | 12 | Standard CBBA | - | - | - | - |
| - | 12 | ED-CBBA | 5 | - | 5 | - |
| - | 12 | ED-CBBA + refresh/5 | - | - | - | - |
| - | 24 | Standard CBBA | - | - | - | - |
| - | 24 | ED-CBBA | 5 | - | 5 | - |
| - | 24 | ED-CBBA + refresh/5 | - | - | - | - |

