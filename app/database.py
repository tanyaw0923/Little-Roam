"""Read from PostgreSQL; never persist unlicensed Google Places content."""
import os
import asyncio
from fastapi import HTTPException
from .models import Candidate, RecommendationRequest
from .geo import bounding_box, origin_for

DDL = """
CREATE TABLE IF NOT EXISTS activities (
    source_id TEXT NOT NULL,
    activity_id TEXT NOT NULL,
    city TEXT NOT NULL,
    province VARCHAR(2) NOT NULL,
    name TEXT NOT NULL,
    address TEXT NOT NULL,
    latitude DOUBLE PRECISION,
    longitude DOUBLE PRECISION,
    website_url TEXT,
    activity_type TEXT NOT NULL DEFAULT 'any'
        CHECK (activity_type IN ('any','indoor','outdoor')),
    categories TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
    price_category TEXT NOT NULL DEFAULT 'any'
        CHECK (price_category IN ('any','free','paid')),
    min_age SMALLINT,
    max_age SMALLINT,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    source_url TEXT NOT NULL,
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (source_id, activity_id)
);
CREATE INDEX IF NOT EXISTS activities_city_active_idx
ON activities (province, lower(city)) WHERE active = TRUE;
"""

def require_db_url():
    url=os.getenv('DATABASE_URL')
    if not url:
        raise HTTPException(status_code=503,detail='DATABASE_URL not configured')
    return url

def _fetch(r: RecommendationRequest):
    import psycopg
    from psycopg.rows import dict_row

    with psycopg.connect(require_db_url(), row_factory=dict_row, connect_timeout=8) as conn:
        with conn.cursor() as cur:
            if r.search_scope == 'regional':
                # Do not invent locations for records that have no coordinates.
                origin = origin_for(r.province, r.city)
                if origin is None:
                    raise ValueError('Unsupported regional search origin')
                min_lat, max_lat, min_lon, max_lon = bounding_box(*origin, 250)
                cur.execute("""SELECT source_id, activity_id, name, address, latitude, longitude,
                                      website_url, activity_type, categories, price_category,
                                      min_age, max_age
                               FROM activities
                               WHERE active = TRUE AND province = %s
                                 AND latitude BETWEEN %s AND %s
                                 AND longitude BETWEEN %s AND %s
                               ORDER BY updated_at DESC, activity_id
                               LIMIT 10000""",
                            (r.province, min_lat, max_lat, min_lon, max_lon))
            else:
                cur.execute("""SELECT source_id, activity_id, name, address, latitude, longitude,
                                      website_url, activity_type, categories, price_category,
                                      min_age, max_age
                               FROM activities
                               WHERE active = TRUE AND province = %s
                                 AND lower(city) = lower(%s)
                               ORDER BY updated_at DESC, activity_id
                               LIMIT 500""",
                            (r.province, r.city))
            rows = cur.fetchall()

    candidates = []
    for x in rows:
        candidates.append(Candidate(
            place_id=f"{x['source_id']}:{x['activity_id']}",
            name=x['name'], address=x['address'],
            latitude=x['latitude'], longitude=x['longitude'],
            website_url=x['website_url'], activity_type=x['activity_type'],
            categories=x['categories'], price_category=x['price_category'],
            min_age=x['min_age'], max_age=x['max_age'], source='curated'))
    return candidates

async def database_candidates(r: RecommendationRequest):
    try:
        return await asyncio.to_thread(_fetch,r)
    except Exception as exc:
        raise HTTPException(status_code=503,detail='Activity database unavailable') from exc
