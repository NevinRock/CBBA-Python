# 0005: Type-dependent task duration

**Status:** Accepted, 2026-11-20

**Decision.** `Task.duration_by_agent_type` (optional `{agent_type: seconds}`) with
`Task.duration_for(agent_type)`; every use of `task.duration` in `lib/CBBA.py` (scoring
and plots) now asks for the executing robot's duration. Tasks without the override are
unchanged, so existing experiments and tests behave as before.

**Tests.** `test/test_type_dependent_duration.py`.

**Observation.** The CBBA score depends on start time only, so a task's own duration
affects bids only through the tasks queued after it in the same bundle. CBBA therefore has
no direct pressure to give shared tasks to the faster ground robots. Experiment 3 measures
whether this matters.
