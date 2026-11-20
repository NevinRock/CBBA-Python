#!/usr/bin/env bash
# Smoke test for Experiment 3: run before any full experiment run.
#   1. unit tests (existing + type-dependent duration + exp3 invariants)
#   2. 2 seeds x every team size x every condition x failure mode x method
#   3. analysis + cross-condition overview on the smoke output
# Usage: scripts/smoke_exp3.sh [python] [jobs]
set -euo pipefail
cd "$(dirname "$0")/.."
PY="${1:-.venv/bin/python}"
JOBS="${2:-4}"
OUT="results/exp3_shared_smoke"
export PYTHONPATH=".:lib:test" MPLBACKEND=Agg

echo "== 1/3 unit tests"
"$PY" -m unittest discover -s test -t . 2>&1 | tail -3

echo "== 2/3 smoke run -> $OUT"
rm -rf "$OUT"
"$PY" test/run_exp3_shared.py --smoke --conditions all --jobs "$JOBS" --out-root "$OUT"

echo "== 3/3 analysis"
for dir in "$OUT"/*/; do
  "$PY" test/analyse_exp3.py "$dir"
done
"$PY" test/overview_exp3.py "$OUT"

expected=$("$PY" -c "from test.run_exp3_shared import CONDITIONS, METHODS
print(sum(3 * 2 * len(c['failure_modes']) * len(METHODS) for c in CONDITIONS.values()))")
rows=0
for f in "$OUT"/*/trials.csv; do rows=$((rows + $(wc -l < "$f") - 1)); done
if [ "$rows" -ne "$expected" ]; then
  echo "SMOKE FAIL: expected $expected trial rows, got $rows"; exit 1
fi
echo "SMOKE OK: $rows trial rows across $(ls -d "$OUT"/*/ | wc -l | tr -d ' ') conditions"
