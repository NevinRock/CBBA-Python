# 0004: Methods compared, and how the comparison is kept fair

**Status:** Accepted, 2026-11-20

**Methods.** The same three as the existing spatial experiment: global standard CBBA,
global ED-CBBA, and ED-CBBA scoped to 40 m with a global ED fallback (local attempt
only for ≤ 4 affected tasks; broadcasts of both attempts are counted).

**Bias fixes found in the audit.**

1. *Stopping-rule inflation.* The solver stops only after N quiet rounds; standard CBBA
   broadcasts through those, ED-CBBA does not. We report both counts and lead with
   `broadcasts_to_converge` (through the last round in which any robot's winner or
   bid list changed). The solver records `last_change_round`; the algorithm is unchanged.
2. *Tie-break bias.* CBBA breaks equal bids in favour of the lower robot ID
   (`lib/CBBA.py`, consensus table). Robot IDs were grouped by type (air first), which
   would hand ties to air robots. Robot and task IDs are now shuffled per seed.
3. *Duration-blind measures.* CBBA's score depends only on start times. Measures that see
   duration were added: mission completion time (`makespan_s`) and total robot time
   on shared tasks (`shared_busy_s`).
4. *Duplicates and consensus* are recorded as outcomes (`duplicate_tasks`,
   `consensus_ok`) instead of crashing the run.

**Known remaining advantages of the scoped method (reported, not corrected).**
- It assumes robots know each other's positions, and no broadcast is charged for the
  failure announcement (also not charged to the global methods).
- Robots outside the local auction keep their plans by construction, so it will
  always show fewer changed owners. Read `changed_owners` with that in mind.
