# Public real-data deployment

Deployment status: **live and verified anonymously** at [GeoCrash public website](https://geocrash-666321636483.us-central1.run.app). Revision `geocrash-00003-kh4` receives 100% of traffic. Planning calculations and actual route generation passed anonymous verification in [`outputs/releases/agency-planning-cloud-smoke.json`](../outputs/releases/agency-planning-cloud-smoke.json); deployed desktop/mobile checks passed in [`outputs/releases/agency-planning-cloud-browser.json`](../outputs/releases/agency-planning-cloud-browser.json). The public service permits unauthenticated invocation; the separate private safety service remains owner-only.

The public application serves actual historical federal FARS aggregates, executable statistical models, Nebraska road screening, and documented APIs. It is separate from the private `geocrash-safety` service and the local noncommercial research explorer. Public accessibility establishes a working product demonstration, not agency certification, data redistribution clearance, or a validated operational forecasting service.

## What is served

| Route | Function |
|---|---|
| `/` | Full-viewport 3D historical fatal-crash map, state/year filters, city camera presets and links into the engines |
| `/explore/` | National real-data workbench: geographic aggregates, annual comparisons, recorded factors, and model evidence |
| `/explore/#models` | Executable state count model and its held-out evaluation |
| `/screening/` | Nebraska screening, road inspector, executable road prediction, and guarded countermeasure scenarios |
| `/planning/` | Treatment budgets, future AADT scenarios, analyst time, outcome comparison, evidence exports, matching audits and route comparisons |
| `/docs`, `/openapi.json` | Interactive and machine-readable public API documentation |
| `/api/public/meta`, `/api/public/states` | Source periods, hashes, limitations, engine states, and supported jurisdictions |
| `/api/public/summary`, `/api/public/map` | Filterable state-year totals and suppressed geographic cells |
| `/api/public/model` | Count model coefficients, training period, held-out results, and baseline comparison |
| `/api/public/forecast` | GET or POST runtime state-level annual count inference |
| `/api/public/behaviors` | Recorded FARS factors with yes/no/unknown/not-applicable denominators |
| `/api/public/export` | Federal aggregate JSON download with source metadata |
| `/api/safety/segments` | Nebraska screening results with exposure and limitations |
| `/api/safety/segments/{segment_id}/prediction` | Runtime negative-binomial/Empirical Bayes inference for an existing road |
| `/api/safety/benefit-cost` | POST calculation using sourced CMF and explicit eligibility/cost assumptions |
| `/health`, `/ready` | Process health and artifact serving readiness |

The current release contains **153,273 fatal crashes and 166,230 fatalities in 2021–2024 across 50 states and DC**. The national map aggregates into 0.25-degree cells and suppresses state-year cells with fewer than five crashes before pooling. Map totals therefore differ from complete summary totals; missing coordinates are accounted for separately. Both maps show crash burden, not exposure-adjusted risk. The 3D homepage uses square-root-scaled column heights; exact values remain available on selection and in the workbench. City camera presets keep state-level summary results. The local deck.gl 9.1.14 bundle renders local state boundaries without remote map tiles or runtime CDN scripts. Browsers without WebGL can follow the visible fallback to `/explore/`.

The state count engine is Poisson regression with state intercepts and a shared linear year trend. Its held-out 2024 evaluation trains on 2021–2023 and reports MAE **34.82 crashes per jurisdiction**, compared with **41.96** for the previous-year count baseline. The serving parameters are then fitted to 2021–2024 for a **frozen 2025 projection**. Since the current year is 2026, this is historical model inference, not a current or live forecast. One held-out year does not establish prospective operational performance.

The road engine serves **11,048 Nebraska segments**, 44,192 road-years, and historical fatal-crash screening with 2025 AADT exposure proxies. Conservative linkage matched 650 of 835 Nebraska fatal crashes; unmatched and ambiguous records remain in the audit. It is an experimental fitted safety performance function and EB analysis, not a locally validated Highway Safety Manual model. Runtime predictions replay all 11,048 stored road estimates with maximum numerical difference approximately `6.72e-11`.

The proposed RoadWorld foundation model remains **architecture only, untrained**. No OpenJEV, Kaggle-trained, or other noncommercial research weights are bundled in the public image. No training endpoint or user-uploaded model execution is exposed.

## Build the real-data artifact

Run from the repository root using the existing official-source pipeline:

```bash
uv pip install --python .venv/bin/python -r requirements-safety.txt -c requirements-safety.lock
.venv/bin/python -m safety.cli ingest --years 2021 2022 2023 2024
.venv/bin/python -m safety.cli build
.venv/bin/python -m safety.cli benchmark --bootstrap 1000 --spatial-folds 5
# Behavior requires the exact same archives under its expected filenames.
mkdir -p data/safety/behavior-archives
for fars_year in 2021 2022 2023 2024; do
  if [ ! -e "data/safety/behavior-archives/geocrash-fars${fars_year}.zip" ]; then
    ln -s "../raw/FARS${fars_year}.zip" "data/safety/behavior-archives/geocrash-fars${fars_year}.zip"
  fi
done
.venv/bin/python -m safety.cli behavior --archive-dir data/safety/behavior-archives --years 2021 2022 2023 2024
.venv/bin/python -m safety.public_data --source data/safety --output data/public
.venv/bin/python -m safety.release audit --root data/safety --output outputs/releases/public-screening-audit.json --require-technical
.venv/bin/uvicorn safety.public_api:app --host 127.0.0.1 --port 8894
```

If the official-source artifacts and matching `behavior.json` / `advanced-benchmark.json` already exist, start at `safety.public_data`; do not download or rebuild just to serve them. Default ingestion writes `data/safety/raw/FARSYYYY.zip`, while the behavior CLI reads `geocrash-farsYYYY.zip` from its archive directory. The symlinks above bridge those names without duplicating large archives. If ingestion used an existing `--archive-dir`, pass that same directory to `behavior` instead and omit this symlink step. Behavior generation verifies archive hashes against the active FARS manifest; do not substitute a newer release silently. The builder validates federal source identity, year coverage, row totals, factor denominators and artifact lineage. Serving validates strict finite JSON and model parameters and fails closed on an invalid release. `data/public/snapshot.json` contains aggregates and numeric coefficients; inference does not load pickle files.

The screening image also needs `data/safety/snapshot.json`, `advanced-benchmark.json`, and `behavior.json`. These are generated evidence artifacts from the existing engine pipeline. The advanced model comparisons are development evidence; their presence does not promote their candidates into the serving model.

## Deploy to the Google Cloud address

The public deployment script explicitly permits unauthenticated invocation, while the existing private service keeps its separate access policy. Use an authenticated Google Cloud CLI and billing-enabled project:

```bash
PYTHON_BIN=.venv/bin/python bash infra/public-cloud-run.sh geocrashai-safety-20260929 us-central1
```

`GCLOUD_BIN` can select an installed CLI path. The script validates artifacts, builds `Dockerfile.public` through `infra/cloudbuild-public.yaml`, and deploys service `geocrash`. Build inputs are controlled by `.gcloudignore-public`; the image bundles approved serving artifacts and public/static interfaces, not raw research data or account credentials.

The runtime uses a dedicated `geocrash-public` service account without newly granted project/storage roles, a non-root container user, one CPU, 1 GiB memory, zero minimum instances, a maximum of two instances, concurrency 20, and a 30-second request timeout. A `/ready` startup probe verifies artifact availability. These limits bound the initial service footprint; they are not an uptime SLA or a strict spending cap.

### Verify from an unauthenticated client

```bash
curl --fail --silent --show-error https://geocrash-666321636483.us-central1.run.app/ready
curl --fail --silent --show-error https://geocrash-666321636483.us-central1.run.app/api/public/meta
curl --fail --silent --show-error 'https://geocrash-666321636483.us-central1.run.app/api/public/summary?state=31&year=2024'
curl --fail --silent --show-error 'https://geocrash-666321636483.us-central1.run.app/api/public/forecast?state=31'
curl --fail --silent --show-error https://geocrash-666321636483.us-central1.run.app/api/safety/status
```

Run the automated unauthenticated check:

```bash
.venv/bin/python scripts/verify_public.py https://geocrash-666321636483.us-central1.run.app --output outputs/releases/public-3d-verification.json
```
 The verifier checks HTML/assets/OpenAPI, national totals, forecast-coefficient parity, road-inference parity, scenario guards, body limits and research isolation.

Also open the 3D homepage, `/explore/` and `/screening/` in a fresh browser without cloud credentials. Select a state and year, run a forecast, inspect a road and its runtime prediction, and check `/docs`. Verify unsupported states/years fail with 422 and unavailable artifacts with 503. Record `/ready`'s revision and artifact hash with release evidence. A successful process health response alone is insufficient.

## Model updates, request limits, and rollback

The service is read-only with respect to datasets and model parameters. POST endpoints calculate bounded forecasts and scenarios; they do not retrain or persist changes. Artifacts are bundled into an image, so updates require a reviewed rebuild and new deployment. Private scheduled jobs do not automatically update this public image. Preserve source hashes, evaluation results, model coefficients, image digest and revision for each release.

All request bodies are capped at **16 KiB**, including streamed POST/PUT/PATCH bodies. Public and screening API requests share a **per-process token bucket**, replenishing six requests per second with a burst of 180. It returns 429 with `Retry-After: 1`; the body limit returns 413. This is an aggregate application limit, not per-user quotas or a distributed abuse-protection guarantee. Reverse-proxy client-IP headers do not determine the bucket. Cloud instance and concurrency limits are separate controls.

The API rejects extra forecast fields and nonfinite values. Successful public GET API responses can be cached for five minutes and carry `X-Data-Release`; other responses use `no-store`. Security headers deny framing and browser camera/microphone/geolocation permissions. No browser map keys, external font downloads, or external map tile service are needed.

For application rollback, find a previously verified revision and send traffic to it:

```bash
gcloud run revisions list --project=geocrashai-safety-20260929 --region=us-central1 --service=geocrash
gcloud run services update-traffic geocrash --project=geocrashai-safety-20260929 --region=us-central1 --to-revisions=PREVIOUS_VERIFIED_REVISION=100
```

Replace the revision placeholder deliberately; repeat the unauthenticated smoke checks afterward. Because public data/model artifacts are image-bundled, the previous revision restores that revision's artifacts. This does not roll back the private safety service, its storage, or its scheduled jobs. For an emergency withdrawal, remove public invocation and verify that unauthenticated requests are denied; preserve the revision for investigation.

## Source rights and commercial boundary

[NHTSA FARS](https://www.nhtsa.gov/research-data/fatality-analysis-reporting-system-fars) supplies the federal historical crash records. [NDOT's publisher policy](https://dot.nebraska.gov/policies-and-disclaimers/) permits use of its web information at the user's risk and supports this informational presentation. It does not establish a blanket commercial redistribution grant, a warranty, agency endorsement, or fitness for operational decisions. Source-specific commercial rights remain an explicit delivery question; the safety API continues to reject `commercial=true` exports.

Public access and commercial clearance are separate. Buyers can inspect actual historical data, working model inference, methods and APIs now at the verified public address. A contract still needs approved data/software terms, agency acceptance criteria, support responsibilities and security requirements. Do not call the site a current incident feed, an all-crash injury model, an HSM-certified engine, or a trained foundation model.

## Verification record

The implementation passed **195 targeted safety tests with 91.01% safety-package coverage** at this release stage. A separate fresh public dependency audit records 50 pinned runtime distributions with zero known vulnerabilities (`outputs/releases/public-dependency-audit.json`); this is a package scan, not an operating-system audit or security certification. Browser checks at 1440px and 390px covered real totals, all 51 boundaries, Nebraska 2024 filtering, runtime count inference, factor categories, reset/error recovery and Alaska/Hawaii, with no viewport overflow or JavaScript errors. Independent `public_finish` review returned **SHIP** with no material fixes, including screening/inference/economics, all 11 links, 413/422 guards and research-route isolation. Unauthenticated cloud verification passed for website assets/docs, national totals, 11,048 roads, state/road inference parity, scenario calculations, input guards and research-route isolation. Cloud Playwright checks passed desktop 1440px and mobile 390px 3D map flows, filtering, tilt/reset, Alaska/Hawaii, error recovery and WebGL fallback, with evidence in `outputs/releases/public-3d-cloud-browser.json`. The `/explore/` workbench regression also passed; these checks do not establish agency validation or commercial rights.


### Earlier 3D homepage release identity

- Service: `geocrash`, project `geocrashai-safety-20260929`, region `us-central1`.
- Revision: `geocrash-00002-vkd`, verified at 100% traffic.
- Image tag: `20260930015440`.
- Image digest: `sha256:2177306944c582575b73a43c6777e4e0d8d4def750407fb5f2b7de0b38085215`.
- Successful Cloud Build: `cd00c192-04ef-4769-9729-14beebd7edaf`.
- Automated anonymous verification: `outputs/releases/public-3d-verification.json`.

Cloud service evidence in `outputs/releases/public-3d-cloud-service.json` confirms 100% traffic on this revision. Model parameters and data artifact hashes are unchanged from the preceding public release. The first post-rollout road-prediction request exceeded 30 seconds; a complete anonymous retry passed. Cold-start latency has not been validated against an SLA.

These identify the public 3D homepage release, not perpetual service health. Re-run verification after updates and before important demonstrations.

## Agency planning release — 2026-09-30

Public revision `geocrash-00003-kh4` was deployed at 100% traffic from build `954f909d-27de-4bba-ad7f-b253fb2186ce`. Image `public:agency-planning-20260930-final`, digest `sha256:31dd37b44df32e68be31f25abf3c7ba8af201b566da08c5380204d6be1b4a02b`. Rollback target: `geocrash-00002-vkd`. Public FARS and road-model snapshots are unchanged. The image additionally contains the source-bound compact NDOT road geometry.

See [Agency planning methods](AGENCY_PLANNING.md) for inputs, endpoints and limits. This release adds calculation-only POST endpoints; submitted agency observations and trips are not persisted by the application. Infrastructure request logs can retain route coordinates. The separate private OSRM service uses its own service account; only the public app service account receives service-level invocation. Configure both `SAFETY_ROUTING_OSRM_URL` and `SAFETY_ROUTING_AUTH_AUDIENCE` to the explicitly accepted routing-service URL. Reproduce the routing backend using `infra/routing/README.md`; no public-demo routing dependency is used in production.

The private routing revision is `geocrash-routing-00002-5fj`, image digest `sha256:f006cffa31c5d597558e327b30d2a4ee2842cd5157f90e126e5ab28ada379287`. See `infra/routing/deployment.json` for immutable source/image identifiers and IAM/startup evidence. Anonymous provider access returns403; the public application's identity can invoke it. Both routing environment variables use `https://geocrash-routing-666321636483.us-central1.run.app`, explicitly configured as an accepted audience. Public route generation and all planning workflows passed deployed verification, including browser report download. Baseline route alternatives are operational as an evaluation feature; live traffic rerouting and demonstrated agency benefits remain unvalidated.
