import asyncio
import os
from unittest.mock import Mock
import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.geo import origin_for, straight_line_km, bounding_box
from app.driving import shortlist, routes_for_candidates, _duration_minutes, filter_by_driving_time
from app.models import Candidate, RecommendationRequest
from app.recommend import recommend


def request(**kwargs):
    return RecommendationRequest(city='Calgary',  children_ages=[2, 6], **kwargs)


def candidate(ident, lat, lon, categories=None):
    return Candidate(place_id=ident, name=ident, address='Alberta',
                     latitude=lat, longitude=lon, categories=categories or ['nature'],
                     source='curated')


def test_regional_origin_and_drive_options():
    r = request(search_scope='regional', max_drive_minutes=120)
    assert r.max_drive_minutes == 120
    assert origin_for('AB','Calgary') is not None


def test_regional_rejects_unsupported_origin():
    with pytest.raises(ValidationError, match='Regional search currently supports'):
        RecommendationRequest(city='Toronto',  children_ages=[4], search_scope='regional')


def test_city_scope_remains_default():
    assert request().search_scope == 'city'


def test_only_supported_driving_minutes():
    with pytest.raises(ValidationError):
        request(search_scope='regional', max_drive_minutes=45)


def test_haversine_approximation_for_db_prefilter():
    calgary = origin_for('AB', 'Calgary')
    banff = origin_for('AB', 'Banff')
    km = straight_line_km(*calgary, *banff)
    assert 95 < km < 120
    assert straight_line_km(*calgary, *calgary) < .001


def test_bounding_box_contains_banff():
    lat, lon = origin_for('AB', 'Calgary')
    a, b, c, d = bounding_box(lat, lon, 250)
    banff_lat, banff_lon = origin_for('AB', 'Banff')
    assert a < banff_lat < b and c < banff_lon < d


def test_preselection_discards_null_coordinates():
    r = request(search_scope='regional', max_drive_minutes=120)
    a = candidate('good', 51.04, -114.08)
    b = Candidate(place_id='missing', name='missing', address='Calgary', source='curated')
    assert [x.place_id for x in shortlist([a,b], r)] == ['good']


def test_shortlist_caps_paid_matrix_elements():
    r = request(search_scope='regional')
    many = [candidate(str(i), 51.04, -114.08) for i in range(45)]
    assert len(shortlist(many,r)) == 10


def test_direct_route_call_is_capped_to_ten(monkeypatch):
    monkeypatch.setenv('GOOGLE_ROUTES_API_KEY', 'fake-testing-key')
    class FakeResponse:
        def raise_for_status(self): pass
        def json(self): return []
    class FakeClient:
        def __init__(self,*args,**kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self,*args): pass
        async def post(self,url,headers,json):
            assert len(json['destinations']) == 10
            return FakeResponse()
    monkeypatch.setattr('app.driving.httpx.AsyncClient', FakeClient)
    result=asyncio.run(routes_for_candidates(
        [candidate(str(i),51.04,-114.08) for i in range(15)],
        request(search_scope='regional')))
    assert result == []


def test_duration_parse():
    assert _duration_minutes('1800s') == 30
    assert _duration_minutes('61.5s') == 1.0
    assert _duration_minutes('not-a-duration') is None


def test_missing_api_key_fails_closed(monkeypatch):
    monkeypatch.delenv('GOOGLE_ROUTES_API_KEY', raising=False)
    r = request(search_scope='regional')
    with pytest.raises(HTTPException) as exc:
        asyncio.run(routes_for_candidates([candidate('x',51.04,-114.07)],r))
    assert exc.value.status_code == 503


def test_google_route_response_filters_long_and_missing(monkeypatch):
    monkeypatch.setenv('GOOGLE_ROUTES_API_KEY', 'fake-testing-key')
    class FakeResponse:
        def raise_for_status(self): pass
        def json(self):
            return [
                {'originIndex':0,'destinationIndex':0,'condition':'ROUTE_EXISTS',
                 'status':{},'duration':'1700s','distanceMeters':21000},
                {'originIndex':0,'destinationIndex':1,'condition':'ROUTE_EXISTS',
                 'duration':'4700s','distanceMeters':91000},
                {'originIndex':0,'destinationIndex':2,'condition':'ROUTE_NOT_FOUND'},
            ]
    class FakeClient:
        def __init__(self,*args,**kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self,*args): pass
        async def post(self,url,headers,json):
            assert json['routingPreference']=='TRAFFIC_UNAWARE'
            assert len(json['destinations'])==3
            return FakeResponse()
    monkeypatch.setattr('app.driving.httpx.AsyncClient',FakeClient)
    r=request(search_scope='regional',max_drive_minutes=30)
    locations=[candidate('a',51.04,-114.07),candidate('b',51.09,-115.35),candidate('c',51.17,-115.57)]
    result=asyncio.run(routes_for_candidates(locations,r))
    assert len(result)==1
    assert result[0].drive_minutes==28.3
    assert result[0].distance_km==21


def test_no_route_estimate_for_mock_data():
    r = request()
    c = Candidate(place_id='a', name='A', address='x', source='mock')
    assert asyncio.run(filter_by_driving_time([c],r))==[c]


def test_driving_fields_in_recommendation(monkeypatch):
    monkeypatch.delenv('OPENAI_API_KEY',raising=False)
    r=request(search_scope='regional',max_drive_minutes=60)
    c=candidate('a',51.04,-114.07).model_copy(update={'drive_minutes':28.3,'distance_km':21})
    result=asyncio.run(recommend([c],r))
    assert result[0].drive_minutes==28.3
    assert result[0].distance_km==21
