# Deploy Little Roam FastAPI recommendations (PostgreSQL + Routes) to Cloud Run

This guide deploys the **API service**, not the existing scheduled Calgary importer job. The importer and its Cloud Scheduler trigger are unaffected.

The service is **private** and runs in `us-central1` using a dedicated runtime service account. It starts with `min-instances=0`, `max-instances=2`, and `PLACES_PROVIDER=postgres`. Secrets are injected by Google Secret Manager; the Google Routes API key is **not** baked into the image.

## Prerequisites

- Little Roam GCP project selected and billing enabled.
- Supabase PostgreSQL connection URL stored as Secret Manager secret `little-roam-database-url`, with an ENABLED version.
- Google Routes API (`routes.googleapis.com`) enabled and a Routes-only API key stored as `little-roam-routes-api-key`, with an ENABLED version.
- You have applied the [Bow Valley seed](sql/seed_bow_valley.sql) and [coordinate backfill](sql/backfill_bow_valley_coordinates.sql) to Supabase if you want Banff/Canmore results.
- API keys are never entered on a command line as literal arguments and never committed.
- Cloud Shell identity has deployment, service account use and IAM binding rights.

## 1. Verify repository and project

```bash
cd ~/Little-Roam/Little-Roam
git pull --ff-only origin main
python -m pytest -q

export PROJECT_ID="$(gcloud config get-value project)"
export REGION="us-central1"
export SERVICE="little-roam-api"
export API_SA="little-roam-api@${PROJECT_ID}.iam.gserviceaccount.com"
echo "Project: $PROJECT_ID | Region: $REGION"
```

Confirm the printed project is the intended billing project.

## 2. Enable GCP services

```bash
gcloud services enable \
  run.googleapis.com cloudbuild.googleapis.com \
  artifactregistry.googleapis.com secretmanager.googleapis.com \
  routes.googleapis.com \
  --project="$PROJECT_ID"
```

Confirm both secret versions exist and are enabled (do **not** print their values):

```bash
gcloud secrets versions list little-roam-database-url --project="$PROJECT_ID"
gcloud secrets versions list little-roam-routes-api-key --project="$PROJECT_ID"
```

## 3. Runtime identity and secret-level access

Create a dedicated identity once (skip creation if it already exists):

```bash
gcloud iam service-accounts describe "$API_SA" --project="$PROJECT_ID" >/dev/null 2>&1 || \
gcloud iam service-accounts create little-roam-api \
  --display-name="Little Roam FastAPI runtime" \
  --project="$PROJECT_ID"
```

Grant read access to **only** the two required secrets:

```bash
for SECRET in little-roam-database-url little-roam-routes-api-key; do
  gcloud secrets add-iam-policy-binding "$SECRET" \
    --project="$PROJECT_ID" \
    --member="serviceAccount:$API_SA" \
    --role="roles/secretmanager.secretAccessor"
done
```

If the source build fails with an IAM error, check the build service account and the documented `roles/run.builder` access. Avoid broad Owner or Editor grants.

## 4. Deploy a private API service

```bash
gcloud run deploy "$SERVICE" \
  --project="$PROJECT_ID" \
  --region="$REGION" \
  --source . \
  --service-account="$API_SA" \
  --no-allow-unauthenticated \
  --min-instances=0 \
  --max-instances=2 \
  --memory=512Mi \
  --cpu=1 \
  --concurrency=10 \
  --timeout=90 \
  --set-env-vars="PLACES_PROVIDER=postgres" \
  --set-secrets="DATABASE_URL=little-roam-database-url:latest,GOOGLE_ROUTES_API_KEY=little-roam-routes-api-key:latest"
```

If the service already exists, deployment creates a new revision. Check its existing configuration before applying changes. The above command intentionally sets a private, source-based API; it does **not** execute the daily Calgary importer job.

## 5. Smoke tests (authenticated)

```bash
export URL="$(gcloud run services describe "$SERVICE" \
  --project="$PROJECT_ID" --region="$REGION" \
  --format='value(status.url)')"
export TOKEN="$(gcloud auth print-identity-token)"

curl --fail-with-body -sS -H "Authorization: Bearer $TOKEN" "$URL/health"

curl --fail-with-body -sS -X POST "$URL/api/v1/recommendations" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"city":"Calgary","children_ages":[2,6],"interests":["nature"],"activity_type":"any","budget":"any","max_results":10}'
```

Then run **one** paid Routes test:

```bash
curl --fail-with-body -sS -X POST "$URL/api/v1/recommendations" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"city":"Calgary","search_scope":"regional","max_drive_minutes":120,"children_ages":[2,6],"interests":["nature","recreation"],"activity_type":"any","budget":"any","max_results":10}'
```

For regional results expect `drive_minutes` and road `distance_km`; a maximum of **10 candidate destinations** is sent to Routes API in each request. The actual result count may be smaller due to missing routes, price/age constraints, or the driving-time threshold.

## 6. Inspect failures and costs

```bash
gcloud run services logs read "$SERVICE" --project="$PROJECT_ID" --region="$REGION" --limit=80
```

API return code 503 may mean missing runtime credentials, database connection trouble, or a missing Routes key. A 502 indicates upstream Routes failure. Avoid writing raw keys or connection strings into logs.

Enable budget alerts, restrict your API key to Routes API, enforce quotas, and keep the service private until you have authentication, user-level rate limiting and abuse protection. A **10-destination per-request** limit does not prevent high costs if the endpoint is called repeatedly.

For local Cloud Shell restart instructions see [README](README.md). For pricing, routing assumptions, and limitations see [DRIVING_TIME_SEARCH.md](DRIVING_TIME_SEARCH.md).
