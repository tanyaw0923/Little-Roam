import asyncio
import pytest
import httpx

from app.models import Candidate, RecommendationRequest
from app.weather import _CACHE, nearest_town, interpret_daily, add_weather, get_town_forecast
from app.recommend import recommend, score_candidate


def request():
    return RecommendationRequest(city="Calgary", province="AB", children_ages=[2],
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
    async def fake_forecast(town):
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
    async def fake_forecast(town):
        return interpret_daily({
            "time":["2026-11-06"],"temperature_2m_max":[17],
            "precipitation_probability_max":[10],"wind_speed_10m_max":[12],
            "weather_code":[1]},town)
    monkeypatch.setattr("app.weather.get_town_forecast",fake_forecast)
    adjusted,_=asyncio.run(add_weather([activity("outdoor","outdoor")],request()))
    assert adjusted[0].weather_score_adjustment>0


def test_weather_failure_does_not_block_recommendations(monkeypatch):
    monkeypatch.setenv("WEATHER_PROVIDER","open_meteo")
    async def error(town):
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
            return {"daily":{"time":["2026-11-06"],"temperature_2m_max":[12],
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
