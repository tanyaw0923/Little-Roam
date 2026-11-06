# Postal code, Bow Valley attractions, and opening hours (pre-public MVP)

## What's implemented

### 1) Canadian postal code as origin — Alberta first

The API accepts a Canadian postal code in a `search_scope=regional` request. It validates the postal-code format and, for the first MVP, accepts only Alberta postal codes (starting with `T`). The backend uses Google Geocoding API v3 to obtain an approximate centre for the postal code; **not a street address or household location**. This coordinate replaces the former Calgary/Canmore/Banff town-centre origin for selecting candidates and the Google Routes drive-time calculation.

- Requires **Geocoding API** (`geocoding-backend.googleapis.com`) and a separate **Geocoding API-restricted server API key** (`GOOGLE_GEOCODING_API_KEY`).
- Uses `components=postal_code:...|country:CA` and checks returned components for the exact postal code and Alberta.
- Rejects invalid / unmatched postal codes rather than falling back to an invented location.
- No postal-code geocoding response or household coordinates are stored in PostgreSQL.
- The existing Google Routes API key is **restricted to Routes**, so it cannot be reused for Geocoding.
- Regional Google Routes remains capped at **10 destinations per request**, while Geocoding adds at most one request.
- For a city-only request, postal code is not accepted; use `search_scope=regional`.

Example:

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

The `city` field is currently required for API compatibility; in regional postal mode the **postal code** is used as driving origin. The `city` value does not override the postal geocode.

## 2) Additional Canmore and Banff attractions

Re-run [sql/seed_bow_valley.sql](sql/seed_bow_valley.sql) in Supabase SQL Editor. It now holds **12 permanent attractions** (6 original plus 6 new), sourced from official Town of Canmore, Town of Banff and Parks Canada descriptions:

- Canmore: Elevation Place, Quarry Lake Park, Riverside Park, Centennial Park, Lions Park, Policeman's Creek Boardwalk.
- Banff: The Fenlands, Recreation Grounds, Central Park, Rotary Park Playground, Birch Avenue Playground, Cave and Basin National Historic Site.

Banff Rotary Park and Birch Avenue playground age ranges come from the official Town of Banff Community Parks page. These are equipment age bands, not a safety guarantee.

**Geocoding/coverage limitation:** Only the original six venues have coordinate backfill in [sql/backfill_bow_valley_coordinates.sql](sql/backfill_bow_valley_coordinates.sql). The newly added six are initially city-searchable **but excluded from regional driving-time searches until verified coordinate data is added**. Do not fabricate coordinates, and do not store Google Maps Geocoding API coordinates without checking Google Maps Platform terms. For long-term use, prefer the municipal open GIS data with suitable licensing. The seed SQL deliberately leaves the new six coordinates blank.

These are venues, **not** proof that any public program, skating session, swimming lane, or museum tour is offered at the desired time.

## 3) Opening hours: report verified status or unknown

The API response includes:
- `hours_status`: `open_now`, `closed_now`, or `unknown`.
- `hours_checked_at`: UTC timestamp of a successful Places check, or null.
- `hours_source_url`: Google Maps link where available, or null.
- `hours_verified`: true **only** if a specific Place Details result provides an explicit status.

Set `HOURS_PROVIDER=google_places` to enable optional **live Google Places API (New) Place Details** lookups. This requires `places.googleapis.com` and a Places API-restricted `GOOGLE_MAPS_API_KEY`. `currentOpeningHours.openNow` incurs the **Place Details Enterprise** SKU; review quotas/prices before enabling. Calls are bounded by `max_results <= 10` and a second 10-lookup cap. Data is obtained per request and never stored.

**Important:** Curated activities do not automatically have a Google Place ID. Apply the optional [sql/activity_place_mappings.sql](sql/activity_place_mappings.sql) migration and populate confirmed mappings manually before live hours can work for curated venues. This table stores the linked IDs, **not** Google hours. If there is no mapping or Google has no explicit hours, API status remains **unknown**. Never infer a place ID by matching only a name.

`open_now` is a third-party provider report about the **venue** at request time, not a guarantee about a specific activity or that future hours will match; a venue can be open while the pool or climbing wall is closed. Parks/trails often have no published operating schedule. We do not currently check hours for arbitrary future visit dates. The official source URL should also be shown and consulted before visiting.

## GCP setup (Cloud Shell)

```bash
export PROJECT_ID="$(gcloud config get-value project)"
gcloud services enable geocoding-backend.googleapis.com places-backend.googleapis.com --project="$PROJECT_ID"
```

Google Geocoding API and Places API (New) need **separate API-restricted keys** from the existing Routes API key. Create the keys in [Credentials](https://console.cloud.google.com/apis/credentials), then store them in Secret Manager without copying them into source control:

```bash
read -rsp "Geocoding API key: " NEW_GEOCODE_KEY; echo
printf '%s' "$NEW_GEOCODE_KEY" | gcloud secrets create little-roam-geocoding-key --data-file=-
unset NEW_GEOCODE_KEY

# If enabling live Place Details hours, use a different Places-restricted key:
read -rsp "Places API key: " NEW_PLACES_KEY; echo
printf '%s' "$NEW_PLACES_KEY" | gcloud secrets create little-roam-places-key --data-file=-
unset NEW_PLACES_KEY
```

If either secret name already exists, use `gcloud secrets versions add NAME --data-file=-` rather than `create`. Never print or paste key values. The Google Routes key is still separate.

## Start FastAPI in Cloud Shell

```bash
cd ~/Little-Roam/Little-Roam
git pull --ff-only origin main
python -m pytest -q

export PLACES_PROVIDER=postgres
export WEATHER_PROVIDER=open_meteo  # Prototype/non-commercial use only
export HOURS_PROVIDER=off          # Change to google_places once mappings/Places key are ready

export DATABASE_URL="$(gcloud secrets versions access latest --secret=little-roam-database-url)"
export GOOGLE_ROUTES_API_KEY="$(gcloud secrets versions access latest --secret=little-roam-routes-api-key)"
export GOOGLE_GEOCODING_API_KEY="$(gcloud secrets versions access latest --secret=little-roam-geocoding-key)"

# Only if HOURS_PROVIDER=google_places:
# export GOOGLE_MAPS_API_KEY="$(gcloud secrets versions access latest --secret=little-roam-places-key)"

python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Cloud Shell Web Preview → port 8000 → `/docs`. Test the JSON request above. Health check: `GET /health`.

The Calgary Cloud Run Job and its Cloud Scheduler schedule are **unaffected**. Do not run the old mock-mode `deploy-cloud-run.sh` expecting these features to become public: the FastAPI **service** must be deployed with the appropriate Secret Manager environment variables and IAM access, and its exposure should remain private while testing.

## Sources and licensing

- Canadian postal geocoding: https://developers.google.com/maps/documentation/geocoding/requests-geocoding
- Google Routes: https://developers.google.com/maps/documentation/routes/compute_route_matrix
- Places current opening hours and fields: https://developers.google.com/maps/documentation/places/web-service/reference/rest/v1/places and https://developers.google.com/maps/documentation/places/web-service/data-fields
- Canmore parks: https://www.canmore.ca/your-community/recreation/outdoor-recreation/parks-playgrounds-sport-fields
- Canmore walking trails: https://www.canmore.ca/your-community/recreation/trails-and-pathways/walking-trails
- Banff parks: https://banff.ca/831/Community-Parks
- Banff venues: https://banff.ca/1156/Places-Around-Town
- Parks Canada Cave and Basin: https://parks.canada.ca/lhn-nhs/ab/caveandbasin

### Next stages

1. Source verified coordinates for the six additional venues from licensed municipal GIS data.
2. Confirm Google Place IDs and/or build an official published-hours ingestion process with schedules and stale-data checks.
3. Add a `visit_date` and `visit_time` before making open-at-visit-time claims.
4. Add full Canadian postal-code coverage, geocoder quota controls, and privacy tests.
5. Add family-level request authentication, cost caps and usage throttling before public launch.
