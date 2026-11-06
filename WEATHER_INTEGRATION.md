# Little Roam weather integration (prototype)

## Purpose

Add **optional, date-specific daily forecast context** to the activity ranking. This is not a real-time safety service and does not determine whether a venue is open, accessible, age-appropriate, or safe.

The initial provider is **Open-Meteo Forecast API**: https://open-meteo.com/en/docs

**Licensing:** the public Open-Meteo free endpoint is intended for non-commercial use. Use this implementation only for local/prototype evaluation until you have arranged a suitable commercial agreement or replaced the provider with a service whose licence permits your use. Provide the required Open-Meteo and underlying weather-data attribution in any user-facing product. See https://open-meteo.com/en/terms .

Environment and Climate Change Canada also offers public weather services via MSC GeoMet: https://api.weather.gc.ca/ . It may be a better Canada-specific provider for later phases, but its API structure and licence terms require a separate integration.

## What is implemented

- Opt-in `WEATHER_PROVIDER=open_meteo` (default: `off`).
- Daily forecast for **the requested visit date** (today if omitted), with local `America/Edmonton` time zone.
- Uses maximum temperature, maximum precipitation probability, maximum wind speed, and WMO weather code.
- Currently supports municipal-centre forecast points for **Calgary, Canmore, Banff**. Each regional activity uses the nearest of those towns by coordinates. Forecasts are **town-level, not precise attraction/mountain trail forecasts**.
- Requests accept an optional `visit_date` (ISO `YYYY-MM-DD`), validated from today through 15 days ahead. Forecasts beyond that window are not estimated or fabricated.
- On a cold, very hot, windy, or precipitation-heavy daily forecast, the algorithm gives indoor venues a small score boost and outdoor venues a small penalty. On other days it slightly favors outdoor activities. Never removes activities purely due to forecast.
- Returns optional `weather_summary` and `weather_source` fields for each recommendation. If weather data is missing, both stay null.
- Up to one forecast request per relevant town and visit date, cached in-process for 15 minutes. No database migration or extra Cloud Scheduler job required.
- Weather errors fail open: rankings revert to non-weather factors for affected destinations.
- The Cloud Run Calgary daily activity importer is unchanged.

**Not yet supported:** Hour-by-hour conditions for actual outing time; alerts, air quality/smoke, UV index, wind chill, ice/snow conditions, road closures, current user GPS, real-time precipitation radar, weather for arbitrary Canadian towns, or live forecast verification. This integration must not be described as real-time weather or a safety recommendation.

## Local test

```bash
cd ~/Little-Roam/Little-Roam
git pull --ff-only origin main
python -m pytest -q

export PLACES_PROVIDER=postgres
export WEATHER_PROVIDER=open_meteo

# Requires an accessible Cloud Shell identity with permission to read the secret.
export DATABASE_URL="$(gcloud secrets versions access latest --secret=little-roam-database-url)"

python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Use the existing Swagger `POST /api/v1/recommendations` endpoint. Example city-only body:

```json
{
  "city": "Calgary",
  "visit_date": "2026-11-08",
  "province": "AB",
  "children_ages": [2, 6],
  "interests": ["nature", "swimming"],
  "activity_type": "any",
  "budget": "any",
  "max_results": 10
}
```

For regional mode also set `"search_scope":"regional","max_drive_minutes":120`, and configure `GOOGLE_ROUTES_API_KEY`; driving requests remain capped at ten routing destinations. Weather API calls do **not** incur Google Routes charges, but the regional routing calls can.

The date in the sample must be today or a future date within the supported 16-day forecast window; update it when running the example. Venue opening hours reported by Google Places are separate from the outing-date forecast and are **not confirmation that a venue or specific program will be open on that day**.

Disable with `export WEATHER_PROVIDER=off`.

## Cloud Run deployment

Do **not** enable the public/free Open-Meteo endpoint for a commercial production deployment without addressing provider terms. For non-commercial evaluation only, after tests pass, update a deployed private FastAPI **service** with:

```bash
gcloud run services update little-roam-api \
  --region=us-central1 \
  --update-env-vars=WEATHER_PROVIDER=open_meteo
```

The update changes the environment variable on the current service revision, but does not upload code. **Deploy the updated FastAPI service code first** using [CLOUD_RUN_DEPLOY.md](CLOUD_RUN_DEPLOY.md), then enable the flag. This does not change the Calgary refresh **job**.

## Tests

`tests/test_weather.py` uses mocked provider responses and checks weather-derived scoring, town localization, in-memory caching, failure behavior, and the opt-out default. No live Open-Meteo calls are required by those tests.

## Future improvements

1. Enable date/time selection and use hourly forecasts at visit time.
2. Support severe weather alerts and air quality with source-specific fields.
3. Integrate Canadian ECCC weather sources or commercial Open-Meteo as permitted.
4. Introduce a weather-provider interface and shared cache for multi-instance Cloud Run.
5. Add user-facing forecast date, provenance, attribution, and 'forecast unavailable' states.
