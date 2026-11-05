#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"
export MPLBACKEND=QtAgg
exec .venv/bin/python test/run_cbba_example_01.py
