# Regional recommendations by driving time

## Overview

The Little Roam recommendation API supports two scopes:
- `search_scope="city"` (default): exact city search from PostgreSQL. Does not call a driving API.
- `search_scope="regional"`: choose a maximum driving time of **30**, **60** or **120** minutes. Only Calgary, Canmore and Banff, Alberta are supported as search origins in this MVP.

Example:

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

The response provides `drive_minutes` and road `distance_km` for regional results. The origin is the **approximate municipal centre**, not the family's home or current location. Travel time uses **Google Routes API Compute Route Matrix** with `TRAFFIC_UNAWARE` — typical traffic-agnostic routing based on road conditions, not a live departure-time forecast.

## How routing works

1. Query authorized, geolocated PostgreSQL records within a generous **250 km aerial** prefilter around the origin.
2. Apply activity type, price and age filters; rank by interest relevance and aerial proximity.
3. Shortlist **at most 10** destinations per request; missing-coordinates or far-out locations are excluded.
4. Request one origin-to-many-destinations route matrix from Google Routes (Essentials tier, no traffic-aware mode).
5. Keep only destinations with a returned route duration within the requested threshold.
6. Rank and return up to 10 activities. Missing/error routes are never converted into invented drive times.

This is an MVP optimization: the top-10 preselection and 250 km prefilter may omit valid results. In particular, **a regional search can return fewer than 10 results even if more suitable venues exist**. Expand to staged routing and database geospatial indexes once usage justifies it.

## Configure the Google Routes API

1. In [Google Cloud APIs & Services](https://console.cloud.google.com/apis/library), enable **Routes API** (`routes.googleapis.com`) in the Little Roam project and ensure billing is enabled.
2. Create a dedicated **server-side** API key restricted to **Routes API**. Set practical quota limits; do not expose this key to the browser or commit it to GitHub.
3. For local development in Cloud Shell, securely export `GOOGLE_ROUTES_API_KEY` using a hidden prompt:
   ```bash
   read -rsp "Google Routes API key: " GOOGLE_ROUTES_API_KEY; echo
   export GOOGLE_ROUTES_API_KEY
   ```
4. Set `PLACES_PROVIDER=postgres`, provide the rotated Supabase `DATABASE_URL`, then start FastAPI and test in Swagger.
5. For Cloud Run, store the key in **Google Secret Manager**, grant your **FastAPI service runtime identity** access, and attach it as the `GOOGLE_ROUTES_API_KEY` environment variable. Do not attach this to the Calgary daily-refresh job, which does not use driving routes.

To enable the public API, add authentication, rate limits and a request budget first. Otherwise malicious or excessive regional queries can incur Routes API charges.

## Pricing and quotas

Google Routes Compute Route Matrix is billed **per element**, meaning one origin times each destination. A maximum of 10 destinations consumes up to **10 elements/search**. Current published Essentials global pricing lists **10,000 free monthly elements** and then **US$5 per 1,000 elements** in the first paid tier, or approximately **US$0.05 for a 10-destination request after free usage**. Other charges may apply. Set daily quotas and monitor costs.

Official references:
- [Google Routes API usage & billing](https://developers.google.com/maps/documentation/routes/usage-and-billing)
- [Google Maps Platform pricing](https://developers.google.com/maps/billing-and-pricing/pricing)
- [Compute Route Matrix field masks](https://developers.google.com/maps/documentation/routes/choose_fields)

## Test

```bash
python -m pytest -q
```

The regional tests stub Google Routes responses, so they should not incur API charges. Run one real regional request only after configuring billing and quotas.

Important: the Calgary daily importer remains unchanged; the driving preference is applied to recommendation requests, not source ingestion.
