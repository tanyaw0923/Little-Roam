#!/usr/bin/env bash
set -euo pipefail

# Run from the project directory in Google Cloud Shell.
# Usage: PROJECT_ID=my-gcp-project bash deploy-cloud-run.sh
: "${PROJECT_ID:?Set PROJECT_ID to your Google Cloud project ID (not display name)}"
REGION="${REGION:-northamerica-northeast2}"
SERVICE="${SERVICE:-little-roam-api}"

printf 'Deploying %s to project %s in %s (private; mock mode)\n' "$SERVICE" "$PROJECT_ID" "$REGION"
gcloud config set project "$PROJECT_ID"
gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com

gcloud run deploy "$SERVICE" \
  --project "$PROJECT_ID" \
  --region "$REGION" \
  --source . \
  --no-allow-unauthenticated \
  --min-instances 0 \
  --max-instances 2 \
  --memory 512Mi \
  --cpu 1 \
  --concurrency 10 \
  --timeout 90 \
  --set-env-vars PLACES_PROVIDER=mock \
  --quiet

URL="$(gcloud run services describe "$SERVICE" --project "$PROJECT_ID" --region "$REGION" --format='value(status.url)')"
printf '\nPrivate API: %s\n' "$URL"
printf 'Health check from authenticated Cloud Shell:\n'
printf 'curl -H "Authorization: Bearer $(gcloud auth print-identity-token)" "%s/health"\n' "$URL"
printf '\nTo try POST recommendations, see CLOUD_RUN_DEPLOY.md\n'
