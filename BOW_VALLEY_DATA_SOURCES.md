# Bow Valley expansion: Canmore and Banff

This first expansion adds **six curated, permanent venues** from official municipal pages. It does **not** ingest dated events automatically yet.

## Load into Supabase

Open Supabase SQL Editor and execute [sql/seed_bow_valley.sql](sql/seed_bow_valley.sql) once. Re-running is safe; its upsert keys avoid duplicates. The existing Calgary source is unchanged.

Check by city:

```sql
SELECT city, count(*) FROM public.activities
WHERE active = TRUE AND province = 'AB'
GROUP BY city ORDER BY city;
```

## Test the recommendation API

Set `PLACES_PROVIDER=postgres` and a valid `DATABASE_URL`. In Swagger, call `POST /api/v1/recommendations` with `city: "Canmore"` or `city: "Banff"`, `province: "AB"`, `budget: "any"`. Both towns are queried individually. **A search for Calgary currently does not include Banff or Canmore**, because the API filters by exact city. The `radius_km` field is not enforced; regional geographic search should be implemented separately, with real coordinates and a validated origin.

## Official sources for further ingestion

**Canmore**
- Open-data parks: https://opendata-canmore.opendata.arcgis.com/datasets/a8f48bbeea6d43bcb67014f8c1a9824a_0/explore
- ArcGIS parks layer: https://services.arcgis.com/USaXRc3mZF0nhsUu/ArcGIS/rest/services/Canmore_Parks/FeatureServer/0
- Town parks and playground information: https://www.canmore.ca/your-community/recreation/outdoor-recreation/parks-playgrounds-sport-fields
- Community calendar (free drop-in programs): https://www.canmore.ca/your-community/community-supports-and-services/communitycalendar
- Recreation calendar: https://www.canmore.ca/your-community/recreation/recreationcalendar

**Banff**
- Town places: https://banff.ca/1156/Places-Around-Town
- Open-data spatial catalogue: https://maps.banff.ca/opendata/
- Town community events: https://www.banff.ca/m/calendar

## Before automatic event ingestion

1. Confirm each source's automated access and republishing conditions. Open-data licences may not cover the entire town website and its event descriptions.
2. Add an `events` table with event identifiers, start/end timestamps, timezone, registration rules, age limits, and expiry. Do not import a scheduled session as an always-available place.
3. Store official URL, attribution and last-verified timestamp for each record. Capture missing prices and age restrictions as unknown.
4. Dry-run new source adapters, review sample records and run idempotency tests before scheduling them.
5. Keep the existing daily Calgary importer isolated until each new adapter is validated.
