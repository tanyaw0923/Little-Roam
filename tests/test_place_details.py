"""Combined website and hours live-enrichment tests, without billable API calls."""
import asyncio
from app.models import Candidate
from app.place_details import enrich_place_details, parse_details


def candidate(**kwargs):
    return Candidate(place_id="curated:test", name="Example Centre",
                     address="Calgary, AB", source="curated", **kwargs)


def test_combined_details_returns_url_and_hours_in_one_call(monkeypatch):
    monkeypatch.setenv("HOURS_PROVIDER", "google_places")
    monkeypatch.setenv("WEBSITE_PROVIDER", "google_places")
    monkeypatch.setenv("GOOGLE_MAPS_API_KEY", "fake")
    calls=[]
    class Response:
        def raise_for_status(self):pass
        def json(self):
            return {"id":"ChIJverified","websiteUri":"https://venue.example/",
                    "currentOpeningHours":{"openNow":True,
                       "weekdayDescriptions":["Monday: 9 AM–5 PM"]}}
    class Client:
        def __init__(self, **kwargs):pass
        async def __aenter__(self):return self
        async def __aexit__(self,*args):pass
        async def get(self,url,headers):
            calls.append(headers["X-Goog-FieldMask"])
            assert url.endswith("ChIJverified")
            return Response()
    monkeypatch.setattr("app.place_details.httpx.AsyncClient",Client)
    data,warning=asyncio.run(enrich_place_details([candidate(
        google_place_id="ChIJverified")]))
    assert len(calls)==1
    assert "websiteUri" in calls[0]
    assert "currentOpeningHours.openNow" in calls[0]
    assert warning is None
    assert data[0].website_url=="https://venue.example/"
    assert data[0].website_source=="google_places"
    assert data[0].hours_status=="open_now"
    assert data[0].published_weekly_hours==["Monday: 9 AM–5 PM"]
    assert "hours_for_visit_date" not in data[0].model_dump()


def test_existing_curated_url_never_overwritten(monkeypatch):
    monkeypatch.setenv("HOURS_PROVIDER","google_places")
    monkeypatch.setenv("WEBSITE_PROVIDER","google_places")
    monkeypatch.setenv("GOOGLE_MAPS_API_KEY","fake")
    class Response:
        def raise_for_status(self):pass
        def json(self):return {"id":"ChIJverified","currentOpeningHours":{"openNow":False}}
    class Client:
        def __init__(self,**kwargs):pass
        async def __aenter__(self):return self
        async def __aexit__(self,*args):pass
        async def get(self,url,headers):
            assert "websiteUri" not in headers["X-Goog-FieldMask"]
            return Response()
    monkeypatch.setattr("app.place_details.httpx.AsyncClient", Client)
    data,warning=asyncio.run(enrich_place_details([candidate(
        google_place_id="ChIJverified", website_url="https://official.example/")]))
    assert data[0].website_url=="https://official.example/"
    assert data[0].website_source=="curated"
    assert data[0].hours_status=="closed_now"


def test_no_id_does_not_spend(monkeypatch):
    monkeypatch.setenv("HOURS_PROVIDER","google_places")
    monkeypatch.setenv("WEBSITE_PROVIDER","google_places")
    monkeypatch.setenv("GOOGLE_MAPS_API_KEY","fake")
    c=candidate()
    out,warning=asyncio.run(enrich_place_details([c]))
    assert out[0].website_url is None
    assert out[0].hours_status=="unknown"
    assert "google.com/maps" in out[0].google_maps_url
    assert warning is not None


def test_no_assumed_hours_for_future_date():
    info=parse_details({"id":"ChIJtest",
                        "regularOpeningHours":{"weekdayDescriptions":["Saturday: Open 24 hours"]}},
                       "ChIJtest",False,True)
    assert info["hours_status"]=="unknown"
    assert info["published_weekly_hours"]==["Saturday: Open 24 hours"]


def test_place_id_mismatch_rejected():
    assert parse_details({"id":"ChIJwrong","websiteUri":"https://bad.example"},
                         "ChIJexpected",True,True)=={}


def test_approved_official_schedule_skips_billable_google_hours(monkeypatch):
    monkeypatch.setenv("HOURS_PROVIDER", "google_places")
    monkeypatch.setenv("WEBSITE_PROVIDER", "off")
    monkeypatch.setenv("GOOGLE_MAPS_API_KEY", "fake")
    class ForbiddenClient:
        def __init__(self, **kwargs):
            raise AssertionError("Official schedule should not call Google")
    monkeypatch.setattr("app.place_details.httpx.AsyncClient", ForbiddenClient)
    from datetime import date
    c=candidate(google_place_id="ChIJverified").model_copy(update={
        "hours_source": "official_website",
        "published_weekly_hours": ["Friday: 09:00 - 17:00"],
    })
    result,warning=asyncio.run(enrich_place_details([c], date(2026,11,6)))
    assert result[0].published_weekly_hours == ["Friday: 09:00 - 17:00"]
    assert result[0].hours_source == "official_website"
    assert warning is None


def test_google_fallback_if_official_schedule_lacks_selected_weekday(monkeypatch):
    monkeypatch.setenv("HOURS_PROVIDER", "google_places")
    monkeypatch.setenv("WEBSITE_PROVIDER", "off")
    monkeypatch.setenv("GOOGLE_MAPS_API_KEY", "fake")
    calls=[]
    class Response:
        def raise_for_status(self): pass
        def json(self):
            return {"id": "ChIJverified", "regularOpeningHours": {
                "weekdayDescriptions": ["Friday: 10 AM - 6 PM"]}}
    class Client:
        def __init__(self, **kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        async def get(self, url, headers):
            calls.append(url)
            return Response()
    monkeypatch.setattr("app.place_details.httpx.AsyncClient", Client)
    from datetime import date
    c=candidate(google_place_id="ChIJverified").model_copy(update={
        "hours_source": "official_website",
        "published_weekly_hours": ["Monday: 09:00 - 17:00"],
    })
    result,warning=asyncio.run(enrich_place_details([c], date(2026,11,6)))
    assert len(calls) == 1
    assert result[0].hours_source == "google_places"
    assert result[0].published_weekly_hours == ["Friday: 10 AM - 6 PM"]
