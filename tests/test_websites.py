"""Live website enrichment tests; no live Places API calls."""
import asyncio

from app.models import Candidate
from app.websites import enrich_websites, valid_website_url, maps_search_url


def activity(**kwargs):
    return Candidate(place_id="curated:a",name="Example Recreation Centre",
                     address="123 Main Street, Calgary, AB",source="curated",**kwargs)


def test_off_keeps_existing_website_and_adds_google_maps_link(monkeypatch):
    monkeypatch.delenv("WEBSITE_PROVIDER",raising=False)
    c=activity(website_url="https://town.example/recreation")
    result,warning=asyncio.run(enrich_websites([c]))
    assert warning is None
    assert result[0].website_url=="https://town.example/recreation"
    assert result[0].website_source=="curated"
    assert "google.com/maps/search" in result[0].google_maps_url


def test_unmapped_curated_place_avoids_guessing_website(monkeypatch):
    monkeypatch.setenv("WEBSITE_PROVIDER","google_places")
    monkeypatch.setenv("GOOGLE_MAPS_API_KEY","fake")
    result,warning=asyncio.run(enrich_websites([activity()]))
    assert result[0].website_url is None
    assert result[0].website_source=="unknown"
    assert "Example%20Recreation%20Centre" in result[0].google_maps_url


def test_google_place_id_fills_missing_website(monkeypatch):
    monkeypatch.setenv("WEBSITE_PROVIDER","google_places")
    monkeypatch.setenv("GOOGLE_MAPS_API_KEY","fake")
    class Response:
        def raise_for_status(self): pass
        def json(self): return {"id":"ChIJverified","websiteUri":"https://venue.example/visit"}
    class Client:
        def __init__(self,**kw): pass
        async def __aenter__(self):return self
        async def __aexit__(self,*a): pass
        async def get(self,url,headers):
            assert url.endswith("/ChIJverified")
            assert headers["X-Goog-FieldMask"]=="id,websiteUri"
            return Response()
    monkeypatch.setattr("app.websites.httpx.AsyncClient",Client)
    result,warning=asyncio.run(enrich_websites([activity(google_place_id="ChIJverified")]))
    assert warning is None
    assert result[0].website_url=="https://venue.example/visit"
    assert result[0].website_source=="google_places"
    assert result[0].google_maps_url.endswith("query_place_id=ChIJverified")


def test_dont_replace_curated_website_or_call_places(monkeypatch):
    monkeypatch.setenv("WEBSITE_PROVIDER","google_places")
    monkeypatch.setenv("GOOGLE_MAPS_API_KEY","fake")
    class ForbiddenClient:
        def __init__(self,**kw):raise AssertionError("Unexpected paid API request")
    monkeypatch.setattr("app.websites.httpx.AsyncClient",ForbiddenClient)
    result,warning=asyncio.run(enrich_websites([activity(
        website_url="https://venue.example",google_place_id="ChIJverified")]))
    assert warning is None
    assert result[0].website_url=="https://venue.example"
    assert result[0].website_source=="curated"


def test_invalid_provider_url_is_not_shown(monkeypatch):
    assert valid_website_url("javascript:alert(1)") is None
    assert valid_website_url("http://localhost/admin") is None
    assert valid_website_url("https://valid.example/path")=="https://valid.example/path"


def test_missing_api_key_does_not_fail_request(monkeypatch):
    monkeypatch.setenv("WEBSITE_PROVIDER","google_places")
    monkeypatch.delenv("GOOGLE_MAPS_API_KEY",raising=False)
    result,warning=asyncio.run(enrich_websites([activity(google_place_id="ChIJverified")]))
    assert result[0].website_url is None
    assert "not configured" in warning


def test_website_lookup_capped_to_ten(monkeypatch):
    monkeypatch.setenv("WEBSITE_PROVIDER","google_places")
    monkeypatch.setenv("GOOGLE_MAPS_API_KEY","fake")
    calls=[]
    async def fake_lookup(client, place_id, key):
        calls.append(place_id)
        return None
    monkeypatch.setattr("app.websites._website_from_place_id",fake_lookup)
    candidates=[Candidate(place_id=str(i),name=str(i),address="Calgary, AB",
                 source="curated",google_place_id=f"ChIJ{i}") for i in range(15)]
    result,warning=asyncio.run(enrich_websites(candidates))
    assert len(calls)==10
    assert len(result)==15
    assert warning is not None
