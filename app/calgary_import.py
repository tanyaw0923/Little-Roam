"""Import City of Calgary Recreation Facilities from its official ArcGIS open-data layer.

Dry-run by default; explicit --apply required to write to PostgreSQL.
Source: https://services1.arcgis.com/AVP60cs0Q9PEA8rH/ArcGIS/rest/services/Recreation_Facility/FeatureServer/0
Attribution: Contains information licensed under the Open Government Licence – City of Calgary.
"""
import argparse
import json
import os
import sys
from urllib.parse import urlparse

import httpx
from .refresh import Feed, FeedActivity, refresh

LAYER_URL = ('https://services1.arcgis.com/AVP60cs0Q9PEA8rH/ArcGIS/rest/'
             'services/Recreation_Facility/FeatureServer/0')
SOURCE_URL = 'https://data.calgary.ca/Recreation-and-Culture/Recreation-Facilities/hxfu-6d96/about_data'
SOURCE_ID = 'calgary_recreation_facilities'
FIELDS = ('OBJECTID,GLOBALID,REC_ID,FACILITY_NAME,COMPLEX_NAME,FACILITY_TYPE,'
          'ADDRESS,WEBSITE,INDR_POOL,OUTDR_POOL,SPRAY_PARK,ICE_INDR,GYM')


def category_tags(a):
    tags = ['recreation']
    facility_type = str(a.get('FACILITY_TYPE') or '').strip().lower()
    if 'aquatic' in facility_type or 'pool' in facility_type or any(
            str(a.get(k) or '').strip().upper() in {'Y', 'YES', 'TRUE', '1'}
            for k in ('INDR_POOL', 'OUTDR_POOL')):
        tags.append('swimming')
    if 'arena' in facility_type or 'ice' in facility_type:
        tags.append('skating')
    if 'leisure' in facility_type or 'recreation' in facility_type:
        tags.append('sports')
    if str(a.get('SPRAY_PARK') or '').strip().upper() in {'Y', 'YES', 'TRUE', '1'}:
        tags.append('spray park')
    return tags


def convert_feature(feature):
    a = feature.get('attributes') or {}
    raw_id = a.get('GLOBALID') or a.get('REC_ID') or a.get('OBJECTID')
    name = str(a.get('FACILITY_NAME') or a.get('COMPLEX_NAME') or '').strip()
    address = str(a.get('ADDRESS') or '').strip()
    if not raw_id or len(name) < 2 or len(address) < 2:
        return None
    website = str(a.get('WEBSITE') or '').strip()
    if website and (urlparse(website).scheme not in {'https', 'http'} or not urlparse(website).netloc):
        website = ''
    # ArcGIS output SR=4326 gives latitude=geometry.y, longitude=geometry.x.
    geom = feature.get('geometry') or {}
    lat, lng = geom.get('y'), geom.get('x')
    if not isinstance(lat, (float, int)) or not isinstance(lng, (float, int)) or not (49 <= lat <= 52 and -116 <= lng <= -112):
        lat = lng = None
    facility_type = str(a.get('FACILITY_TYPE') or '').lower()
    # Mixed recreation centers must not be treated as purely indoor or outdoor.
    activity_type = 'indoor' if ('indoor' in facility_type or 'arena' in facility_type) else 'any'
    return FeedActivity(
        source_id=SOURCE_ID,
        activity_id=str(raw_id).strip().strip('{}').lower(),
        city='Calgary',province='AB',name=name,
        address=f'{address}, Calgary, AB', latitude=lat,longitude=lng,
        website_url=website or None,activity_type=activity_type,
        categories=category_tags(a), price_category='any',
        min_age=None,max_age=None,source_url=SOURCE_URL,active=True)


def transform(features):
    if not isinstance(features, list):
        raise ValueError('Expected ArcGIS features array')
    records = [r for f in features if (r := convert_feature(f)) is not None]
    unique = {}
    for r in records:
        if r.activity_id in unique:
            raise ValueError('Duplicate source identifier: ' + r.activity_id)
        unique[r.activity_id] = r
    if not unique:
        raise ValueError('No usable features returned; refusing empty import')
    return Feed(activities=list(unique.values()))


def fetch_features(client, page_size=500):
    all_features = []
    for offset in range(0, 50000, page_size):
        resp = client.get(LAYER_URL + '/query', params={
            'where':'1=1','outFields':FIELDS,'returnGeometry':'true',
            'outSR':'4326','f':'json','resultOffset':offset,
            'resultRecordCount':page_size,'orderByFields':'OBJECTID ASC'})
        resp.raise_for_status()
        data = resp.json()
        if 'error' in data:
            raise ValueError('ArcGIS source returned an error: ' + str(data['error'].get('message','unknown')))
        batch = data.get('features')
        if not isinstance(batch,list):
            raise ValueError('ArcGIS response missing features')
        all_features.extend(batch)
        if len(batch) < page_size:
            return all_features
    raise ValueError('Unexpectedly large source; refusing partial import')


def main(argv=None):
    parser = argparse.ArgumentParser(description='Calgary recreation import (dry-run by default)')
    parser.add_argument('--apply', action='store_true',help='Write validated records to DATABASE_URL')
    parser.add_argument('--preview', type=int,default=5,help='Number of sample records to show')
    args = parser.parse_args(argv)
    with httpx.Client(timeout=40,follow_redirects=False) as client:
        feed = transform(fetch_features(client))
    print(json.dumps({'source_id':SOURCE_ID,'validated':len(feed.activities),
          'dry_run':not args.apply,
          'samples':[a.model_dump(mode='json') for a in feed.activities[:max(0,min(args.preview,20))]]},indent=2))
    if args.apply:
        database_url=os.getenv('DATABASE_URL')
        if not database_url:
            sys.exit('DATABASE_URL is required for --apply')
        print(json.dumps({'status':'saved','upserted':refresh(feed,database_url)}))

if __name__=='__main__':
    main()
