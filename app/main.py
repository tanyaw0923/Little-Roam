from dotenv import load_dotenv
load_dotenv()
from fastapi import FastAPI
from .models import RecommendationRequest, RecommendationResponse
from .discovery import discover
from .recommend import recommend
from .driving import filter_by_driving_time

app=FastAPI(title='Little Roam Recommendation API',version='0.1.0')

@app.get('/health')
def health():
    return {'status':'ok'}

@app.post('/api/v1/recommendations',response_model=RecommendationResponse)
async def recommendations(payload:RecommendationRequest):
    mode,candidates=await discover(payload)
    candidates=await filter_by_driving_time(candidates,payload)
    results=await recommend(candidates,payload)
    warnings=['Demo data only; no listed attractions are real.' if mode=='mock' else
              'Activity details require independent verification from permitted sources; confirm hours, prices and age suitability.',
              'Unknown price is excluded from free-only requests; age and facility information may be incomplete.',
              'Weather and verified opening hours are not integrated in v0.1.']
    if payload.search_scope == 'regional':
        warnings.append('Driving durations are Google Routes traffic-unaware estimates from an approximate city centre, not from a family home or live traffic. At most 10 candidate routes are evaluated; missing-coordinate and unavailable routes are excluded.')
    if len(results)<payload.max_results:
        warnings.append('Fewer eligible places found than requested; no fabricated recommendations added.')
    return RecommendationResponse(city=payload.city,province=payload.province,mode=mode,
                                  count=len(results),recommendations=results,warnings=warnings)
