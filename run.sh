#!/usr/bin/env bash
# GeoCrashAI end-to-end pipeline. Each stage caches its outputs in data/processed/.
set -euo pipefail
cd "$(dirname "$0")"
PY=.venv/bin/python
if [ ! -x "$PY" ]; then
  uv venv --python 3.14 --system-site-packages .venv
  uv pip install --python "$PY" -r requirements.txt
fi
$PY -m tests.test_features
[ -f data/processed/metro.parquet ] || $PY -m src.ingest     # stream 7.7M-row CSV -> parquet subsets
$PY -m src.build_metro                                       # OSM GIS + NAIP imagery + neighborhood
$PY -m src.models                                            # RQ1/RQ2/RQ5 baselines + ablation
$PY -m src.discovery                                         # RQ3/RQ4 regimes, hotspots, anomalies, map
