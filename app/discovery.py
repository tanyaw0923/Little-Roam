import os
import httpx
from fastapi import HTTPException
from .models import Candidate, RecommendationRequest

# Synthetic, deliberately fictional records for testing. Not real attractions.
MOCK_CATEGORIES = ['animals','nature','science','art','sports','museum','library','playground','garden','swimming','music','walking','history','craft']

def mock_candidates(request: RecommendationRequest) -> list[Candidate]:
    result=[]
    for i in range(1, 26):
        category=MOCK_CATEGORIES[(i-1)%len(MOCK_CATEGORIES)]
        indoors=category in {'science','art','museum','library','swimming','music','craft'}
        result.append(Candidate(
            place_id=f'mock-{i}', name=f'Demo {category.title()} Activity {i}',
            address=f'Synthetic test location, {request.city}, {request.province}',
            activity_type='indoor' if indoors else 'outdoor', categories=[category],
            price_category='free' if i%3==0 else 'any',
            source='mock'))
    return result

# Text searches bring a variety of family-friendly venues; not a live event calendar.
QUERIES = ['family museum', 'zoo animal sanctuary', 'playground park',
           'science centre kids', 'public library', 'family recreation centre',
           'botanical garden', 'indoor playground']

async def google_candidates(request: RecommendationRequest) -> list[Candidate]:
    key=os.getenv('GOOGLE_MAPS_API_KEY')
    if not key:
        raise HTTPException(status_code=503, detail='GOOGLE_MAPS_API_KEY is not configured')
    fields='places.id,places.displayName,places.formattedAddress,places.location,places.googleMapsUri,places.websiteUri,places.types'
    headers={'X-Goog-Api-Key':key,'X-Goog-FieldMask':fields,'Content-Type':'application/json'}
    results={}
    async with httpx.AsyncClient(timeout=15) as client:
        for term in QUERIES:
            payload={'textQuery':f'{term} in {request.city}, {request.province}, Canada',
                     'regionCode':'CA','maxResultCount':20}
            try:
                response=await client.post('https://places.googleapis.com/v1/places:searchText',headers=headers,json=payload)
                response.raise_for_status()
            except httpx.HTTPError as e:
                raise HTTPException(status_code=502,detail=f'Places API request failed: {type(e).__name__}') from e
            for p in response.json().get('places',[]):
                pid=p.get('id')
                if not pid or pid in results: continue
                location=p.get('location') or {}
                types=p.get('types') or []
                outdoor=any(t in types for t in ('park','playground','hiking_area','botanical_garden','zoo'))
                indoor=any(t in types for t in ('museum','library','aquarium','amusement_center','art_gallery'))
                a_type='outdoor' if outdoor else 'indoor' if indoor else 'any'
                results[pid]=Candidate(place_id=pid,name=(p.get('displayName') or {}).get('text','Unnamed place'),
                    address=p.get('formattedAddress',''), latitude=location.get('latitude'),
                    longitude=location.get('longitude'),google_maps_url=p.get('googleMapsUri'),
                    website_url=p.get('websiteUri'), google_place_id=pid, activity_type=a_type,
                    categories=types+[term],source='google_places')
    return list(results.values())

async def discover(request: RecommendationRequest) -> tuple[str,list[Candidate]]:
    mode=os.getenv('PLACES_PROVIDER','mock').lower()
    if mode == 'mock': return mode,mock_candidates(request)
    if mode == 'google': return mode,await google_candidates(request)
    if mode == 'postgres':
        from .database import database_candidates
        return mode, await database_candidates(request)
    raise HTTPException(status_code=500,detail='PLACES_PROVIDER must be mock, google or postgres')
