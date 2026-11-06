# Little Roam 🧭

**AI-powered family activity discovery for Canadian families.**

Little Roam is an early-stage Python/FastAPI backend that recommends family outings by location, children's ages, interests, indoor/outdoor preference, and price category. It starts in Calgary, Alberta, and is designed to expand across Canada. Regional searches can use an Alberta postal-code area as the driving origin.

## Project status

- ✅ FastAPI and interactive Swagger API tested in Google Cloud Shell
- ✅ Supabase PostgreSQL connected and real Calgary attraction records tested during development
- ✅ Calgary recreation-facilities importer run successfully in the development environment
- ✅ Generic PostgreSQL JSON-feed refresh and unit tests in repository
- ✅ Calgary-specific importer is committed in `app/calgary_import.py`
- ✅ Calgary Cloud Run daily importer deployed and Scheduler trigger configured (as reported in deployment setup)
- ✅ Optional weather-aware ranking implemented in GitHub (not yet live-tested or deployed)
- ✅ Alberta postal-code origin, additional Bow Valley venue seed, and optional hours verification implemented in code (live integration not yet validated)
- ⏳ Public website not yet deployed

> The API is a working MVP, not a fully verified production activity recommender. Opening hours, prices and age suitability are not yet comprehensively verified. Regional routing is optional and only supports Calgary, Canmore and Banff origins.

## Architecture

```text
Future Next.js website
       |
       v
FastAPI /api/v1/recommendations
       |
       +-- PostgreSQL (Supabase): curated/licensed Canadian activities
       +-- Python ranking and optional OpenAI-generated explanations
       +-- Optional Google Places API (live discovery; not cached permanently)
       +-- Optional Open-Meteo same-day forecasts (evaluation/non-commercial use)
       +-- Optional Geocoding API (Alberta postal-code origin)
       +-- Optional Places Details (reported venue hours)
       
Approved activity data -> validation/upsert -> PostgreSQL
                          ^
                   Cloud Run Job + Scheduler (Calgary configured)
```

| Component | Technology |
|---|---|
| Backend | FastAPI, Python, Pydantic |
| Database | Supabase PostgreSQL + psycopg |
| Recommendations | Python matching/ranking, optional OpenAI and weather adjustment |
| Place discovery | Google Places API (New), optional |
| Postal-code origin | Google Geocoding API (optional, paid) |
| Operating hours | Google Places Details (optional, paid) |
| Hosting | GCP Cloud Run |
| Scheduled updates | Cloud Run Jobs + Cloud Scheduler (Calgary configured) |
| Testing | pytest |

## Quick start

Python 3.11+ required.

```bash
git clone https://github.com/tanyaw0923/Little-Roam.git
cd Little-Roam
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

For Windows PowerShell, activate with `.venv\Scripts\Activate.ps1` and copy the environment template with `Copy-Item .env.example .env`.

Open `/docs` for interactive Swagger documentation. In Cloud Shell, use Web Preview on port 8000 and append `/docs` before the `?authuser=...` query string.

Health check: `GET /health`, expected `{"status":"ok"}`.

### Restart FastAPI in Google Cloud Shell (Supabase + Routes API)

Use this workflow when you reopen Cloud Shell or restart the Little Roam recommendation API. The Cloud Run **daily Calgary importer** runs separately; restarting FastAPI here does not affect its Scheduler trigger.

```bash
cd ~/Little-Roam/Little-Roam
git pull --ff-only origin main

# Run tests before starting the local API.
python -m pytest -q

# Use the real Supabase activity records, rather than fictional mock venues.
export PLACES_PROVIDER=postgres

# Read secrets into environment variables without printing their values.
# Requires Secret Manager access for your signed-in Cloud Shell identity.
export DATABASE_URL="$(gcloud secrets versions access latest --secret=little-roam-database-url)"
export GOOGLE_ROUTES_API_KEY="$(gcloud secrets versions access latest --secret=little-roam-routes-api-key)"

# Fail early rather than launching with empty credentials.
test -n "$DATABASE_URL" && test -n "$GOOGLE_ROUTES_API_KEY" || {
  echo "Missing required secret; check project, permissions and enabled secret versions" >&2
  exit 1
}

python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

If dependencies are missing, install them first using `python -m pip install -r requirements.txt`. If the startup command reports that port 8000 is already in use, stop the existing Uvicorn process (`Ctrl+C` in its terminal) before restarting.

Open **Cloud Shell → Web Preview → Preview on port 8000**, then visit `/docs`. If the preview URL includes `?authuser=0`, use `.../docs?authuser=0` (not `...?authuser=0/docs`). In Swagger, use **POST `/api/v1/recommendations`** and the regional sample request below. Expect `drive_minutes` and road `distance_km` for results with valid routes. Regional requests evaluate at most **10 destinations** per search, and can return fewer than 10 recommendations.

You must have enabled `routes.googleapis.com`, configured a Routes API-restricted key, and stored that key in Secret Manager for regional requests. To enable the service from Cloud Shell:

```bash
gcloud services enable routes.googleapis.com --project="$(gcloud config get-value project)"
```

**Security:** Never paste database URLs or API key values into GitHub, issues, logs, or chat. Secrets exported in Cloud Shell persist in that shell session; stop the server and run `unset DATABASE_URL GOOGLE_ROUTES_API_KEY` when finished. For production, inject the secrets into the **FastAPI Cloud Run service** using Secret Manager, not into client-side code. The API service has not been confirmed deployed with this new regional feature.

### Recommend family activities

`POST /api/v1/recommendations`

```json
{
  "city": "Calgary",
  "children_ages": [2, 6],
  "interests": ["animals", "nature"],
  "activity_type": "any",
  "budget": "any",
  "max_results": 10
}
```

Returns up to 10 candidates, with names, addresses, optional URLs, scores, reasons, parent tips and warnings. When fewer eligible records exist, it returns fewer than 10 rather than fabricating places.

## Data providers

Set `PLACES_PROVIDER`:

| Value | Required configuration | Purpose |
|---|---|---|
| `mock` (default) | None | Fictional venues for local testing |
| `postgres` | `DATABASE_URL` | Supabase PostgreSQL curated/licensed activities |
| `google` | `GOOGLE_MAPS_API_KEY` | Live Google Places Text Search (usage charges possible) |

The PostgreSQL schema is defined in `app/database.py`. Use the **Supabase Session Pooler** connection URL and do not commit credentials. For the full Cloud Shell restart procedure, including both Secret Manager credentials, see **Restart FastAPI in Google Cloud Shell** above.

The table should have row-level security enabled, and production access should use least-privilege database accounts. Store the production `DATABASE_URL` in Google Cloud Secret Manager. Rotate any credential that was previously exposed.

## Weather-aware recommendations (optional)

Little Roam can apply a **same-day forecast** to activity ranking for Calgary, Canmore, and Banff. This uses the official Open-Meteo API interface with daily maximum temperature, maximum precipitation probability, maximum wind speed, and weather code. See [WEATHER_INTEGRATION.md](WEATHER_INTEGRATION.md) for details, limitations, test instructions, and provider licensing.

- **Default:** `WEATHER_PROVIDER=off`. No weather requests or forecast-based adjustments.
- **Evaluation only:** `WEATHER_PROVIDER=open_meteo`. The public endpoint's free access is for non-commercial usage. Before launching a commercial site, arrange a suitable paid/commercial weather service or use an alternative provider with appropriate terms.
- Weather is based on **today in America/Edmonton**, not user-selected future days, real-time weather, or a weather alert feed.
- In a multi-town regional search, forecast context is associated with the activity's **nearest supported town**, not necessarily the Calgary search origin.
- On days with adverse forecast indicators, indoor activities get a modest relevance boost; outdoor activities are not removed.
- Forecast lookups are cached in-process for 15 minutes. Provider failures do not interrupt recommendations.

To try weather locally in Cloud Shell after fetching the latest code and configuring PostgreSQL:

```bash
export WEATHER_PROVIDER=open_meteo
python -m pytest -q
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Run `POST /api/v1/recommendations` in Swagger. Returned activities may include `weather_summary` and `weather_source`. Do not present this forecast as confirmation that an outdoor activity is safe, open, or suitable for a child. Set `WEATHER_PROVIDER=off` to disable the feature.

## Postal-code regional search and opening hours (prototype)

Regional requests can now include an **Alberta postal code** (example: `T2P 1J9`). The backend geocodes that approximate postal area, then uses Google Routes for drive times to **at most ten candidate attractions**. City-centre fallback continues to work when no postal code is supplied. Postal codes are not stored in the activity database or passed to the optional OpenAI explanation.

```json
{
  "city": "Calgary",
  "postal_code": "T2P 1J9",
  "search_scope": "regional",
  "max_drive_minutes": 120,
  "children_ages": [2, 6],
  "interests": ["nature", "playground"],
  "activity_type": "any",
  "budget": "any",
  "max_results": 10
}
```

`GOOGLE_GEOCODING_API_KEY` must be a **separate Geocoding API-restricted key**; it is not interchangeable with the Routes-only key. Invalid or unverified postal codes return an error rather than a made-up location. Use the detailed [Postal/Bow Valley/Hours guide](POSTAL_BOW_VALLEY_HOURS.md).

The [Bow Valley seed](sql/seed_bow_valley.sql) now includes **12 official-source Canmore/Banff attractions**. Reapply the SQL to Supabase to add the six new venues. The additional six do not yet have verified coordinates and will appear only in city-specific searches until they are geolocated from an authorized source; the original six have a separate [coordinate backfill](sql/backfill_bow_valley_coordinates.sql).

Operating hours are optional with `HOURS_PROVIDER=google_places` and a separate Places API-restricted `GOOGLE_MAPS_API_KEY`. The returned venue may have `hours_status`, `published_weekly_hours`, `hours_checked_at` and `hours_source_url`. If no exact Google Place ID is available, the result explicitly remains `unknown`. For curated Supabase activities, apply [the optional vetted Place ID mapping table](sql/activity_place_mappings.sql) and link only reviewed IDs. **These are venue hours, not a promise of an activity or class being offered.** Places Details hours use paid Enterprise-tier fields; the number of calls is capped at ten per request.

These features are implemented in GitHub, but the Geocoding and Places integrations are **not yet verified against live services or deployed**. Leave the daily Calgary importer untouched.

## Activity ingestion and daily refresh

- `app/refresh.py` reads an authorized HTTPS JSON activity feed and upserts records using stable IDs.
- `examples/activities-feed.example.json` contains fictional sample data.
- `POSTGRES_DAILY_REFRESH.md` documents the generic refresh workflow.
- `app/calgary_import.py` imports permitted Calgary recreation-facilities records with validation and stable-ID upserts. The Calgary Cloud Run Job and daily trigger have been configured.

Calgary pipeline: **Cloud Scheduler (daily) → Cloud Run Job → validated Calgary recreation data → Supabase PostgreSQL**. Check recent Cloud Run execution logs to confirm each scheduled run succeeds.

Daily scheduler configuration is in place; routine execution health and monitoring are not yet verified. Prefer incremental updates, record source attribution, and alert on failed jobs. Only store data you are licensed to retain; Google Places API content has additional caching/storage restrictions.

## Deployment

See [CLOUD_RUN_DEPLOY.md](CLOUD_RUN_DEPLOY.md) for private Cloud Run deployment. The initial script deploys in mock mode. For PostgreSQL mode, configure `PLACES_PROVIDER=postgres` and inject `DATABASE_URL` through Secret Manager.

Cloud Run, source builds, network traffic, AI requests, Google Routes/Places and managed database usage can incur charges. Configure billing alerts and quotas before public launch.

## Tests

```bash
python -m pytest -q
```

## Roadmap

1. Monitor the scheduled Calgary importer and verify source licensing and deduplication.
2. Expand ingestion to additional official Canmore and Banff sources.
3. Add verified family-specific activity data: ages, pricing, opening times and event schedules.
4. Improve driving-time search candidate selection, routing cost controls and licensed Canadian weather coverage.
5. Add authentication, usage limits, evaluation, and the family-facing website.
6. Expand to additional Canadian cities and bilingual support.

## Data accuracy and privacy

Recommendations are informational, not guarantees of admission, hours, safety or suitability. Verify details at the source. Collect minimal information about children, and avoid storing exact birth dates or home addresses unless genuinely necessary.

---
Little Roam is an independent project for Canadian families.

## Bow Valley: Canmore and Banff

The repository includes an idempotent [12-venue Canmore and Banff seed](sql/seed_bow_valley.sql) and a [guide to official town data sources](BOW_VALLEY_DATA_SOURCES.md). Apply the SQL to Supabase for initial coverage. The curated venues are not yet automatically refreshed; town event calendars require a separate dated-events model and access/licensing review. Single-city search is the default; optional regional mode supports driving-time searches.

## Regional recommendations by driving time

The backend supports a **30-, 60-, or 120-minute** regional driving preference from a geocoded Alberta postal-code area, or from an approximate Calgary, Canmore, or Banff centre if no postal code is provided. It uses the paid Google Routes API; the existing single-city search remains the default and does **not** require a Routes key.

```json
{
  "city": "Calgary",
  "search_scope": "regional",
  "max_drive_minutes": 120,
  "children_ages": [2, 6],
  "interests": ["nature", "recreation"],
  "activity_type": "any",
  "budget": "any",
  "max_results": 10
}
```

For regional results, `drive_minutes` is the traffic-unaware Google driving duration and `distance_km` is road distance. Without a postal code, these are calculated **from an approximate town centre**. With a postal code, they are calculated from the approximate postal area—not the family's exact address. No route, unknown coordinates, or a failed Routes call will ever be replaced with a guessed drive time.

To enable:
1. Use `PLACES_PROVIDER=postgres` and your Supabase `DATABASE_URL`.
2. Run the [Bow Valley seed](sql/seed_bow_valley.sql) and [coordinate backfill](sql/backfill_bow_valley_coordinates.sql) if not already applied.
3. For postal-code searches, also enable Geocoding API and configure a restricted GOOGLE_GEOCODING_API_KEY (see guide). Enable Google Routes API and supply `GOOGLE_ROUTES_API_KEY` securely through GCP Secret Manager.
4. Execute the tests, then redeploy the **FastAPI Cloud Run service**. The existing Calgary daily importer and Cloud Scheduler trigger remain unchanged.

See [DRIVING_TIME_SEARCH.md](DRIVING_TIME_SEARCH.md) for complete setup, API quota/cost controls and limitations. To bound costs, the MVP routes at most **10 candidate destinations per search**; this may omit relevant venues. Driving times are not traffic-aware or departure-time-specific. Nationwide origins and postal-code routing are future work.
