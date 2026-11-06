from datetime import datetime
from zoneinfo import ZoneInfo
from dotenv import load_dotenv
load_dotenv()
from fastapi import FastAPI
from .models import RecommendationRequest, RecommendationResponse
from .discovery import discover
from .recommend import recommend
from .driving import filter_by_driving_time
from .weather import add_weather
from .postal import resolve_postal_origin
from .hours import verify_hours
from .websites import enrich_websites
from .place_matching import match_missing_place_ids
from .recommend import eligible, score_candidate

app=FastAPI(title='Little Roam Recommendation API',version='0.1.0')

@app.get('/health')
def health():
    return {'status':'ok'}

@app.post('/api/v1/recommendations',response_model=RecommendationResponse)
async def recommendations(payload:RecommendationRequest):
    if payload.search_scope == 'regional' and payload.postal_code:
        lat, lon = await resolve_postal_origin(payload.postal_code, payload.province)
        payload._resolved_origin = (lat, lon)
    mode,candidates=await discover(payload)
    candidates=await filter_by_driving_time(candidates,payload)
    candidates,weather_warning=await add_weather(candidates,payload)
    # Confirm hours only for top-ranked eligible activities (<=10 billable lookups).
    eligible_candidates = [c for c in candidates if eligible(c, payload)]
    selected = sorted(eligible_candidates, key=lambda c: (-score_candidate(c,payload), c.distance_km if c.distance_km is not None else float('inf'), c.place_id))[:payload.max_results]
    selected,matching_warning=await match_missing_place_ids(selected)
    selected,hours_warning=await verify_hours(selected)
    selected,website_warning=await enrich_websites(selected)
    results=await recommend(selected,payload)
    warnings=['Demo data only; no listed attractions are real.' if mode=='mock' else
              'Activity details require independent verification from permitted sources; confirm hours, prices and age suitability.',
              'Unknown price is excluded from free-only requests; age and facility information may be incomplete.',
              'Weather is a daily forecast for the selected outing date, not live conditions or a safety assessment. Venue open-now and weekly hours do not confirm opening on the planned visit date; check venue and specific activity schedules.']
    if payload.search_scope == 'regional':
        warnings.append('Driving durations are Google Routes traffic-unaware estimates from an approximate postal-code area (when provided), otherwise a city centre; not from a home address or live traffic. At most 10 candidate routes are evaluated; missing-coordinate and unavailable routes are excluded.')
    if matching_warning:
        warnings.append(matching_warning)
    if hours_warning:
        warnings.append(hours_warning)
    if website_warning:
        warnings.append(website_warning)
    if weather_warning:
        warnings.append(weather_warning)
    if len(results)<payload.max_results:
        warnings.append('Fewer eligible places found than requested; no fabricated recommendations added.')
    return RecommendationResponse(visit_date=payload.visit_date or datetime.now(ZoneInfo('America/Edmonton')).date(),
                                  city=payload.city,province=payload.province,mode=mode,
                                  count=len(results),recommendations=results,warnings=warnings)
