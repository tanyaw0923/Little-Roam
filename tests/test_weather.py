import asyncio
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
from pydantic import ValidationError
import pytest
import httpx

from app.models import Candidate, RecommendationRequest
from app.weather import _CACHE, nearest_town, interpret_daily, add_weather, get_town_forecast
from app.recommend import recommend, score_candidate


def request():
    return RecommendationRequest(city="Calgary", children_ages=[2],
                                 search_scope="regional", max_drive_minutes=120)


def activity(name, kind, latitude=51.17, longitude=-115.57):
    return Candidate(place_id=name, name=name, address="AB",
                     latitude=latitude, longitude=longitude,
                     activity_type=kind, source="curated")


def test_nearest_weather_town_is_destination_not_origin():
    assert nearest_town(51.17, -115.57) == "banff"
    assert nearest_town(51.04, -114.07) == "calgary"


def test_adverse_weather_favors_indoor(monkeypatch):
    monkeypatch.setenv("WEATHER_PROVIDER", "open_meteo")
    _CACHE.clear()
    async def fake_forecast(town, outing_date=None):
        return interpret_daily({
            "time": ["2026-11-06"], "temperature_2m_max": [-18],
            "precipitation_probability_max": [80], "wind_speed_10m_max": [42],
            "weather_code": [75]}, town)
    monkeypatch.setattr("app.weather.get_town_forecast",fake_forecast)
    candidates=[activity("outdoor","outdoor"),activity("indoor","indoor")]
    adjusted, warning=asyncio.run(add_weather(candidates,request()))
    assert warning is None
    assert adjusted[1].weather_source=="Open-Meteo"
    assert "Banff" in adjusted[1].weather_summary
    assert score_candidate(adjusted[1],request())>score_candidate(adjusted[0],request())
    selected=asyncio.run(recommend(adjusted,request()))
    assert selected[0].place_id=="indoor"
    assert selected[0].weather_summary is not None


def test_mild_weather_favors_outdoor(monkeypatch):
    monkeypatch.setenv("WEATHER_PROVIDER","open_meteo")
    async def fake_forecast(town, outing_date=None):
        return interpret_daily({
            "time":["2026-11-06"],"temperature_2m_max":[17],
            "precipitation_probability_max":[10],"wind_speed_10m_max":[12],
            "weather_code":[1]},town)
    monkeypatch.setattr("app.weather.get_town_forecast",fake_forecast)
    adjusted,_=asyncio.run(add_weather([activity("outdoor","outdoor")],request()))
    assert adjusted[0].weather_score_adjustment>0


def test_weather_failure_does_not_block_recommendations(monkeypatch):
    monkeypatch.setenv("WEATHER_PROVIDER","open_meteo")
    async def error(town, outing_date=None):
        raise httpx.TimeoutException("unavailable")
    monkeypatch.setattr("app.weather.get_town_forecast",error)
    candidates=[activity("park","outdoor")]
    adjusted,warning=asyncio.run(add_weather(candidates,request()))
    assert adjusted==candidates
    assert "unavailable" in warning.lower()


def test_weather_off_is_default(monkeypatch):
    monkeypatch.delenv("WEATHER_PROVIDER",raising=False)
    candidates=[activity("park","outdoor")]
    adjusted,warning=asyncio.run(add_weather(candidates,request()))
    assert adjusted==candidates and warning is None


def test_weather_api_parser_rejects_empty_forecast():
    with pytest.raises(ValueError):
        interpret_daily({"time":[]}, "banff")


def test_weather_fetch_uses_cache(monkeypatch):
    _CACHE.clear()
    requests=[]
    class Response:
        def raise_for_status(self): pass
        def json(self):
            return {"daily":{"time":[datetime.now(ZoneInfo("America/Edmonton")).date().isoformat()],"temperature_2m_max":[12],
                  "precipitation_probability_max":[20],"wind_speed_10m_max":[10],"weather_code":[2]}}
    class FakeClient:
        def __init__(self,*a,**kw): pass
        async def __aenter__(self): return self
        async def __aexit__(self,*a): pass
        async def get(self,url,params):
            requests.append((url,params))
            return Response()
    monkeypatch.setattr("app.weather.httpx.AsyncClient",FakeClient)
    a=asyncio.run(get_town_forecast("calgary"))
    b=asyncio.run(get_town_forecast("calgary"))
    assert a==b
    assert len(requests)==1
    assert requests[0][1]["timezone"]=="America/Edmonton"
    assert requests[0][1]["start_date"]==requests[0][1]["end_date"]


def test_requested_visit_date_is_in_schema_and_rejects_past():
    today=datetime.now(ZoneInfo("America/Edmonton")).date()
    r=RecommendationRequest(city="Calgary", children_ages=[2],
                            visit_date=today+timedelta(days=2))
    assert r.visit_date == today + timedelta(days=2)
    with pytest.raises(ValidationError):
        RecommendationRequest(city="Calgary", children_ages=[2],
                              visit_date=today-timedelta(days=1))
    with pytest.raises(ValidationError):
        RecommendationRequest(city="Calgary", children_ages=[2],
                              visit_date=today+timedelta(days=16))


def test_date_specific_forecast_is_passed_to_provider(monkeypatch):
    monkeypatch.setenv("WEATHER_PROVIDER","open_meteo")
    selected=(datetime.now(ZoneInfo("America/Edmonton")).date()+timedelta(days=3))
    called=[]
    async def fake_forecast(town, outing_date=None):
        called.append((town,outing_date))
        return interpret_daily({"time":[outing_date],"temperature_2m_max":[8],
             "precipitation_probability_max":[25],"wind_speed_10m_max":[12],
             "weather_code":[1]}, town, outing_date)
    monkeypatch.setattr("app.weather.get_town_forecast",fake_forecast)
    r=RecommendationRequest(city="Calgary",children_ages=[2],visit_date=selected)
    c=activity("park","outdoor")
    out,w=asyncio.run(add_weather([c],r))
    assert called==[("calgary",selected.isoformat())]
    assert selected.isoformat() in out[0].weather_summary
    assert w is None


def test_forecast_mismatch_rejected():
    with pytest.raises(ValueError,match="does not match"):
        interpret_daily({"time":["2026-11-06"],"temperature_2m_max":[9]},
                         "calgary","2026-11-07")


def test_response_does_not_claim_open_on_visit_date():
    from app.recommend import recommend
    r=RecommendationRequest(city="Calgary",children_ages=[2],
        visit_date=datetime.now(ZoneInfo("America/Edmonton")).date()+timedelta(days=2))
    c=activity("museum","indoor").model_copy(update={"hours_status":"open_now"})
    result=asyncio.run(recommend([c],r))
    assert result[0].hours_status=="open_now"
    assert "hours_for_visit_date" not in result[0].model_dump()


def test_regional_weather_uses_destination_town(monkeypatch):
    monkeypatch.setenv("WEATHER_PROVIDER", "open_meteo")
    selected = datetime.now(ZoneInfo("America/Edmonton")).date() + timedelta(days=2)
    called = []

    async def fake_forecast(town, outing_date=None):
        called.append((town, outing_date))
        return interpret_daily({
            "time": [outing_date],
            "temperature_2m_max": [7],
            "precipitation_probability_max": [20],
            "wind_speed_10m_max": [15],
            "weather_code": [1],
        }, town, outing_date)

    monkeypatch.setattr("app.weather.get_town_forecast", fake_forecast)
    r = RecommendationRequest(city="Calgary", children_ages=[2],
                              search_scope="regional", visit_date=selected)
    out, warning = asyncio.run(add_weather([activity("banff_park", "outdoor")], r))
    assert called == [("banff", selected.isoformat())]
    assert out[0].weather_summary.startswith("Banff forecast")
    assert warning is None
