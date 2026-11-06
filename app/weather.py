"""Optional, failure-tolerant weather context for Little Roam recommendations.

MVP: chosen outing-date daily forecast for the nearest supported Bow Valley town.
Open-Meteo's public endpoint is for non-commercial evaluation; commercial
deployment requires an appropriate provider licence/plan.
"""
import asyncio
import logging
import os
import time

import httpx

from datetime import datetime
from zoneinfo import ZoneInfo

from .geo import CENTRES, straight_line_km

logger = logging.getLogger(__name__)
OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
CACHE_SECONDS = 900
_CACHE = {}  # (province, city) -> (monotonic-expiry, forecast)

def nearest_town(latitude: float, longitude: float) -> str:
    options = [(straight_line_km(latitude, longitude, lat, lon), city)
               for (province, city), (lat, lon) in CENTRES.items() if province == "AB"]
    return min(options)[1] if options else "calgary"

def weather_town(candidate, request):
    if request.search_scope == "regional" and candidate.latitude is not None and candidate.longitude is not None:
        return nearest_town(candidate.latitude, candidate.longitude)
    return request.city.strip().lower()

def interpret_daily(daily: dict, town: str, expected_date: str | None = None):
    """Conservative indoor/outdoor preference—not a safety determination."""
    def first(field):
        values = daily.get(field)
        return values[0] if isinstance(values, list) and values else None

    temp = first("temperature_2m_max")
    precip = first("precipitation_probability_max")
    wind = first("wind_speed_10m_max")
    code = first("weather_code")
    day = first("time")
    if day is None or all(v is None for v in (temp, precip, wind, code)):
        raise ValueError("Incomplete daily forecast")
    if expected_date is not None and day != expected_date:
        raise ValueError('Forecast date does not match outing date')
    if not isinstance(day, str):
        raise ValueError("Unexpected forecast date")
    risk = ((isinstance(precip, (int, float)) and precip >= 65)
            or (isinstance(wind, (int, float)) and wind >= 40)
            or (isinstance(temp, (int, float)) and (temp <= -15 or temp >= 32))
            or (isinstance(code, (int, float)) and int(code) in (65, 67, 75, 77, 82, 86, 95, 96, 99)))
    parts = []
    if isinstance(temp, (int, float)):
        parts.append(f"high {temp:g}°C")
    if isinstance(precip, (int, float)):
        parts.append(f"precipitation chance up to {precip:g}%")
    if isinstance(wind, (int, float)):
        parts.append(f"wind up to {wind:g} km/h")
    return {"date": day, "town": town.title(), "summary": f"{town.title()} forecast for {day}: " + ", ".join(parts),
            "indoor_favoured": bool(risk), "source": "Open-Meteo"}

async def get_town_forecast(town: str, outing_date: str | None = None):
    outing_date = outing_date or datetime.now(ZoneInfo('America/Edmonton')).date().isoformat()
    key = ("AB", town, outing_date)
    cached = _CACHE.get(key)
    if cached and cached[0] > time.monotonic():
        return cached[1]
    latlon = CENTRES.get(key)
    if latlon is None:
        return None
    params = {"latitude": latlon[0], "longitude": latlon[1],
              "daily": "weather_code,temperature_2m_max,precipitation_probability_max,wind_speed_10m_max",
              "timezone": "America/Edmonton", "start_date": outing_date, "end_date": outing_date}
    async with httpx.AsyncClient(timeout=6) as client:
        response = await client.get(OPEN_METEO_URL, params=params)
        response.raise_for_status()
        forecast = interpret_daily(response.json()["daily"], town, outing_date)
    _CACHE[key] = (time.monotonic() + CACHE_SECONDS, forecast)
    return forecast

async def add_weather(candidates, request):
    """Return (annotated candidates, warning). Forecast failures never block search."""
    provider = os.getenv("WEATHER_PROVIDER", "off").lower()
    if provider == "off":
        return candidates, None
    if provider != "open_meteo":
        return candidates, "Unsupported weather provider; weather adjustment skipped."
    if not candidates:
        return candidates, None
    towns = {weather_town(c, request) for c in candidates}
    outing_date = (request.visit_date or datetime.now(ZoneInfo('America/Edmonton')).date()).isoformat()
    async def safe_fetch(town):
        try:
            return town, await get_town_forecast(town, outing_date)
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
            logger.warning("Weather forecast unavailable for %s: %s", town, type(exc).__name__)
            return town, None
    weather = dict(await asyncio.gather(*(safe_fetch(town) for town in towns)))
    annotated = []
    for c in candidates:
        forecast = weather.get(weather_town(c, request))
        if not forecast:
            annotated.append(c)
            continue
        # Ranking bonus/penalty is intentionally modest. Never exclude outdoor
        # activities based on a daily forecast or assert current conditions.
        adjustment = (0.75 if c.activity_type == "indoor" else -0.75 if c.activity_type == "outdoor" else 0.0) if forecast["indoor_favoured"] else (0.3 if c.activity_type == "outdoor" else 0.0)
        annotated.append(c.model_copy(update={
            "weather_summary": forecast["summary"],
            "weather_source": forecast["source"],
            "weather_score_adjustment": adjustment}))
    missing = [town for town in towns if weather.get(town) is None]
    warning = ("Forecast unavailable for " + ", ".join(sorted(missing)) + "; rankings use non-weather signals there.") if missing else None
    return annotated, warning
