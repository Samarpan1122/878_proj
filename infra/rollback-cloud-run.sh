#!/usr/bin/env bash
# Restores code traffic only; mounted data and scheduled jobs are separate releases.
set -euo pipefail
PROJECT="${1:?Usage: bash infra/rollback-cloud-run.sh PROJECT_ID REVISION [REGION]}"
REVISION="${2:?Supply the exact previously verified revision}"
REGION="${3:-us-central1}"
GCLOUD_BIN="${GCLOUD_BIN:-gcloud}"
SERVICE="geocrash-safety"
[[ "$REVISION" == "$SERVICE-"* ]] || { echo 'Revision does not belong to geocrash-safety.' >&2; exit 1; }
# Validate existence before changing traffic. This command does not alter IAM.
"$GCLOUD_BIN" run revisions describe "$REVISION" --project="$PROJECT" --region="$REGION" --format='value(metadata.name)' >/dev/null
"$GCLOUD_BIN" run services update-traffic "$SERVICE" --project="$PROJECT" --region="$REGION" --to-revisions="$REVISION=100"
echo 'Code traffic restored. Verify mounted data provenance, job images and authenticated smoke checks separately.'
