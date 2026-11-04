"""Scheduled ingestion from an independently owned/licensed JSON activity feed.

Expected document: {"activities":[{...}]} (see examples/activities-feed.example.json).
Run as Cloud Run Job: python -m app.refresh
"""
import json
import os
import logging
from datetime import datetime, timezone
import httpx
from pydantic import BaseModel, Field, HttpUrl, field_validator
from .database import DDL
from .models import Province, ActivityType, Budget

logger=logging.getLogger(__name__)

class FeedActivity(BaseModel):
    source_id: str = Field(min_length=1,max_length=100,pattern=r'^[a-zA-Z0-9_-]+$')
    activity_id: str = Field(min_length=1,max_length=200)
    city: str = Field(min_length=2,max_length=80)
    province: Province
    name: str = Field(min_length=2,max_length=250)
    address: str = Field(min_length=2,max_length=300)
    latitude: float | None = Field(default=None,ge=-90,le=90)
    longitude: float | None = Field(default=None,ge=-180,le=180)
    website_url: HttpUrl | None = None
    activity_type: ActivityType = 'any'
    categories: list[str] = Field(default_factory=list,max_length=30)
    price_category: Budget = 'any'
    min_age: int | None = Field(default=None,ge=0,le=17)
    max_age: int | None = Field(default=None,ge=0,le=17)
    source_url: HttpUrl
    active: bool = True

    @field_validator('source_id')
    @classmethod
    def disallow_google_as_source(cls, value):
        if value.lower().startswith(('google','places')):
            raise ValueError('Do not ingest Google Places content into this persistent feed')
        return value

class Feed(BaseModel):
    activities: list[FeedActivity] = Field(max_length=10000)

UPSERT = """
INSERT INTO activities
(source_id,activity_id,city,province,name,address,latitude,longitude,
 website_url,activity_type,categories,price_category,min_age,max_age,active,source_url,last_seen_at,updated_at)
VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW(),NOW())
ON CONFLICT (source_id,activity_id) DO UPDATE SET
city=EXCLUDED.city, province=EXCLUDED.province, name=EXCLUDED.name,
address=EXCLUDED.address, latitude=EXCLUDED.latitude, longitude=EXCLUDED.longitude,
website_url=EXCLUDED.website_url, activity_type=EXCLUDED.activity_type,
categories=EXCLUDED.categories, price_category=EXCLUDED.price_category,
min_age=EXCLUDED.min_age, max_age=EXCLUDED.max_age, active=EXCLUDED.active,
source_url=EXCLUDED.source_url,last_seen_at=NOW(),updated_at=NOW();
"""

def refresh(feed:Feed, database_url:str)->int:
    # Validate the entire feed before writing anything. A repeat run updates rather than duplicates.
    # Never delete entries solely because they were absent from a partial source feed.
    records=feed.activities
    seen=set()
    for record in records:
        key=(record.source_id, record.activity_id)
        if key in seen:
            raise ValueError('Duplicate activity key in source feed')
        seen.add(key)
    import psycopg
    with psycopg.connect(database_url) as conn:
        with conn.cursor() as cur:
            cur.execute(DDL)
            for a in records:
                cur.execute(UPSERT,(a.source_id,a.activity_id,a.city,a.province,a.name,a.address,
                                  a.latitude,a.longitude,str(a.website_url) if a.website_url else None,
                                  a.activity_type,a.categories,a.price_category,a.min_age,a.max_age,
                                  a.active,str(a.source_url)))
    return len(records)

def main():
    url=os.environ.get('ACTIVITY_FEED_URL','')
    db=os.environ.get('DATABASE_URL','')
    if not url.startswith('https://') or not db:
        raise SystemExit('ACTIVITY_FEED_URL (https) and DATABASE_URL required')
    with httpx.Client(timeout=30,follow_redirects=False) as client:
        response=client.get(url)
        response.raise_for_status()
    feed=Feed.model_validate(response.json())
    count=refresh(feed,db)
    logger.warning('Updated %s activity records from the permitted source feed',count)
    print(json.dumps({'status':'ok','upserted':count,'refreshed_at':datetime.now(timezone.utc).isoformat()}))

if __name__=='__main__':
    main()
