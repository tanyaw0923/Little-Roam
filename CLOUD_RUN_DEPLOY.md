# Deploy Little Roam v0.1 to GCP Cloud Run

This deployment runs in **mock mode** without invoking Google Places or OpenAI APIs. It uses a **private** Cloud Run service, `min-instances=0`, and `max-instances=2` for a constrained initial test. It does not establish a spending cap: configure Google Cloud billing budgets and API quotas separately. Source builds, container storage, and network traffic may incur charges even if Cloud Run request usage is within its free tier.

## 1. Open Cloud Shell and upload the project

In Google Cloud Console, select your existing project and open **Cloud Shell**. Upload the ZIP, unzip it, and enter the folder. For a ZIP whose contents have a `little-roam-backend/` folder:

```bash
unzip little-roam-backend-gcp.zip
cd little-roam-backend
```

## 2. Deploy

Replace `YOUR_PROJECT_ID` with your actual **project ID**, not the project display name:

```bash
export PROJECT_ID="YOUR_PROJECT_ID"
bash deploy-cloud-run.sh
```

Default region is **Toronto (`northamerica-northeast2`)**. Set `REGION=northamerica-northeast1` for Montréal or another supported region as needed.

> If IAM permissions or billing prevent deployment, inspect the error before granting broader roles. Source deployments can require Cloud Run, Cloud Build, and Artifact Registry permissions; check the official Cloud Run source deployment documentation.

## 3. Test private service in Cloud Shell

```bash
export REGION="northamerica-northeast2"
export SERVICE="little-roam-api"
export URL="$(gcloud run services describe "$SERVICE" --region "$REGION" --format='value(status.url)')"
export TOKEN="$(gcloud auth print-identity-token)"

curl -sS -H "Authorization: Bearer $TOKEN" "$URL/health"

curl -sS -X POST "$URL/api/v1/recommendations" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"city":"Calgary","province":"AB","children_ages":[2,6],"interests":["nature","animals"],"activity_type":"any","budget":"any","radius_km":25,"max_results":10}'
```

Expect `/health` to return `{"status":"ok"}` and the recommendation endpoint to return `"mode":"mock"` with 10 fictional places. This **does not** mean the system is recommending verified attractions yet.

## 4. Turn on paid external APIs later (optional)

Only after reviewing the Google Places billing/field mask and establishing API quotas, enable Places API (New) and create a **server-restricted** API key for your backend. Use Google Cloud Secret Manager for both Google Maps and OpenAI keys, **not** `--set-env-vars` for sensitive values.

Example setup (run only when ready; these commands request secret contents interactively):

```bash
gcloud services enable secretmanager.googleapis.com places-backend.googleapis.com
printf 'Paste Google Maps API key: '; read -rs GOOGLE_MAPS_API_KEY; echo
printf '%s' "$GOOGLE_MAPS_API_KEY" | gcloud secrets create little-roam-google-maps-key --data-file=-
unset GOOGLE_MAPS_API_KEY

# Grant only the Cloud Run runtime service account access to the secret.
# First inspect the actual runtime service account:
gcloud run services describe "$SERVICE" --region "$REGION" --format='value(spec.template.spec.serviceAccountName)'
```

After identifying the runtime service account and granting it `roles/secretmanager.secretAccessor` **on that specific secret**, run:

```bash
gcloud run services update "$SERVICE" --region "$REGION" \
  --update-secrets GOOGLE_MAPS_API_KEY=little-roam-google-maps-key:1 \
  --update-env-vars PLACES_PROVIDER=google
```

`GOOGLE_MAPS_API_KEY` is not required in mock mode. If you also want model-written descriptions, create an `OPENAI_API_KEY` secret separately and grant the runtime account access; then attach with `--update-secrets OPENAI_API_KEY=SECRET_NAME:VERSION`.

**Important:** This v0.1 Google Places integration launches 8 Text Search queries per recommendation request. It does not enforce `radius_km`, validate city membership, validate age suitability, or independently verify prices/opening hours. Its results must not yet be presented as fully verified Canadian family recommendations. Before opening it publicly, implement authentication/rate limiting and cost protection.

## 5. View logs and avoid unwanted charges

```bash
gcloud run services logs read "$SERVICE" --region "$REGION" --limit 50
```

In Google Cloud Billing, create a small budget and alerts. **Budgets notify rather than automatically stopping billing**. Set API quotas and review cost reports. To remove the test service:

```bash
gcloud run services delete "$SERVICE" --region "$REGION"
```

Container images from source builds remain in Artifact Registry until deleted separately; inspect them if cleaning up.
