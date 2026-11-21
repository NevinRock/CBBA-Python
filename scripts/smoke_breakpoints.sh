#!/usr/bin/env bash
# Smoke test for the breaking-point sweeps (Experiment 3B). Run before a full run.
#   1. unit tests   2. 2 seeds x every sweep x size x level x method   3. analysis
# Usage: scripts/smoke_breakpoints.sh [python] [jobs]
set -euo pipefail
cd "$(dirname "$0")/.."
PY="${1:-.venv/bin/python}"
JOBS="${2:-4}"
OUT="results/breakpoints_smoke"
export PYTHONPATH=".:lib:test" MPLBACKEND=Agg

echo "== 1/3 unit tests"
"$PY" -m unittest discover -s test -t . 2>&1 | tail -3
echo "== 2/3 smoke run -> $OUT"
rm -rf "$OUT"
"$PY" test/run_breakpoints.py --smoke --jobs "$JOBS" --out-root "$OUT"
echo "== 3/3 analysis"
"$PY" test/analyse_breakpoints.py "$OUT"

expected=$("$PY" -c "from test.run_breakpoints import SWEEPS
print(sum(3 * 2 * len(s['levels']) * len(s['methods']) for s in SWEEPS.values()))")
rows=0
for f in "$OUT"/*/runs.csv; do rows=$((rows + $(wc -l < "$f") - 1)); done
if [ "$rows" -ne "$expected" ]; then echo "SMOKE FAIL: expected $expected rows, got $rows"; exit 1; fi
echo "SMOKE OK: $rows rows"
