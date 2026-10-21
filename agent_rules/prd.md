# PRD — GeoCrashAI

## What to build
A reproducible pipeline testing whether explicit geospatial context (OSM GIS buffers, NAIP aerial imagery,
leakage-safe neighborhood history) improves traffic-accident severity and duration modeling beyond
conventional accident and weather variables, plus unsupervised regime, hotspot and anomaly discovery.
See README_GeoCrashAI.md for the full research design (RQ1–RQ5).

## Target users
CSCE 878 course project team, instructors and reviewers; later, transportation-safety analysts.

## Features
- National tabular baselines (severity classification, duration regression)
- City-scale (Omaha metro + Lincoln) multimodal feature table
- Ablation A–E and GIS buffer-scale comparison, under temporal and spatial-block evaluation
- Accident-regime and imagery-regime clustering
- HDBSCAN hotspots split into frequent vs. severe
- Observed-vs-expected severity anomaly cells with scale sensitivity
- Interactive folium GIS map
- Web explorer: search any US location, Google Maps, forecasts, what-if predictions, risk index, regimes, hotspots, time-lapse
