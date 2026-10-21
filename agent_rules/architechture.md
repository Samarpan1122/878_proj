# Architecture

## Proposed foundation model direction (2026-09-29)

The user requested a new from-scratch deep-learning architecture inspired by OpenJEV and additional ideas. The detailed proposal is [docs/FOUNDATION_ARCHITECTURE.md](../docs/FOUNDATION_ARCHITECTURE.md), with a non-executable design configuration at [configs/foundation/roadworld_scratch.json](../configs/foundation/roadworld_scratch.json).

It proposes a roughly 50–55M dense multimodal road encoder, JEPA self-supervision, exposure-offset count and censored-duration heads, an optional measured-motion branch, and a typed decision scorer. OpenJEV is a distinct noncommercial Qwen-derived decision model, not JEPA; its weights are not part of the proposed commercial lineage. The existing engine below is implemented; the proposed `roadworld/` package and foundation training are not yet implemented. Preserve this distinction.

## Independent safety stack (2026-09-29)
`safety.cli ingest` -> official FARS + NDOT adapters -> immutable source provenance ->
`safety.cli build` -> full road-year panel -> local NB SPF + validation -> EB screening -> atomic `snapshot.json`.
`safety.api` serves the new screening page, read-only evidence and scenario calculator.
The local `web.server` opts into lazy legacy research routes; production never enables those routes or packages legacy data/models.
`safety.feeds`, `monitoring`, and `cloud_job` handle timestamped NOAA/authorized incident snapshots, drift review, and GCS-generation-safe candidate jobs.
Optional `database` mirrors artifacts into PostGIS; `warehouse` exports private BigQuery GIS tables.
Cloud Run serves private snapshots; separate service accounts run scheduled weather/candidate work. See docs/OPERATIONS.md.

## App flow
```
run.sh
 ├─ tests/test_features.py        self-checks (cleaning, leakage-safe neighborhood, NDVI fractions)
 ├─ src/ingest.py                 stream Kaggle US_Accidents_March23.csv (HF mirror) -> parquet subsets
 ├─ src/build_metro.py            Omaha metro + Lincoln: clean -> OSM GIS -> NAIP imagery -> neighborhood
 │    ├─ src/features.py          cleaning, duration target, temporal, neighborhood, temporal split
 │    ├─ src/gis.py               OSMnx road graph + land-use polygons, 100/250/500 m buffers
 │    └─ src/imagery.py           Planetary Computer NAIP chips -> NDVI fractions + ResNet-18 embeddings
 ├─ src/models.py                 national baselines; metro ablation A–E (temporal + spatial-block CV)
 └─ src/discovery.py              KMeans regimes, image regimes, HDBSCAN hotspots, O/E anomalies, folium map
```

## Folder structure
- `src/` pipeline code (one module per stage)
- `tests/` runnable self-checks
- `data/processed/` parquet artifacts (gitignored, regenerable)
- `outputs/{tables,figures,maps,reports}/` results

## Tech stack
Python 3.14, pandas, scikit-learn (HistGradientBoosting, RF, logistic/ridge, KMeans, HDBSCAN),
geopandas + osmnx (OpenStreetMap), rasterio + pystac-client + planetary-computer (NAIP),
torch/torchvision (ResNet-18 embeddings on Apple MPS), folium (map).
