#!/usr/bin/env bash
# Explicitly publishes the real-data informational portal. The private service is unchanged.
set -euo pipefail
PROJECT="${1:?Usage: bash infra/public-cloud-run.sh PROJECT_ID [REGION]}"
REGION="${2:-us-central1}"
GCLOUD_BIN="${GCLOUD_BIN:-gcloud}"
PYTHON_BIN="${PYTHON_BIN:-python}"
SERVICE=geocrash
RUNTIME_SA="geocrash-public@${PROJECT}.iam.gserviceaccount.com"
IMAGE="${IMAGE:-${REGION}-docker.pkg.dev/${PROJECT}/geocrash/public:$(date -u +%Y%m%d%H%M%S)}"
"$PYTHON_BIN" -c 'from pathlib import Path; from safety.api import strict_json; from safety.public_data import validate_snapshot; validate_snapshot(strict_json(Path("data/public/snapshot.json").read_text()))'
"$PYTHON_BIN" -m safety.release audit --root data/safety --output outputs/releases/public-screening-audit.json --require-technical
"$GCLOUD_BIN" services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com iam.googleapis.com --project="$PROJECT"
if ! "$GCLOUD_BIN" artifacts repositories describe geocrash --project="$PROJECT" --location="$REGION" >/dev/null 2>&1; then
  "$GCLOUD_BIN" artifacts repositories create geocrash --repository-format=docker --project="$PROJECT" --location="$REGION"
fi
if ! "$GCLOUD_BIN" iam service-accounts describe "$RUNTIME_SA" --project="$PROJECT" >/dev/null 2>&1; then
  "$GCLOUD_BIN" iam service-accounts create geocrash-public --project="$PROJECT" --display-name='GeoCrash public read-only portal'
fi
# No runtime project/storage role is granted: the served artifacts are bundled.
if [[ "${SKIP_BUILD:-false}" != true ]]; then
  "$GCLOUD_BIN" builds submit . --project="$PROJECT" --config=infra/cloudbuild-public.yaml \
    --substitutions="_IMAGE=$IMAGE" --ignore-file=.gcloudignore-public
fi
"$GCLOUD_BIN" run deploy "$SERVICE" --project="$PROJECT" --region="$REGION" --image="$IMAGE" \
  --service-account="$RUNTIME_SA" --allow-unauthenticated --ingress=all \
  --cpu=1 --memory=1Gi --min-instances=0 --max-instances=2 --concurrency=20 --timeout=30 --port=8080 \
  --startup-probe=httpGet.path=/ready,httpGet.port=8080,periodSeconds=10,timeoutSeconds=5,failureThreshold=12 \
  --set-env-vars="GEOCRASH_PUBLIC_DATA=/app/data/public,GEOCRASH_SCREENING_DATA=/app/data/safety,PUBLIC_PORTAL_URL=/,SAFETY_ROUTING_OSRM_URL=${SAFETY_ROUTING_OSRM_URL:-},SAFETY_ROUTING_AUTH_AUDIENCE=${SAFETY_ROUTING_AUTH_AUDIENCE:-}"
"$GCLOUD_BIN" run services describe "$SERVICE" --project="$PROJECT" --region="$REGION" --format='value(status.url)'
