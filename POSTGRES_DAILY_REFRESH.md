# PostgreSQL daily update — Little Roam

## Architecture

- **User API:** Cloud Run service, `PLACES_PROVIDER=postgres`; searches independently curated or licensed data in PostgreSQL. No paid Google Places calls on normal requests.
- **Database:** PostgreSQL (either Supabase hosted PostgreSQL or Cloud SQL PostgreSQL).
- **Daily update:** Cloud Run Job runs `python -m app.refresh` once each day using Cloud Scheduler. It fetches a JSON activity feed you have rights to store, validates the entire feed, then performs upserts in one transaction.
- **Source governance:** Do **not** feed Google's Places API name, address, coordinates, or other protected content into persistent PostgreSQL tables. Google Place IDs alone are generally storage-exempt, but other Places content is restricted. See Google Maps Platform policies.

## Configure the database

Create a PostgreSQL database and connect using a least-privilege user. For initial setup, run once using Python:

```python
from app.database import DDL
import os, psycopg
with psycopg.connect(os.environ['DATABASE_URL']) as conn:
    with conn.cursor() as cur:
        cur.execute(DDL)
```

The refresh job also creates the table if it doesn't exist, so a single DB user with table-create privileges works for initial development. In production, use migrations and separate schema-owner, read-only API and writer roles.

`DATABASE_URL` can be a Supabase PostgreSQL connection URI (with the appropriate TLS settings) or Cloud SQL PostgreSQL URI. Store it in Secret Manager. Never commit the actual URI to GitHub.

## Prepare the source feed

Publish an HTTPS URL containing a JSON object with `activities` as in `examples/activities-feed.example.json`. The example is **fictional and inactive**, not production data. Use your own curated records or feeds with explicit permission to store and republish. Each activity must have a stable `(source_id, activity_id)` key, city, Canadian province, name, address, and a source URL. To deactivate an activity, set `active` to `false`; partial feed gaps never automatically delete existing rows.

## Test refresh locally

```bash
export DATABASE_URL='postgresql://USER:PASSWORD@HOST:5432/DBNAME?sslmode=require'
export ACTIVITY_FEED_URL='https://YOUR-OWN-DOMAIN.example/activities.json'
python -m app.refresh
PLACES_PROVIDER=postgres uvicorn app.main:app --reload
```

## GCP Cloud Run Job

After deploying the service, create a separate **Cloud Run Job** using the same container image (see Cloud Run service image URL in the console). Set its container command to `python`, arguments `-m`, `app.refresh`. Configure `DATABASE_URL` using Secret Manager, and `ACTIVITY_FEED_URL` as a plain env variable. The runtime service account needs secret-access permission and network access to PostgreSQL. If using Cloud SQL, attach the Cloud SQL instance and use its Unix socket connection configuration.

From the Cloud Run console: **Jobs → Create job → select image → Container command/arguments → Secrets and variables**. Set task count 1 and retries appropriate to avoid repeated requests during source outages.

After creating the Job, open its **Triggers** tab → **Add Scheduler Trigger**:
- Frequency: `0 6 * * *` (6:00 AM daily)
- Timezone: `America/Edmonton`
- Service account: dedicated scheduler identity with permission to execute this job

This runs the upsert once daily. Verify successful runs in Cloud Logging; create an alert if it fails. Cloud Scheduler can retry and delivery is not guaranteed exactly once, so the database upsert is idempotent.

## Switch your API to PostgreSQL

Update the Cloud Run service with `PLACES_PROVIDER=postgres` and inject a Secret Manager `DATABASE_URL` secret. Test a city you actually imported. With zero curated records, the endpoint intentionally returns zero results rather than inventing locations.

## Important current MVP limitations

- No PostGIS distance radius filtering yet. `radius_km` is not enforced.
- Google Place IDs, geocoding, and live details can be added separately according to provider terms.
- A daily feed for temporary events should include dates and expiry logic in a future schema migration. This first table models persistent venues/activities, not time-specific calendar events.
- Authentication/rate limiting and age/fee/source verification are still required before public launch.
