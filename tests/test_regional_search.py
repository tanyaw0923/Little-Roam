import asyncio
import pytest
from pydantic import ValidationError

from app.geo import origin_for, straight_line_km, bounding_box
from app.models import Candidate, RecommendationRequest
from app.recommend import recommend

def request(**kwargs):
    return RecommendationRequest(city='Calgary', province='AB', children_ages=[2, 6], **kwargs)

def test_regional_origin_and_radius_up_to_200():
    r = request(search_scope='regional', radius_km=150)
    assert r.search_scope == 'regional'
    assert origin_for('AB','Calgary') is not None

def test_regional_rejects_unsupported_origin():
    with pytest.raises(ValidationError, match='Regional search currently supports'):
        RecommendationRequest(city='Toronto',province='ON',children_ages=[4],search_scope='regional')

def test_city_scope_remains_default():
    assert request().search_scope == 'city'

def test_radius_above_200_rejected():
    with pytest.raises(ValidationError):
        request(search_scope='regional',radius_km=201)

def test_haversine_calculation():
    calgary = origin_for('AB', 'Calgary')
    banff = origin_for('AB', 'Banff')
    km = straight_line_km(*calgary,*banff)
    assert 95 < km < 120
    assert straight_line_km(*calgary,*calgary) < 0.001

def test_bounding_box_contains_banff_for_150km():
    lat,lon = origin_for('AB','Calgary')
    min_lat,max_lat,min_lon,max_lon = bounding_box(lat,lon,150)
    b_lat,b_lon=origin_for('AB','Banff')
    assert min_lat < b_lat < max_lat
    assert min_lon < b_lon < max_lon

def test_distance_is_preserved_in_api_recommendations(monkeypatch):
    monkeypatch.delenv('OPENAI_API_KEY',raising=False)
    r = request(search_scope='regional',radius_km=150)
    c = Candidate(place_id='banff_1',name='Test Banff Park',address='Banff, AB',
        latitude=51.17366,longitude=-115.57284,distance_km=105.1,source='curated')
    result=asyncio.run(recommend([c],r))
    assert result[0].distance_km == 105.1
