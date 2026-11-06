"""Safe Google Places matching tests. No API calls or database mutations."""
import asyncio

from app.models import Candidate
from app.place_matching import confirmed_match, match_missing_place_ids


def candidate(**kwargs):
    return Candidate(place_id="calgary:a",name="Example Swimming Centre",
                     address="100 Example Ave, Calgary, AB",
                     latitude=51.04,longitude=-114.08,
                     source="curated",**kwargs)


def result(name="Example Swimming Centre", lat=51.0401, lon=-114.0801, pid="ChIJverified"):
    return {"id":pid, "displayName":{"text":name},
            "location":{"latitude":lat,"longitude":lon}}


def test_exact_name_and_geo_required():
    c=candidate()
    assert confirmed_match(c,[result()])=="ChIJverified"
    assert confirmed_match(c,[result(name="Different Swimming Centre")]) is None
    assert confirmed_match(c,[result(lat=51.15)]) is None
    assert confirmed_match(c,[result(),result(pid="ChIJduplicate")]) is None
    c=c.model_copy(update={"latitude":None})
    assert confirmed_match(c,[result()]) is None


def test_no_matching_when_disabled(monkeypatch):
    monkeypatch.delenv("PLACE_MATCH_PROVIDER",raising=False)
    c=candidate()
    out,warning=asyncio.run(match_missing_place_ids([c]))
    assert out==[c] and warning is None


def test_matched_ids_can_feed_live_details(monkeypatch):
    monkeypatch.setenv("PLACE_MATCH_PROVIDER","google_places")
    monkeypatch.setenv("GOOGLE_MAPS_API_KEY","test")
    class Resp:
        def raise_for_status(self):pass
        def json(self):return {"places":[result()]}
    class Client:
        def __init__(self,**kwargs):pass
        async def __aenter__(self):return self
        async def __aexit__(self,*args):pass
        async def post(self,url,headers,json):
            assert json["maxResultCount"]==5
            assert "places.id" in headers["X-Goog-FieldMask"]
            return Resp()
    monkeypatch.setattr("app.place_matching.httpx.AsyncClient",Client)
    out,warning=asyncio.run(match_missing_place_ids([candidate()]))
    assert warning is None
    assert out[0].google_place_id=="ChIJverified"


def test_match_lookup_capped_at_five(monkeypatch):
    monkeypatch.setenv("PLACE_MATCH_PROVIDER","google_places")
    monkeypatch.setenv("GOOGLE_MAPS_API_KEY","test")
    calls=[]
    class Resp:
        def raise_for_status(self):pass
        def json(self):return {"places":[]}
    class Client:
        def __init__(self,**kwargs):pass
        async def __aenter__(self):return self
        async def __aexit__(self,*args):pass
        async def post(self,url,headers,json):
            calls.append(json["textQuery"])
            return Resp()
    monkeypatch.setattr("app.place_matching.httpx.AsyncClient",Client)
    many=[candidate().model_copy(update={"place_id":str(i)}) for i in range(12)]
    out,warning=asyncio.run(match_missing_place_ids(many))
    assert len(calls)==5
    assert all(c.google_place_id is None for c in out)
    assert warning is not None


def test_missing_key_does_not_block_search(monkeypatch):
    monkeypatch.setenv("PLACE_MATCH_PROVIDER","google_places")
    monkeypatch.delenv("GOOGLE_MAPS_API_KEY",raising=False)
    out,warning=asyncio.run(match_missing_place_ids([candidate()]))
    assert out[0].google_place_id is None
    assert "missing" in warning.lower()
