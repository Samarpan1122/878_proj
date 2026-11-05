# GeoCrashAI

An auditable road-safety screening workspace, with an independent research explorer.

## Public real-data website

**Live: https://geocrash-666321636483.us-central1.run.app** (Cloud Run revision `geocrash-00004-xag`, deployed 2026-11-05)

| Page | What it does |
|---|---|
| [Map](https://geocrash-666321636483.us-central1.run.app/) | 3D map of FARS fatal crashes 2021–2024 with a satellite view. Type any US address to fly there and see every fatal crash nearby as a pin, with per-crash details (date, road, collision, light, weather, vehicles). |
| [Data](https://geocrash-666321636483.us-central1.run.app/explore/) | State and year totals, the 2025 state projection, state ranking, yearly trend and recorded crash factors. |
| [Road screening](https://geocrash-666321636483.us-central1.run.app/screening/) | Nebraska road segments ranked by excess fatal crashes, a future-traffic projection and a treatment budget comparison. |
| [Analysis](https://geocrash-666321636483.us-central1.run.app/notebook/) | The complete course notebook (EDA, classification, regression, time series, clustering) with a .ipynb download. |
| [API docs](https://geocrash-666321636483.us-central1.run.app/docs) | OpenAPI for the public endpoints, including `GET /api/public/crashes?lat=&lng=&r=` ([contract](docs/CRASH_POINTS.md)). |

Per-crash points come from NHTSA FARS (`scripts/build_crash_points.py` → `data/public/crashes.jsonl.gz`); the Analysis page is rebuilt with `uv run --no-project --with markdown python scripts/build_notebook_page.py`. Place search uses Google Places when `GOOGLE_MAPS_API_KEY` is set on the service, otherwise OpenStreetMap Nominatim. See the [public deployment guide](docs/PUBLIC_DEPLOYMENT.md) for release evidence and operating limits. The 2025 projection is frozen historical inference, not a current forecast.

## Demonstrate and evaluate

Start with the [buyer and pilot package](docs/commercial/README.md): buyer brief, ten-minute demo, pilot scope, claims matrix, diligence evidence, and unsent outreach drafts. The foundation model remains a design proposal.

Use the verified public real-data website for buyer discussions. An optional offline, dataset-free workflow demonstration remains available with 24 fictional corridors:

```bash
.venv/bin/python -m safety.demo --root data/synthetic-demo
GEOCRASH_SAFETY_DATA=data/synthetic-demo .venv/bin/uvicorn safety.api:app --host 127.0.0.1 --port 8893
```

Open http://localhost:8893. The generator refuses to overwrite existing data; reuse the generated directory on subsequent launches. All example observations, predictions and intervals are explicitly synthetic. No real crash records or model-performance claims are included in this demo.

```bash
.venv/bin/python -m safety.release audit --root data/safety --output outputs/releases/readiness.json --require-technical
.venv/bin/python -m safety.release bundle --output outputs/releases/geocrash-evaluation.zip
```

The evaluation ZIP contains allowlisted code, documentation, deployment files and a synthetic generator with a SHA-256 manifest. It excludes real datasets, credentials and research weights. Its startup instructions work from an extracted directory. A passing technical audit does not grant commercial data/software rights or agency acceptance. See [procurement gates](docs/PROCUREMENT.md) and [operations](docs/OPERATIONS.md).

The **safety engine** uses official FARS fatal-crash records and Nebraska DOT road traffic counts. It builds a complete road-by-year panel, estimates exposure, fits an experimental negative-binomial safety performance function, and ranks roads with Empirical Bayes expected and excess fatal-crash frequency. A sourced countermeasure calculator makes eligibility, costs, severity transfer and statistical-fatality valuation explicit.

The **research explorer** retains the original classification, regression, forecasting, clustering, imagery, EDA, outliers and illustrative replay. Its noncommercial dataset and trained models are separate from the safety engine and excluded from the deployment image.

## Run locally

```bash
uv pip install --python .venv/bin/python -r requirements-safety.txt -r requirements-test.txt
# Official downloads; existing research caches are never overwritten:
.venv/bin/python -m safety.cli ingest --years 2021 2022 2023 2024
.venv/bin/python -m safety.cli build
.venv/bin/python -m safety.cli refresh-feeds
.venv/bin/uvicorn safety.api:app --host 127.0.0.1 --port 8891
```

Open http://localhost:8891 for safety screening and `/docs` for the OpenAPI interface. Use `.venv/bin/python -m web.server` for the integrated local research explorer on port 8878, with the screening workspace at `/safety.html`. Research models load only when their endpoints are requested.

## What is implemented

- Official FARS ZIP ingestion with source hashes, year/schema checks and missing-coordinate reporting.
- Paginated NDOT AADT road ingestion and a separate agency CSV staging path with documented provenance.
- Conservative metric road linkage; ambiguous and distant crashes remain in the audit, never assigned arbitrarily.
- Zero-crash roads, calendar-day vehicle-mile exposure, explicit traffic-vintage proxies, and no rates without valid denominators.
- Local NB safety performance function, temporal and geographic holdouts, exposure-only baseline, EB frequency/excess and conditional 95% intervals.
- Outcome-free road context, Poisson boosting and a learned expert mixture, with nested development comparisons and paired geographic uncertainty.
- Official FARS speeding, reported alcohol and distraction cohorts with explicit unknown/not-applicable denominators.
- FHWA CMF 4737 cost-benefit scenarios and USDOT statistical-fatality valuation in stated dollar years.
- NOAA weather snapshots, freshness checks, authorized GeoJSON incident adapter, drift reports and candidate retraining.
- FastAPI validation, atomic snapshots, tests, CI, optional transactional PostGIS, Docker, Google Cloud deployment and scheduled-job support.
- Pilot protocol and a reproducible study report. No agency partnership or demonstrated treatment effect is claimed.

## Before operational or commercial use

The current NDOT traffic feed is a **2025 vintage**. Rates against older FARS years are explicitly **proxies**, not verified historical risk. Road facility types and historical geometry are not complete; the SPF is experimental, not an HSM-calibrated agency model. Fatal-crash-only data cannot train an all-crash injury-severity classifier. The pipeline preserves the distinction.

FARS is federal public data. NDOT’s publisher policy supports informational use at the user’s risk; blanket commercial redistribution rights remain unconfirmed and the API rejects commercial export. Agency-wide crash records, historical exposure, permitted 511 access and a real pilot partner remain external prerequisites.

## Documentation

- [Proposed foundation model architecture, training plan and research hypotheses](docs/FOUNDATION_ARCHITECTURE.md) — design only; no foundation checkpoint has been trained.
- [Engine methods and generated study](docs/SAFETY_ENGINE.md)
- [Advanced models, measured results and behavioral analysis](docs/ADVANCED_MODELS.md)
- [Omaha study: corrected GIS, data drift and monthly adaptation](docs/OMAHA_STUDY.md)
- [Deployment and operations](docs/OPERATIONS.md)
- [Omaha–Lincoln pilot protocol](docs/PILOT.md)
- [Original research design](README_GeoCrashAI.md)
- [Session handoff](SESSION_HANDOFF.md)

Run `.venv/bin/python -m pytest tests/test_safety*.py --cov=safety --cov-fail-under=80` for the independent engine checks. The coverage threshold applies to the safety package, not the historical research codebase.

Software licensing has not been selected by the owner. Third-party data, imagery and models retain their respective terms; no blanket commercial license is implied.

## Agency planning workspace

`/planning/` adds budget-constrained treatment scenarios, analyst-time economics, descriptive before/after evaluation, evidence exports, conditional future traffic projections, coordinate matching audits, and route comparison. See [methods and API](docs/AGENCY_PLANNING.md). Financial and predictive results remain explicitly conditional; connected live traffic and agency validation are not claimed.
