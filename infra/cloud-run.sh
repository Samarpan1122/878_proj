#!/usr/bin/env bash
# Execute only after selecting the explicit project and its billing account.
set -euo pipefail
PROJECT="${1:?Usage: bash infra/cloud-run.sh PROJECT_ID [REGION]}"
REGION="${2:-us-central1}"
GCLOUD_BIN="${GCLOUD_BIN:-gcloud}"
PYTHON_BIN="${PYTHON_BIN:-python}"
SERVICE="geocrash-safety"
IMAGE="${IMAGE:-${REGION}-docker.pkg.dev/${PROJECT}/geocrash/safety:$(date -u +%Y%m%d%H%M%S)}"
RUNTIME_SA="geocrash-runtime@${PROJECT}.iam.gserviceaccount.com"
JOB_SA="geocrash-jobs@${PROJECT}.iam.gserviceaccount.com"
SCHEDULER_SA="geocrash-scheduler@${PROJECT}.iam.gserviceaccount.com"
[[ -f data/safety/snapshot.json ]] || { echo 'Build data/safety/snapshot.json before deployment.' >&2; exit 1; }
"$PYTHON_BIN" -m safety.release audit --root data/safety \
  --output outputs/releases/readiness.json --require-technical

"$GCLOUD_BIN" services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com iam.googleapis.com --project="$PROJECT"
if ! "$GCLOUD_BIN" artifacts repositories describe geocrash --project="$PROJECT" --location="$REGION" >/dev/null 2>&1; then
  "$GCLOUD_BIN" artifacts repositories create geocrash --repository-format=docker --project="$PROJECT" --location="$REGION"
fi
if ! "$GCLOUD_BIN" iam service-accounts describe "$RUNTIME_SA" --project="$PROJECT" >/dev/null 2>&1; then
  "$GCLOUD_BIN" iam service-accounts create geocrash-runtime --project="$PROJECT" --display-name='GeoCrashAI read-only API'
fi
# .gcloudignore is an allowlist, protecting the upload as well as the final image.
if [[ "${SKIP_BUILD:-false}" != true ]]; then
  "$GCLOUD_BIN" builds submit . --project="$PROJECT" --tag="$IMAGE" --ignore-file=.gcloudignore
fi
deploy=(run deploy "$SERVICE" --project="$PROJECT" --region="$REGION" --image="$IMAGE"
  --service-account="$RUNTIME_SA" --cpu=1 --memory=1Gi --min-instances=0 --max-instances=2
  --concurrency=40 --timeout=60 --port=8080
  --startup-probe=httpGet.path=/ready,httpGet.port=8080,periodSeconds=10,timeoutSeconds=5,failureThreshold=12)
if [[ "${PUBLIC_DEMO:-false}" == true ]]; then
  deploy+=(--allow-unauthenticated)
else
  deploy+=(--no-allow-unauthenticated)
fi
if [[ -n "${DATA_BUCKET:-}" ]]; then
  "$GCLOUD_BIN" storage buckets describe "gs://$DATA_BUCKET" --project="$PROJECT" >/dev/null
  # Publish the self-contained serving snapshot last. Candidate jobs verify its
  # source hashes/manifests and fail closed during a partially uploaded release.
  if [[ "${SKIP_DATA_UPLOAD:-false}" != true ]]; then
  for artifact in screening.parquet panel.parquet model.json segments.parquet crashes.parquet fars-manifest.json aadt-manifest.json feeds.json monitoring.json advanced-benchmark.json behavior.json snapshot.json; do
    # Scheduled refresh owns an existing live feed snapshot. A source deployment
    # must not replace it with an older laptop copy.
    if [[ "$artifact" == feeds.json ]] && "$GCLOUD_BIN" storage objects describe "gs://$DATA_BUCKET/safety/feeds.json" --project="$PROJECT" >/dev/null 2>&1; then
      continue
    fi
    if [[ -f "data/safety/$artifact" ]]; then
      "$GCLOUD_BIN" storage cp "data/safety/$artifact" "gs://$DATA_BUCKET/safety/$artifact" --project="$PROJECT"
    fi
  done
  fi
  "$GCLOUD_BIN" storage buckets add-iam-policy-binding "gs://$DATA_BUCKET" --member="serviceAccount:$RUNTIME_SA" --role=roles/storage.objectViewer --project="$PROJECT" >/dev/null
  deploy+=(--execution-environment=gen2 --add-volume="name=data,type=cloud-storage,bucket=$DATA_BUCKET,readonly=true"
    --add-volume-mount=volume=data,mount-path=/mnt/data --update-env-vars=SAFETY_DATA_DIR=/mnt/data/safety,GEOCRASH_SAFETY_DATA=/mnt/data/safety)
fi
if [[ -n "${CLOUD_SQL_CONNECTION:-}" ]]; then
  : "${DATABASE_SECRET:?Set DATABASE_SECRET to the existing Secret Manager secret containing DATABASE_URL}"
  "$GCLOUD_BIN" services enable sqladmin.googleapis.com secretmanager.googleapis.com --project="$PROJECT"
  "$GCLOUD_BIN" projects add-iam-policy-binding "$PROJECT" --member="serviceAccount:$RUNTIME_SA" --role=roles/cloudsql.client >/dev/null
  "$GCLOUD_BIN" secrets add-iam-policy-binding "$DATABASE_SECRET" --project="$PROJECT" --member="serviceAccount:$RUNTIME_SA" --role=roles/secretmanager.secretAccessor >/dev/null
  deploy+=(--add-cloudsql-instances="$CLOUD_SQL_CONNECTION" --set-secrets="DATABASE_URL=$DATABASE_SECRET:latest")
fi
"$GCLOUD_BIN" "${deploy[@]}"

if [[ "${ENABLE_SCHEDULES:-false}" == true ]]; then
  : "${DATA_BUCKET:?Scheduled jobs require DATA_BUCKET for persistent artifacts}"
  "$GCLOUD_BIN" services enable cloudscheduler.googleapis.com --project="$PROJECT"
  for name in geocrash-jobs geocrash-scheduler; do
    if ! "$GCLOUD_BIN" iam service-accounts describe "$name@$PROJECT.iam.gserviceaccount.com" --project="$PROJECT" >/dev/null 2>&1; then
      "$GCLOUD_BIN" iam service-accounts create "$name" --project="$PROJECT"
    fi
  done
  "$GCLOUD_BIN" storage buckets add-iam-policy-binding "gs://$DATA_BUCKET" --project="$PROJECT" --member="serviceAccount:$JOB_SA" --role=roles/storage.objectAdmin >/dev/null
  for task in feeds candidate; do
    if [[ "$task" == feeds ]]; then
      cli_args="-m,safety.cloud_job,--bucket,$DATA_BUCKET,--task,feeds"
      schedule='*/15 * * * *'
    else
      cli_args="-m,safety.cloud_job,--bucket,$DATA_BUCKET,--task,candidate"
      schedule='0 3 * * 0'
    fi
    job="geocrash-$task"
    "$GCLOUD_BIN" run jobs deploy "$job" --project="$PROJECT" --region="$REGION" --image="$IMAGE" \
      --service-account="$JOB_SA" --tasks=1 --max-retries=0 --task-timeout=3600 --cpu=1 --memory=2Gi \
      --command=python --args="$cli_args" --set-env-vars=PYTHONUNBUFFERED=1
    "$GCLOUD_BIN" run jobs add-iam-policy-binding "$job" --project="$PROJECT" --region="$REGION" \
      --member="serviceAccount:$SCHEDULER_SA" --role=roles/run.invoker >/dev/null
    verb=create
    if "$GCLOUD_BIN" scheduler jobs describe "$job" --project="$PROJECT" --location="$REGION" >/dev/null 2>&1; then verb=update; fi
    "$GCLOUD_BIN" scheduler jobs "$verb" http "$job" --project="$PROJECT" --location="$REGION" \
      --schedule="$schedule" --time-zone=America/Chicago --http-method=POST \
      --uri="https://run.googleapis.com/v2/projects/$PROJECT/locations/$REGION/jobs/$job:run" \
      --oauth-service-account-email="$SCHEDULER_SA" --message-body='{}'
  done
fi
"$GCLOUD_BIN" run services describe "$SERVICE" --project="$PROJECT" --region="$REGION" --format='value(status.url)'
