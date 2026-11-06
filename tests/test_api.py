import asyncio
import os
from fastapi.testclient import TestClient
from app.main import app
from app.models import Candidate,RecommendationRequest
from app.recommend import eligible,recommend

client=TestClient(app)

def test_health():
    assert client.get('/health').json()=={'status':'ok'}

def test_mock_returns_ten():
    os.environ['PLACES_PROVIDER']='mock'
    response=client.post('/api/v1/recommendations',json={'city':'Calgary','children_ages':[2,6], 'interests':['nature']})
    assert response.status_code==200
    data=response.json()
    assert data['count']==10
    assert data['mode']=='mock'
    assert all(x['source']=='mock' for x in data['recommendations'])

def test_invalid_age():
    r=client.post('/api/v1/recommendations',json={'city':'Calgary','children_ages':[18]})
    assert r.status_code==422

def test_free_budget_excludes_unknown():
    r=RecommendationRequest(city='Calgary',children_ages=[4],budget='free')
    assert not eligible(Candidate(place_id='a',name='A',address='x',source='mock'),r)

def test_model_never_fabricates_ten():
    r=RecommendationRequest(city='Calgary',children_ages=[4])
    c=Candidate(place_id='a',name='A',address='x',source='mock')
    assert len(asyncio.run(recommend([c],r)))==1


def test_request_schema_does_not_require_or_show_province():
    schema=client.get('/openapi.json').json()
    request_schema=schema['components']['schemas']['RecommendationRequest']
    assert 'province' not in request_schema['properties']
    assert 'province' not in request_schema.get('required',[])
    response=client.post('/api/v1/recommendations',json={
        'city':'Calgary','children_ages':[4]})
    assert response.status_code==200
    assert response.json()['province']=='AB'


def test_internal_province_alberta():
    r=RecommendationRequest(city='Banff',children_ages=[5])
    assert r.province=='AB'
    assert 'province' not in r.model_dump()


def test_optional_visit_date_in_openapi_and_response(monkeypatch):
    from datetime import datetime, timedelta
    from zoneinfo import ZoneInfo
    monkeypatch.setenv('PLACES_PROVIDER','mock')
    monkeypatch.setenv('WEATHER_PROVIDER','off')
    tomorrow=(datetime.now(ZoneInfo('America/Edmonton')).date()+timedelta(days=1)).isoformat()
    schema=client.get('/openapi.json').json()
    assert 'visit_date' in schema['components']['schemas']['RecommendationRequest']['properties']
    r=client.post('/api/v1/recommendations',json={
        'city':'Calgary','children_ages':[4],'visit_date':tomorrow})
    assert r.status_code==200
    assert r.json()['visit_date']==tomorrow
    assert all(x['hours_for_visit_date']=='unknown' for x in r.json()['recommendations'])
