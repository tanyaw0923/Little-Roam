# Little Roam 🧭

**AI-powered family activity discovery for Canadian families.**

Little Roam is an early-stage Python/FastAPI backend that recommends family outings by location, children's ages, interests, indoor/outdoor preference, and price category. It starts in Calgary, Alberta, and is designed to expand across Canada.

## Project status

- ✅ FastAPI and interactive Swagger API tested in Google Cloud Shell
- ✅ Supabase PostgreSQL connected and real Calgary attraction records tested during development
- ✅ Calgary recreation-facilities importer run successfully in the development environment
- ✅ Generic PostgreSQL JSON-feed refresh and unit tests in repository
- ⏳ Calgary-specific importer **not yet committed** to this repository
- ⏳ Scheduled Cloud Run ingestion, weather integration and public website not yet confirmed live

> The API is a working MVP, not a fully verified production activity recommender. Opening hours, prices, age suitability and search radius are not yet comprehensively verified/enforced.

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
       
Approved activity data -> validation/upsert -> PostgreSQL
                          ^
                   Cloud Run Job + Scheduler (planned)
```

| Component | Technology |
|---|---|
| Backend | FastAPI, Python, Pydantic |
| Database | Supabase PostgreSQL + psycopg |
| Recommendations | Python matching/ranking + optional OpenAI |
| Place discovery | Google Places API (New), optional |
| Hosting | GCP Cloud Run |
| Scheduled updates | Cloud Run Jobs + Cloud Scheduler (planned) |
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

### Recommend family activities

`POST /api/v1/recommendations`

```json
{
  "city": "Calgary",
  "province": "AB",
  "children_ages": [2, 6],
  "interests": ["animals", "nature"],
  "activity_type": "any",
  "budget": "any",
  "radius_km": 25,
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

The PostgreSQL schema is defined in `app/database.py`. Connect with the **Supabase Session Pooler** URL; do not put credentials in the repository. In Cloud Shell, for a one-session test:

```bash
export PLACES_PROVIDER=postgres
read -rsp "Supabase connection URL: " DATABASE_URL; echo
export DATABASE_URL
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

The table should have row-level security enabled, and production access should use least-privilege database accounts. Store the production `DATABASE_URL` in Google Cloud Secret Manager. Rotate any credential that was previously exposed.

## Activity ingestion and daily refresh

- `app/refresh.py` reads an authorized HTTPS JSON activity feed and upserts records using stable IDs.
- `examples/activities-feed.example.json` contains fictional sample data.
- `POSTGRES_DAILY_REFRESH.md` documents the generic refresh workflow.
- The Calgary-specific `app/calgary_import.py` has been run in Cloud Shell but **is not included in the current GitHub tree**. Push that file and its tests before building a production importer image.

Planned daily pipeline: **Cloud Scheduler (6 AM America/Edmonton) → Cloud Run Job → validated Calgary/Canadian activity sources → Supabase PostgreSQL**.

A scheduled production job and monitoring are not yet verified. Prefer incremental updates, record source attribution, and alert on failed jobs. Only store data you are licensed to retain; Google Places API content has additional caching/storage restrictions.

## Deployment

See [CLOUD_RUN_DEPLOY.md](CLOUD_RUN_DEPLOY.md) for private Cloud Run deployment. The initial script deploys in mock mode. For PostgreSQL mode, configure `PLACES_PROVIDER=postgres` and inject `DATABASE_URL` through Secret Manager.

Cloud Run, source builds, network traffic, AI requests, Google Places and managed database usage can incur charges. Configure billing alerts and quotas before public launch.

## Tests

```bash
python -m pytest -q
```

## Roadmap

1. Commit and validate the Calgary importer, including source licensing and deduplication.
2. Run a Cloud Run Job manually, then add a daily Scheduler trigger and logging.
3. Add verified family-specific activity data: ages, pricing, opening times and event schedules.
4. Enforce distance filters using PostGIS and integrate Canadian weather.
5. Add authentication, usage limits, evaluation, and the family-facing website.
6. Expand to additional Canadian cities and bilingual support.

## Data accuracy and privacy

Recommendations are informational, not guarantees of admission, hours, safety or suitability. Verify details at the source. Collect minimal information about children, and avoid storing exact birth dates or home addresses unless genuinely necessary.

---
Little Roam is an independent project for Canadian families.
