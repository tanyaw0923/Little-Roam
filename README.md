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
- ✅ Optional weather-aware ranking locally tested (public/cloud service not yet deployed); outing-date selection newly implemented and awaiting tests
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
       +-- Optional Open-Meteo outing-date forecasts (evaluation/non-commercial use)
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

### Plan an outing on a specific date

Requests can include **`visit_date`** in `YYYY-MM-DD` format. If omitted, the API uses today's date in Alberta. The supported window is today through 15 days ahead. The optional Open-Meteo weather provider requests that **exact day's daily forecast** separately for Calgary/Canmore/Banff destinations; it does not invent forecasts beyond the provider's published horizon. See [WEATHER_INTEGRATION.md](WEATHER_INTEGRATION.md).

Example for November 8, 2026 (update to a date within 15 days of the day you test):

```json
{
  "city": "Calgary",
  "visit_date": "2026-11-08",
  "children_ages": [2, 6],
  "interests": ["nature", "swimming"],
  "max_results": 10
}
```

**Hours are not yet confirmed for the selected visit date.** The API distinguishes the venue's reported **open-now** status and published weekly opening hours from `hours_for_visit_date: "unknown"`. Swimming, skating, holiday opening and other session schedules require separate date-specific evidence; never infer them from weekly hours. Optional live Places lookups incur charges and require verified Place ID mappings. The City of Calgary daily importer is unchanged.

### Recommend family activities

`POST /api/v1/recommendations`

**No province input is required.** The current Alberta-only MVP automatically uses `AB` internally for Calgary, Canmore, Banff, and Alberta postal codes. The response still includes the resolved province for clarity. When Little Roam expands across Canada, we can infer province from validated postal-code or geocoded location data instead of asking parents to select it.

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

## Visit-date opening hours\n\nFor each recommendation, Little Roam identifies the weekday of `visit_date` (or today's date in Alberta if omitted), then returns only that day's line in `published_weekly_hours` and `visit_day_hours`. For example, a Friday Banff search may return `\"Friday: 11 a.m. - 5 p.m. (Oct 16 - May 14)\"` rather than the full seven-day schedule. Recognized month/day seasonal ranges are checked, including ranges crossing New Year. Explicit dated notices remain in `hours_date_notice`. `hours_for_visit_date` remains `unknown`: ordinary schedules do not prove that an attraction or session will actually be available. No database migration is required for this filtering change.\n\n## Official website operating hours (new, backend only)

Little Roam now supports **either live Google Places hours or independently verified hours from an operator-reviewed official website**. The latter is stored in a **separate** Supabase ledger, not mixed with Google's licensed data and not overwritten by the Calgary importer.

Set up the official-site path in the **Supabase SQL Editor**, in order:

1. Apply [sql/activity_official_hours.sql](sql/activity_official_hours.sql) to create the optional ledger table.
2. Ensure [sql/seed_bow_valley.sql](sql/seed_bow_valley.sql) has already inserted Bow Valley venues.
3. Apply [sql/seed_verified_official_hours.sql](sql/seed_verified_official_hours.sql) to load **two checked examples**: the Town of Banff's Fenlands public building hours, and Parks Canada's Cave and Basin winter hours. The source was inspected **2026-11-06**, with records expiring **2026-11-20**. After expiry the API rejects this outdated evidence until someone rechecks and updates it. These records do **not** promise public skating, museum programming, or holiday access.

In the running **FastAPI Cloud Shell environment**:

```bash
export PLACES_PROVIDER=postgres
export OFFICIAL_HOURS_PROVIDER=postgres
# OPTIONAL: leave Places off until its restricted API key exists
export HOURS_PROVIDER=off
export WEBSITE_PROVIDER=off
export PLACE_MATCH_PROVIDER=off
```

The existing `DATABASE_URL` is sufficient; no Google key is required for sourced official-site schedules. You can enable `HOURS_PROVIDER=google_places` as well once your Places key is configured. In that case **fresh official-site weekly descriptions take precedence** when present, while `hours_status` remains the separately attributed Google *open-now* reading. Returned fields include:

- `visit_day_hours`: the single published opening-hours line matching the `visit_date` weekday, or `null` when unavailable/outside a recognized seasonal window.
- `published_weekly_hours`: now returns **only the matching visit-day line** (zero or one element) instead of all seven weekdays. Matching is by weekday label, not array position.
- `hours_source`: `official_website`, `google_places`, or `unknown`.
- `hours_source_url`: direct official venue schedule page (or Google Maps link when Google is the source).
- `hours_checked_at`: when the listed schedule was inspected.
- `hours_schedule_verified`: true when a non-stale schedule exists for the **selected weekday**; it does not mean actual opening or program availability has been confirmed.
- `hours_status`, `hours_status_source`, `hours_status_checked_at`: live venue open/closed status, only when Google supplies it.
- `hours_date_notice`: explicitly documented notice for the selected date, if available.
- `hours_for_visit_date`: still `unknown`. Even published weekly hours and a dated notice do not confirm a specific activity will take place at the selected time.

**Important:** Official page scraping is **not enabled**. Today's solution uses reviewed records or Google Places live responses; arbitrary websites can have misleading or JavaScript-rendered schedules. To add other venues, review the official source, enter real hours with source URL, verification time, expiry date, and any dated exceptions into `activity_official_hours`. The API drops expired or old (over 30 days) verified schedules automatically. Refer to the migration and example seed for the supported format.

## Venue websites and opening hours (backend only)

Little Roam can optionally use **Google Places API (New)** to show official venue websites and business opening hours in the existing FastAPI recommendation JSON. It does not require a frontend or new Supabase data columns.

- **First:** return the independently sourced `website_url` in Supabase if present; never overwrite it.
- **For other venues:** when a Google Place ID is mapped, fetch `websiteUri` live from Place Details. `website_source` indicates `curated`, `google_places` or `unknown`. Google Maps search links are always available as a **separate** `google_maps_url` fallback, **not** a made-up official website.
- **When no mapped Place ID exists:** optional exact-name-and-nearby-coordinate Text Search finds a likely Google Place ID **only** if the name matches exactly after punctuation normalization AND coordinates are within 350 m. Ambiguous matches are discarded. The IDs are used per request, not automatically saved to Supabase.
- **Business hours:** current `hours_status` (`open_now`, `closed_now`, `permanently_closed` or `unknown`), `published_weekly_hours`, `hours_checked_at` and `hours_source_url` are returned from Google when available. `hours_for_visit_date` remains `unknown` because business opening hours cannot confirm a specific future swimming, skating or museum program.
- **Cost controls:** up to five billable Text Search matching requests and ten combined Place Details requests per recommendation request. Website and hours are requested in **one** Place Details call per matched attraction; enable billing alerts and API quotas.
- **Google policies:** display Google Maps attribution for Places-derived data. Google Places content cannot be stored or scraped into the Supabase activity table; this integration only fetches it during the request. The Google Place ID is exempt from standard caching restrictions. Review Google Maps Platform service terms before launching.

To enable in a **development shell**, first enable **Places API (New)** in the GCP project and create a **server-side Places API-restricted key** under `GOOGLE_MAPS_API_KEY`; the Routes-only and Geocoding-only API keys will not work for this. Store the key in Secret Manager under `little-roam-places-key` (see [POSTAL_BOW_VALLEY_HOURS.md](POSTAL_BOW_VALLEY_HOURS.md)).

```bash
export GOOGLE_MAPS_API_KEY="$(gcloud secrets versions access latest --secret=little-roam-places-key)"
export PLACE_MATCH_PROVIDER=google_places
export WEBSITE_PROVIDER=google_places
export HOURS_PROVIDER=google_places
```

Restart FastAPI after exporting these values:

```bash
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

If `GOOGLE_MAPS_API_KEY` is unset or Google fails, recommendations continue without verified URLs/hours. If the existing Supabase rows have no coordinates, the automatic ID matcher cannot verify them: use an authorized coordinate source and/or the optional [reviewed Place ID mapping SQL](sql/activity_place_mappings.sql). The first five unmatched results are evaluated per request, so some venues may remain unknown even when Google offers a matching listing.

Google Places field documentation: https://developers.google.com/maps/documentation/places/web-service/place-details ; policies: https://developers.google.com/maps/documentation/places/web-service/policies

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
