# 0008: Breaking-point sweeps (Experiment 3B)

**Status:** Accepted, 2026-11-20. Code: `test/run_breakpoints.py`, `test/analyse_breakpoints.py`,
`scripts/smoke_breakpoints.sh`, tests in `test/test_breakpoints.py`.

**Goal.** Find the stress level at which each re-auction method stops working, one
stressor at a time, on Experiment 3 missions (balanced air/ground, shared tasks).

**Fixed across sweeps.** 6/12/24 robots, 50 seeds, one common initial ED-CBBA allocation
with full communication (isolates the re-auction), failure before execution, the same
failed robot(s), radio range, packet-loss draws and inform times for every method.

| Sweep | Stress levels (increasing) | Methods |
| --- | --- | --- |
| `split` | fixed radio range: full, 80, 60, 50, 40, 35, 30, 25, 20, 15 m | 4 |
| `loss_sparse` | loss 0–0.6 × range {full, 1.5×, 1.0× connectivity threshold} | 4 |
| `mass_failure` | 1 robot, 10, 25, 40, 50, 60% of the team at once | 4 |
| `stale_never` | fraction of survivors ever told: 1.0, 0.9, 0.75, 0.5, 0.25 | 3 (no scoped) |
| `stale_delay` | half told at once, the rest after 1, 2, 5, 10, 20 rounds | 3 (no scoped) |

Methods: standard CBBA, ED-CBBA, ED-CBBA with a full refresh every 5 rounds, scoped
ED-CBBA (40 m). Fully reset re-auction with +10% incumbency bonus, except the stale
sweeps.

**Success** = robots agree, no task claimed twice, the auction ended by itself (cap 500
rounds), and no task lost while capacity remained (time never binds, so free slots per
type bound the assignable tasks). **Consistent** = the first three only. **Breaking
point** = first level with success (or consistency) below 90%, and below 50%.

**Stale-belief model.** Solver changes in `lib/CBBA.py`, all off by default:
`failed_agents` (dead robots stay in the belief lists but never bid or broadcast),
`warm_start` (robots start from the converged pre-failure lists and plans), and
`inform_round` (when each robot releases the failed robot's tasks). This is an
*orphan-release* re-auction, not a full reset, so stale sweeps are not directly
comparable with the other sweeps' broadcast counts. Scoped recovery is excluded because
"who knows" is the sweep variable.

**Known effect of CBBA's timestamps.** A dead robot never produces newer information, so
its stale winning bids cannot spread back to robots that have released them (consensus
table entries 9 and 13 require newer timestamps). Expected failure: uninformed robots
disagree forever, and tasks that only they would take stay unassigned.

**Scoped consistency** counts only the robots in the local auction; robots outside it
are not modelled as learning the new owners.
