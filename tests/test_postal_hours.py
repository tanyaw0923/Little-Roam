import asyncio
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.models import Candidate, RecommendationRequest
from app.postal import normalize_postal_code, resolve_postal_origin
from app.geo import request_origin
from app.driving import shortlist
from app.hours import verify_hours, _fetch_hours, MAX_HOURS_REQUESTS


def request(**kwargs):
    return RecommendationRequest(city="Calgary",  children_ages=[2], **kwargs)


def test_postal_normalizes_case_spacing():
    assert normalize_postal_code("t2p1j9") == "T2P 1J9"
    assert normalize_postal_code("T2P 1J9") == "T2P 1J9"


@pytest.mark.parametrize("postal",["abc123","123456","K1A0B1","T2P-1J9"])
def test_bad_postal_rejected_for_alberta(postal):
    with pytest.raises(ValidationError):
        request(search_scope="regional", postal_code=postal)


def test_postal_requires_regional_scope():
    with pytest.raises(ValidationError):
        request(postal_code="T2P 1J9")


def test_postal_origin_overrides_city_centre():
    r=request(search_scope="regional",postal_code="T2P 1J9")
    r._resolved_origin=(51.14,-114.18)
    assert request_origin(r)==(51.14,-114.18)
    c=Candidate(place_id="test",name="test",address="AB",latitude=51.14,
        longitude=-114.18,source="curated")
    assert shortlist([c],r)==[c]


def test_postal_geocoding_exact_match(monkeypatch):
    monkeypatch.setenv("GOOGLE_GEOCODING_API_KEY","test-only")
    class Response:
        def raise_for_status(self): pass
        def json(self):
            return {"status":"OK","results":[{
                "address_components":[
                    {"long_name":"T2P 1J9","types":["postal_code"]},
                    {"short_name":"AB","types":["administrative_area_level_1"]},
                    {"short_name":"CA","types":["country"]}],
                "geometry":{"location":{"lat":51.05,"lng":-114.07}}}]}
    class Client:
        def __init__(self,**kw): pass
        async def __aenter__(self): return self
        async def __aexit__(self,*a): pass
        async def get(self,url,params):
            assert params["components"]=="postal_code:T2P1J9|country:CA"
            return Response()
    monkeypatch.setattr("app.postal.httpx.AsyncClient",Client)
    assert asyncio.run(resolve_postal_origin("T2P1J9","AB"))==(51.05,-114.07)


def test_postal_mismatched_result_refused(monkeypatch):
    monkeypatch.setenv("GOOGLE_GEOCODING_API_KEY","test-only")
    class Response:
        def raise_for_status(self): pass
        def json(self): return {"status":"OK","results":[{"partial_match":True}]}
    class Client:
        def __init__(self,**kw):pass
        async def __aenter__(self):return self
        async def __aexit__(self,*a):pass
        async def get(self,url,params):return Response()
    monkeypatch.setattr("app.postal.httpx.AsyncClient",Client)
    with pytest.raises(HTTPException) as e:
        asyncio.run(resolve_postal_origin("T2P1J9","AB"))
    assert e.value.status_code==422


def test_hours_off(monkeypatch):
    monkeypatch.delenv("HOURS_PROVIDER",raising=False)
    candidates=[Candidate(place_id="x",name="x",address="AB",source="curated")]
    assert asyncio.run(verify_hours(candidates))==(candidates,None)


def test_hours_no_id_does_not_spend(monkeypatch):
    monkeypatch.setenv("HOURS_PROVIDER","google_places")
    monkeypatch.setenv("GOOGLE_MAPS_API_KEY","fake")
    c=Candidate(place_id="x",name="x",address="AB",source="curated")
    out,w=asyncio.run(verify_hours([c]))
    assert out[0].hours_status=="unknown"
    assert "No verified Google Place ID" in w


def test_hours_verification_for_explicit_id(monkeypatch):
    monkeypatch.setenv("HOURS_PROVIDER","google_places")
    monkeypatch.setenv("GOOGLE_MAPS_API_KEY","fake")
    class Response:
        def raise_for_status(self):pass
        def json(self):return {"id":"ChIJtest","businessStatus":"OPERATIONAL",
                  "currentOpeningHours":{"openNow":True}}
    class Client:
        def __init__(self,**kw):pass
        async def __aenter__(self):return self
        async def __aexit__(self,*a):pass
        async def get(self,url,headers):
            assert url.endswith("/ChIJtest")
            return Response()
    monkeypatch.setattr("app.hours.httpx.AsyncClient",Client)
    c=Candidate(place_id="x",name="x",address="AB",google_place_id="ChIJtest",source="curated")
    out,w=asyncio.run(verify_hours([c]))
    assert w is None
    assert out[0].hours_status=="open_now"
    assert out[0].hours_checked_at
    assert out[0].hours_source_url


def test_hours_cap_is_ten(monkeypatch):
    assert MAX_HOURS_REQUESTS==10
    monkeypatch.setenv("HOURS_PROVIDER","google_places")
    monkeypatch.setenv("GOOGLE_MAPS_API_KEY","fake")
    n=[]
    async def fake(client, place_id, key):
        n.append(place_id)
        return None
    monkeypatch.setattr("app.hours._fetch_hours",fake)
    many=[Candidate(place_id=str(i),name=str(i),address="AB",google_place_id=f"ChIJ{i}",source="curated") for i in range(25)]
    out,w=asyncio.run(verify_hours(many))
    assert len(n)==10


def test_driving_matrix_starts_at_postal_origin(monkeypatch):
    from app.driving import routes_for_candidates
    monkeypatch.setenv("GOOGLE_ROUTES_API_KEY","fake")
    class Response:
        def raise_for_status(self): pass
        def json(self):
            return [{"originIndex":0,"destinationIndex":0,"condition":"ROUTE_EXISTS",
                     "duration":"600s","distanceMeters":8000}]
    class Client:
        def __init__(self,**kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self,*args): pass
        async def post(self,url,headers,json):
            origin=json["origins"][0]["waypoint"]["location"]["latLng"]
            assert origin=={"latitude":51.14,"longitude":-114.18}
            return Response()
    monkeypatch.setattr("app.driving.httpx.AsyncClient",Client)
    request_with_postal=request(search_scope="regional",postal_code="T2P 1J9")
    request_with_postal._resolved_origin=(51.14,-114.18)
    c=Candidate(place_id="x",name="x",address="AB",
                latitude=51.2,longitude=-114.2,source="curated")
    results=asyncio.run(routes_for_candidates([c],request_with_postal))
    assert len(results)==1
    assert results[0].drive_minutes==10


def test_weekly_hours_fallback_from_google_places(monkeypatch):
    monkeypatch.setenv("HOURS_PROVIDER", "google_places")
    monkeypatch.setenv("GOOGLE_MAPS_API_KEY", "fake")
    class Response:
        def raise_for_status(self): pass
        def json(self):
            return {"id": "ChIJverified",
                    "regularOpeningHours": {"weekdayDescriptions": [
                        "Monday: 9 AM–5 PM", "Tuesday: 9 AM–5 PM"]}}
    class Client:
        def __init__(self, **kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        async def get(self, url, headers): return Response()
    monkeypatch.setattr("app.hours.httpx.AsyncClient", Client)
    c=Candidate(place_id="x",name="x",address="Calgary",source="curated",
                google_place_id="ChIJverified")
    result, warning=asyncio.run(verify_hours([c]))
    assert result[0].hours_status == "unknown"
    assert result[0].published_weekly_hours == [
        "Monday: 9 AM–5 PM", "Tuesday: 9 AM–5 PM"]
    assert result[0].hours_checked_at is not None
    assert warning is not None
