# Rules

## Use
- pandas / scikit-learn for all ML; HistGradientBoosting as the main model (handles NaN and imbalance).
- osmnx / geopandas for GIS; Planetary Computer NAIP for imagery (public domain).
- Temporal split + spatial-block CV. Never a plain random split for metro experiments.
- Neighborhood features only from accidents that ENDED before the target accident STARTED.

## Avoid
- Writing the raw 3 GB CSV or raw image chips to disk (the machine has under 1 GB free).
- Duplicating torch in the venv (use the system torch 2.13 and torchvision 0.28).
- Leaky features: Description, Distance(mi), End_Time-derived values as predictors of severity.
- Causal language for anomalies; they are leads for investigation.

## Error handling
Fail loudly. Stages are cached parquet files; delete one to recompute that stage.

## Boundaries for AI
Don't delete data/processed caches or user caches without asking. Don't add dependencies that
duplicate installed ones. Update memory.md and pahses.md after each stage.
