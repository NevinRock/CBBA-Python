# Experiment 1: Homogeneous - results and reproduction

The formal run contains 270 method outcomes: 30 paired seeds at each of
6, 12 and 24 robots. Each pair shares one initial allocation and one assigned
robot failure before execution. Local attempts and global fallbacks are both
counted. Parameters are in [the root configuration](../../config_homogeneous_scenario.json).

## Results

- [Complete English report](final_report.md)
- [All seven required metrics](figures/all_seven_metrics.png)
- [All 270 trials](trials.csv)
- [Mean, SD, median, min/max, sample counts and intervals](summary_statistics.csv)
- [Paired method comparisons](paired_comparisons.csv) and [seed-level differences](paired_seed_differences.csv)
- [Recovery/fallback summary](fallback_summary.csv) and [all failed local attempts](fallback_attempts.csv)
- [Independent audit](independent_audit.json), [verification](verification.json), and [provenance](run_provenance.json)
- [Candidate file inventory](submission_manifest.json)

Seven PNG files are retained: one overview containing all seven required
metrics and the six auxiliary figures referenced by the report. Redundant
individual copies of the seven overview panels are omitted.

## Verify the saved run without executing auctions

From the repository root, using Python 3.13.5 and dependencies in the existing
`requirements.txt` (the exact run environment is also in [environment-freeze.txt](environment-freeze.txt)):

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s test -p 'test_*.py' -v
.\.venv\Scripts\python.exe test/audit_homogeneous_results.py --output-dir doc/homogeneous
.\.venv\Scripts\python.exe test/analyze_homogeneous_results.py --output-dir doc/homogeneous
```

The first command includes ordinary small unit fixtures. The last two read
saved evidence only and never execute CBBA or repeat the 270 formal outcomes.
Analysis regenerates five derived CSV statistics/comparison files, seven figures
and the report, preserving `trials.csv` and the compressed evidence bytes.

For a new experiment, use a **new empty output directory**:

```powershell
.\.venv\Scripts\python.exe test/run_homogeneous_experiment.py --full --output-dir outputs/homogeneous_reproduction
```

The runner's default is a 27-row smoke run. The full command above is explicit
and is separate from auditing the saved data. Runtime is subject to machine
and execution-order noise; deterministic non-timing observations are reproducible.

## Why one compressed evidence file is included

CSV alone can reproduce numerical summaries, but cannot independently verify
physical schedules, common initial allocations or solver beliefs. The minimal
supplement is [audit_evidence.jsonl.gz](audit_evidence.jsonl.gz), a deterministic
gzip-compressed JSONL container, **not a ZIP of the outputs directory**. It holds:

- all 90 original input snapshots and 270 method diagnostics;
- the four runner evidence files and their public checksum inventory;
- preflight metadata and exactly the 13 historical source/document
  witnesses needed to check execution-time SHA-256 values.

The public metadata omits the original machine-local configuration and Python
executable paths. The scientific records and source witnesses retain their exact
bytes. There are 379 entries. Every entry has a relative path, bytes encoded in
base64, and SHA-256. The reader rejects unsafe/duplicate paths or hash failures,
expands into a temporary directory, and verifies that the visible `trials.csv`
matches the evidence after normalising line endings. No permanent extraction or local `outputs/` dependency
is required. Frozen source witnesses are not imported or executed during audit.

Omitting this roughly 2 MB supplement would leave only the historical audit
certificate and numerical re-analysis, **not independent schedule/consensus
verification**. The smallest complete supplement under the retained auditor
schema is this evidence file; the complete 418-file outputs directory and a
full ZIP are unnecessary.

## Provenance and audit scope

The run used base commit `41d1ceb8a8c27b5759b69d66ba5a6b3b0c23c93e`.
Experiment files were uncommitted at execution time. Exact executed witnesses
and their hashes remain in the evidence; current delivery-script hashes are
recorded separately. No experiment logic, core algorithm or numerical result
was changed when preparing this compact delivery.

The audit verifies every actual auction's participants against their paths,
winning bids and physical schedules. Successful local results combine that
consensus with unchanged outsider schedules; mission-wide dissemination to
nonparticipants is outside the model. Runtime, quiet stopping tails, additional
discount/bonus assumptions and communication accounting limits are disclosed
in the report.

The complete local formal and smoke outputs, all original diagnostics and
logs are retained outside this candidate file set. They are deliberately not
part of the proposed Git submission. No extra raw records or ZIP are needed
to audit this compact candidate.
