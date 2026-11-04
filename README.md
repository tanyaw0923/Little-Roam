# Little Roam Recommendation API — v0.1

Python FastAPI backend for a Canadian family-activity recommender.

## Requirements
Python 3.11+ recommended.

## Install

```bash
python -m venv .venv
# Windows PowerShell: .venv\\Scripts\\Activate.ps1
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # Windows PowerShell: Copy-Item .env.example .env
uvicorn app.main:app --reload
```

Open http://127.0.0.1:8000/docs and try POST /api/v1/recommendations.

Example JSON:
```json
{
  "city": "Calgary", "province": "AB", "children_ages": [2, 6],
  "interests": ["animals", "nature"], "activity_type": "any",
  "budget": "any", "radius_km": 25, "max_results": 10
}
```

## Providers
- `PLACES_PROVIDER=mock`: fictional demo activities, no paid API calls.
- `PLACES_PROVIDER=google`: live Places API (New) text searches; requires `GOOGLE_MAPS_API_KEY`. Activate Places API (New), configure billing and quotas, restrict your key.
- Optional `OPENAI_API_KEY` enables AI-generated copy. Without it the response is deterministic.

**Important limitations:** Version 0.1 does **not** enforce distance or validate the requested city; `radius_km` is a reserved interface field. Canadian city/province inputs are supplied to search, but the results are not yet geofenced. No live events, age verification, weather, opening-hours verification, or actual ticket prices. `free` budget only includes venues explicitly marked free, which Google Places does not establish: in Google mode, this filter generally returns zero recommendations. Do not represent this as a production-ready family recommendation engine. Google Places data usage, storage and display are subject to Google Maps Platform terms; review these before caching or persisting place details.

## Tests
```bash
pytest -q
```

## Suggested v0.2
1. Geocode Canadian city/postal code, calculate haversine distance, enforce radius and country.
2. Verify age suitability, free/paid admissions and opening hours from trusted venue/event sources.
3. Add municipal/community event feeds with explicit event start/end dates.
4. Add weather integration, weather fallback, and reliable citations.
5. Cache only what each provider's terms permit; rate limit API; improve logging and cost monitoring.

## Google Cloud Run deployment

See [CLOUD_RUN_DEPLOY.md](CLOUD_RUN_DEPLOY.md) for Cloud Shell deployment and authenticated smoke testing. The default deployment is a **private Cloud Run service in mock mode**; no external API keys are required.

## PostgreSQL + daily updates (v0.2 scaffold)

Set `PLACES_PROVIDER=postgres` and `DATABASE_URL` to recommend from curated/licensed PostgreSQL records. `app.refresh` performs an idempotent daily upsert from your HTTPS source feed. See [POSTGRES_DAILY_REFRESH.md](POSTGRES_DAILY_REFRESH.md). No real data feed is configured yet and database connection has not been integration-tested. Google Places content should not be persisted except as its terms expressly permit.
