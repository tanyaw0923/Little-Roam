import json
import os
from .models import Candidate, Recommendation, RecommendationRequest


def score_candidate(c:Candidate, r:RecommendationRequest)->float:
    # Soft matching only for unknown age/type. Hard exclusions belong in eligible().
    interest_words=set(' '.join(r.interests).lower().replace('_',' ').split())
    candidate_words=set(' '.join([c.name,*c.categories]).lower().replace('_',' ').split())
    overlap=len(interest_words & candidate_words)
    return round(1.0 + 2.0*overlap + (0.5 if c.price_category=='free' else 0) + c.weather_score_adjustment,2)

def eligible(c:Candidate,r:RecommendationRequest)->bool:
    if r.activity_type!='any' and c.activity_type not in (r.activity_type,'any'):
        return False
    if r.budget=='free' and c.price_category!='free':
        return False
    if any(c.min_age is not None and age<c.min_age or c.max_age is not None and age>c.max_age for age in r.children_ages):
        return False
    return True

async def explain(selected:list[Candidate],r:RecommendationRequest)->dict[str,tuple[str,str]]:
    # LLM only writes copy. It cannot change IDs or introduce new venues/facts.
    if not os.getenv('OPENAI_API_KEY') or not selected:
        return {}
    from openai import AsyncOpenAI
    from pydantic import BaseModel
    class Entry(BaseModel):
        place_id:str
        reason:str
        parent_tip:str
    class Batch(BaseModel):
        items:list[Entry]
    client=AsyncOpenAI()
    data=[{'place_id':c.place_id,'name':c.name,'categories':c.categories,'type':c.activity_type} for c in selected]
    try:
        result=await client.beta.chat.completions.parse(
            model=os.getenv('OPENAI_MODEL','gpt-4.1-mini'),
            messages=[{'role':'system','content':'Write concise helpful family recommendation copy. Use ONLY given place names/types/categories; never claim hours, safety, admission prices, weather, accessibility, age suitability or amenities without provided evidence. Avoid certainty. Return one entry per place ID.'},
                      {'role':'user','content':json.dumps({'family':r.model_dump(mode='json', exclude={'postal_code'}),'places':data})}],
            response_format=Batch)
        parsed=result.choices[0].message.parsed
        allowed={c.place_id for c in selected}
        return {x.place_id:(x.reason[:300],x.parent_tip[:300]) for x in (parsed.items if parsed else []) if x.place_id in allowed}
    except Exception:
        # Deterministic behavior remains available if LLM is down.
        return {}

async def recommend(candidates:list[Candidate],r:RecommendationRequest)->list[Recommendation]:
    eligible_candidates=[c for c in candidates if eligible(c,r)]
    ordered=sorted(eligible_candidates,key=lambda c:(-score_candidate(c,r),c.distance_km if c.distance_km is not None else float('inf'),c.place_id))[:r.max_results]
    narratives=await explain(ordered,r)
    out=[]
    for c in ordered:
        reason,tip=narratives.get(c.place_id,(
            'Potential match based on your activity preferences; check the official listing for age suitability.',
            'Confirm operating hours, admission fees, and child facilities before visiting.'))
        out.append(Recommendation(place_id=c.place_id,name=c.name,address=c.address,
            google_maps_url=c.google_maps_url,website_url=c.website_url,website_source=c.website_source,
            official_source_url=c.official_source_url,
            activity_type=c.activity_type,distance_km=c.distance_km,drive_minutes=c.drive_minutes,
            weather_summary=c.weather_summary,weather_source=c.weather_source,
            hours_status=c.hours_status,hours_source_url=c.hours_source_url,
            hours_checked_at=c.hours_checked_at,published_weekly_hours=c.published_weekly_hours,
            hours_source=c.hours_source,hours_status_source=c.hours_status_source,
            hours_date_notice=c.hours_date_notice,
            hours_for_visit_date='unknown',
            hours_verified=(c.hours_status != 'unknown'),
            reason=reason,parent_tip=tip,
            source=c.source,score=score_candidate(c,r)))
    return out
