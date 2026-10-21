# Safety engine operations

For the public real-data website, anonymous API access, image-bundled model updates and public revision rollback, use the [public deployment guide](PUBLIC_DEPLOYMENT.md). This document primarily covers the separate private safety service and evaluation package.

## Evaluation release tooling

`python -m safety.release audit --root data/safety --require-technical` validates the serving snapshot, local input SHA-256 values, exact source-manifest agreement and presence of temporal/geographic evaluation records. The report is `outputs/releases/readiness.json`. `/api/safety/readiness` deliberately performs only the lighter serving-metadata assessment and labels file verification unverified; it is not a replacement for the offline audit. Commercial readiness stays false until external rights, engineering and contractual review are resolved.

`python -m safety.demo --root data/synthetic-demo` creates 24 deterministic fictional corridors in a new/empty directory. Serve with `GEOCRASH_SAFETY_DATA=data/synthetic-demo uvicorn safety.api:app --host 127.0.0.1 --port 8893`. The UI, scenario JSON and CSV/JSON exports retain synthetic labels. The model/behavior sections are hidden because no measured model or behavioral results exist in this fixture.

`python -m safety.release bundle` builds `outputs/releases/geocrash-evaluation.zip`, with code, docs and a synthetic generator but no real datasets, account files or research weights. The manifest records each packaged file's bytes and SHA-256. This is an engineering evaluation package, not a software-license grant. The buyer workflow is in [docs/commercial](commercial/README.md).

The private release originally pinned 49 resolved runtime distributions. Its Python 3.12 resolution audit on 2026-09-30 UTC found no known vulnerabilities in those versions (`outputs/releases/dependency-audit.json`). The public build adds `packaging==26.3`, making 50 pinned distributions; its separate fresh audit reports 50 dependencies and zero known vulnerabilities in `outputs/releases/public-dependency-audit.json`. Do not present the earlier 49-distribution audit as verification of the expanded public lock. This scan does not inspect the container OS, prove absence of vulnerabilities, or certify the application. The constraints file is version-pinned, not a cryptographic package-hash lock; the container base tag also remains mutable. Repeat resolution/audit deliberately before updating the pins.

The independent `safety` package uses FARS fatal crashes and an NDOT exposure network. It does not load the legacy research engine, Kaggle tables, or their weights. NDOT's commercial reuse terms remain unconfirmed; isolation from Kaggle does not by itself authorize commercial deployment.

## Local service

```bash
python -m pip install -r requirements-test.txt
python -m safety.cli --root data/safety ingest --years 2021 2022 2023
python -m safety.cli --root data/safety build
python -m safety.cli --root data/safety refresh-feeds
GEOCRASH_SAFETY_DATA=data/safety uvicorn safety.api:app --host 127.0.0.1 --port 8080
pytest tests/test_safety*.py --cov=safety --cov-report=term-missing --cov-fail-under=80
```

`/health` checks the process; `/api/safety/status` includes snapshot readiness. Local compatibility aliases `/healthz` and `/readyz` exist, but avoid them through Cloud Run: [Google reserves some paths ending in z](https://docs.cloud.google.com/run/docs/known-issues#reserved-url-paths). `/docs` documents the API. The service serves the safety workspace, with the research dashboard remaining separately accessible through its original server.

Ingest and model fitting should run sequentially on this laptop because the handoff records memory pressure and disk exhaustion during parallel training. Lightweight tests and web work can run concurrently. Retain at least one previous approved artifact set outside the active data directory for rollback.

```bash
docker compose up --build api
POSTGRES_PASSWORD='choose-a-local-password' docker compose --profile database up -d db
```

The optional local PostGIS container binds only to loopback. Its fallback password is explicitly for development. Set your own password before using the database. The production Dockerfile copies only approved safety files and assets; `.dockerignore` and `.gcloudignore` separately limit image contents and cloud-upload contents.

## Feed provenance and failure handling

The default feed calls NOAA's active Nebraska weather alerts endpoint. These are weather warnings, not crash detections. A successful zero-alert response is valid. Set `NWS_USER_AGENT` to an application identifier and operational contact as requested by the [NWS API documentation](https://www.weather.gov/documentation/services-web-api).

An agency 511 adapter can consume an explicitly authorized HTTPS GeoJSON FeatureCollection. Each feature needs a stable `id` (feature or properties), Point geometry `[longitude, latitude]`, and optional `description` and `updated_at` properties. IDs deduplicate within one refresh. Invalid identifiers or coordinates reject that entire refresh rather than silently hiding source defects.

```python
from safety.feeds import refresh_feeds

refresh_feeds("data/safety", incident_config={
    "url": "https://YOUR_AUTHORIZED_PROVIDER/geojson",
    "provider": "Agency name",
    "terms_url": "https://YOUR_AUTHORIZED_PROVIDER/terms",
    "permitted_use": "Describe the actual authorized use",
    "approved_by": "Agency agreement owner"
})
```

No Nebraska 511 or Waze account is assumed or scraped. The operator must supply the real agreement. Keep configuration and credentials outside the served artifacts; do not put tokens in terms URLs. Feed URLs and raw exception messages are omitted from public snapshots. Refresh failures retain the previous successful records and timestamp, set `status=error`, and report staleness. Sources with no agreement report `not_configured`. `feed_status` considers snapshots older than 30 minutes stale by default. API instances do not refresh feeds on request.

## Monitoring and model review

The safety workspace exposes `/api/safety/model-evidence` and `/api/safety/behavior` for the advanced development comparison and aggregate recorded factors. Missing artifacts return 503; source fingerprints differing from the active snapshot return 409. Build them with `safety.cli benchmark` and `safety.cli behavior` as documented in `docs/ADVANCED_MODELS.md`. Benchmarking reconstructs the road-year panel from verified sources, so an old cached panel cannot acquire new source hashes. These reports do not change the active NB/EB model.

The integrated local research app additionally exposes `/api/research/advanced` and `POST /api/research/predict`. These are absent from the production safety-only app. Their neural weights and noncommercial data stay under `outputs/research/`; deployment upload allowlists exclude them. Saved-model replay evidence lives in `outputs/research/inference_verification.json`.

`safety.monitoring.drift_report(reference, current)` reports PSI, row-count coverage, and missingness changes. PSI ≥0.2, coverage movement exceeding 20%, or missingness growth exceeding five percentage points prompts review. These are operational heuristics, not p-values. Investigate incomplete source delivery, changed segmentation, traffic-count vintage, and linkage yield before treating a warning as model drift.

```bash
python -m safety.cli --root data/safety build --candidate
```

Candidate builds write to a timestamped directory and require manual review before promotion. Weekly refitting does not create newer annual FARS or AADT releases. Refresh those annual sources explicitly when published, then compare matching coverage and temporal/spatial validation against the active model. Promote only after a named reviewer accepts validation, coverage, licensing, and calibration. Roll back by restoring the complete previously approved artifact set, with `snapshot.json` replaced last.

## Optional PostGIS and BigQuery

`infra/postgis.sql` provides constrained spatial tables and geography indexes. `safety.database.import_snapshot` imports one artifact set transactionally, merging screening statistics into segment properties when available. The nearby-road query uses metre distances, bound parameters, and coordinate/radius limits. It is optional: the API remains usable with filesystem artifacts alone.

```python
from safety.database import import_snapshot, nearby_segments
import_snapshot("data/safety")  # DATABASE_URL in the environment
roads = nearby_segments(41.2565, -95.9345, radius_miles=5)
```

Use Secret Manager for a deployed database URL. The Cloud SQL connection must already exist and have PostGIS enabled or permit schema initialization. The import account needs write/schema privileges; use a separate read-only account for serving queries. `infra/bigquery.sql` is a parameterized warehouse schema template, not a claim that a warehouse has been provisioned. Replace `YOUR_PROJECT`, load approved exports, and use the included geographic query pattern.

## Google Cloud deployment

The deployment script requires an explicit existing project ID and an already linked billing account. It enables APIs, creates an Artifact Registry repository and restricted service accounts, builds the image, and deploys an authenticated Cloud Run service. Resource creation incurs normal provider charges. Inspect the explicit project in every command. The user requested a new project through the CLI; its actual creation/deployment status belongs in the session handoff, not this reusable guide.

```bash
bash infra/cloud-run.sh YOUR_PROJECT us-central1
# Optional public demo; authorize public access before using this switch:
PUBLIC_DEMO=true bash infra/cloud-run.sh YOUR_PROJECT us-central1
```

For persistent live feeds and scheduled candidate builds, create a dedicated regional bucket, then:

```bash
DATA_BUCKET=YOUR_EXISTING_BUCKET ENABLE_SCHEDULES=true \
  bash infra/cloud-run.sh YOUR_PROJECT us-central1
```

Only named safety artifacts upload to `gs://BUCKET/safety/`. The API receives read-only bucket access; jobs receive object access to that dedicated bucket. Weather refresh runs every 15 minutes; candidate fitting runs Sundays at 03:00 America/Chicago. Cloud Scheduler invokes Cloud Run Jobs with OAuth and a dedicated invoker service account, following [Google's job scheduling guide](https://cloud.google.com/run/docs/execute/jobs-on-schedule). The API uses a read-only [Cloud Storage volume mount](https://cloud.google.com/run/docs/configuring/services/cloud-storage-volume-mounts). Jobs use `safety.cloud_job` to download inputs to local temporary disk and publish outputs through the Storage SDK with generation preconditions. Do not use a bucket containing unrelated sensitive data for this service account.

The job wrapper creates one conditional lease object before doing work. A concurrent job fails closed rather than clobbering a snapshot. A killed job may leave `safety/.job-lease.json`; confirm the corresponding execution has stopped, inspect its run ID/generation, and remove that exact generation to recover. Never remove a live worker's lease. Candidate output folders require `complete.json` to be considered complete, and still need manual approval. Failed partial uploads never replace the active model. The wrapper avoids assuming POSIX locking or atomic file rename behavior on a writable object-storage mount.

Deployment uploads the self-contained serving snapshot last. Before candidate fitting, the job verifies local crash/road file hashes and both source manifests against that snapshot's provenance. A job racing a deployment fails closed on any mismatch; retry after deployment completes. This detects mixed source releases instead of fitting and reporting results from inconsistent inputs.

Without `DATA_BUCKET`, the service uses its bundled immutable snapshot and there are no scheduled jobs. Container-local writes are ephemeral. The deployment script does not create a Cloud SQL instance or attach a billing account automatically. To attach an existing instance, set `CLOUD_SQL_CONNECTION=project:region:instance` and `DATABASE_SECRET=existing-secret-name`; this configures connectivity but does not change the API's default filesystem read path.

`infra/vertex-job.json` is a REST CustomJob request template. Replace its project, bucket, image tag, and service account, enable Vertex AI, and submit through the CustomJobs API or translate `jobSpec` into the CLI configuration format. The template uses the same Storage SDK wrapper to run `build --candidate`; it does not register or promote a model. Verify permissions and regional machine availability before submission. See [Google's custom training documentation](https://cloud.google.com/vertex-ai/docs/training/create-custom-job).

Cloud deployment should be verified by authenticated `/health`, readiness in `/api/safety/status`, a representative screening request, feed freshness after a scheduled execution, and a candidate artifact produced by a test job. Check job failures, API 5xx responses, cloud budget alerts, and bucket growth during operation. CI verifies application code offline; it does not demonstrate that cloud credentials, billing, or agency access are configured.

The current private pilot is in project `geocrashai-safety-20260929`. To open it through your authenticated CLI:

```bash
CLOUDSDK_CONFIG="$PWD/.cloud-config" .tools/google-cloud-sdk/bin/gcloud run services proxy \
  geocrash-safety --project=geocrashai-safety-20260929 --region=us-central1 --port=8892
```

Then visit http://localhost:8892. The directly deployed URL requires an identity token; simply opening it in an ordinary browser tab does not attach one. The fully local integrated workspace remains http://localhost:8878/safety.html.

## Release preflight, smoke checks and rollback

Every `infra/cloud-run.sh` deployment now runs the offline release audit before calling cloud services. Set `PYTHON_BIN=.venv/bin/python` when using the local virtual environment. The audit writes `outputs/releases/readiness.json`; a technical failure stops deployment. Passing it does not clear data rights or establish commercial acceptance. `/api/safety/readiness` serves a lighter assessment without hashing every source file per request.

Cloud Run startup probes call `/ready`, which returns 503 for a missing, invalid or empty screening snapshot. `/health` remains process liveness. Invalid optional feed files report an explicit stale error without disabling the historical screening API. Numeric overflow in snapshot metadata and evidence is rejected before serialization.

For a code-only update to the existing mounted pilot, set `SKIP_DATA_UPLOAD=true` along with `DATA_BUCKET`; this preserves every active object. The preflight still checks the local build inputs. Verify the deployed snapshot timestamp and provenance afterward because the mounted cloud dataset is independently managed. The deployment now preserves unrelated environment variables while updating the data paths.

The following checks are read-only and do not execute jobs or change IAM:

```bash
# Standalone safety API on loopback (not the integrated research server):
.venv/bin/python scripts/smoke_safety.py http://127.0.0.1:8080

# Private Cloud Run; uses the operator's configured gcloud login:
CLOUDSDK_CONFIG="$PWD/.cloud-config" .venv/bin/python scripts/smoke_safety.py \
  https://geocrash-safety-666321636483.us-central1.run.app \
  --identity-token --gcloud .tools/google-cloud-sdk/bin/gcloud --require-private \
  --output outputs/releases/cloud-smoke.json
```

Smoke checks cover authenticated health, populated readiness, screening, workspace assets, research-route isolation and the commercial-export guard. Identity tokens are kept out of output and redirects are rejected. The existing `scripts/verify_cloud.py` additionally checks IAM policy, BigQuery and optional scheduled-job executions. Neither tool proves agency acceptance or effectiveness of interventions.

Before a release, retain its exact revision, immutable image digest, source manifests and complete approved data artifacts. To restore a previously verified code revision:

```bash
GCLOUD_BIN=.tools/google-cloud-sdk/bin/gcloud CLOUDSDK_CONFIG="$PWD/.cloud-config" \
  bash infra/rollback-cloud-run.sh YOUR_PROJECT geocrash-safety-PREVIOUS_REVISION us-central1
```

This changes service traffic only and leaves IAM intact. A previous code revision still sees the current shared bucket: rolling back code does **not** roll back mounted data, feed objects or scheduled-job images. Restore those separately only from the recorded approved release, verify source hashes, and replace `snapshot.json` last. Rerun smoke checks and the fuller cloud verification after recovery. The rollback helper has been checked locally; no cloud rollback drill or recovery-time guarantee is claimed.
