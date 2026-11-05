"""Drive-time filters for regional searches using Google Routes API.

No guesswork: missing/error routes are excluded. Uses traffic-unaware route
duration (not predicted live traffic). Google route results are not persisted.
Only route at most 25 candidates per search to cap billable matrix elements.
"""
import math
import os
import re

import httpx
from fastapi import HTTPException

from .geo import origin_for, straight_line_km
from .models import Candidate, RecommendationRequest

ROUTE_MATRIX_URL = "https://routes.googleapis.com/distanceMatrix/v2:computeRouteMatrix"
MAX_ROUTE_ELEMENTS = 25
MAX_GEO_CANDIDATES_KM = 250

def _waypoint(lat: float, lon: float) -> dict:
    return {"waypoint": {"location": {"latLng": {"latitude": lat, "longitude": lon}}}}

def _duration_minutes(value: str) -> float | None:
    # Google's protobuf Duration JSON is "<number>s", including fractional seconds.
    if not isinstance(value, str) or not re.fullmatch(r"\d+(?:\.\d+)?s", value):
        return None
    seconds = float(value[:-1])
    return round(seconds / 60, 1) if math.isfinite(seconds) else None

def shortlist(candidates: list[Candidate], request: RecommendationRequest) -> list[Candidate]:
    """Cheap relevance/coordinate preselection before any paid routing call."""
    from .recommend import eligible, score_candidate
    origin = origin_for(request.province, request.city)
    if origin is None:
        return []
    found = []
    for item in candidates:
        if item.latitude is None or item.longitude is None or not eligible(item, request):
            continue
        straight_km = straight_line_km(*origin, item.latitude, item.longitude)
        if straight_km > MAX_GEO_CANDIDATES_KM:
            continue
        found.append((item, straight_km))
    found.sort(key=lambda t: (-score_candidate(t[0], request), t[1], t[0].place_id))
    return [x for x, _ in found[:MAX_ROUTE_ELEMENTS]]

async def routes_for_candidates(candidates: list[Candidate], request: RecommendationRequest) -> list[Candidate]:
    """Attach genuine drive minutes/road kilometres; do not substitute aerial distances."""
    if not candidates:
        return []
    key = os.getenv("GOOGLE_ROUTES_API_KEY")
    if not key:
        raise HTTPException(503, "GOOGLE_ROUTES_API_KEY is required for regional driving searches")

    origin = origin_for(request.province, request.city)
    if origin is None:
        raise HTTPException(422, "Unsupported regional origin")

    payload = {
        "origins": [_waypoint(*origin)],
        "destinations": [_waypoint(c.latitude, c.longitude) for c in candidates],
        "travelMode": "DRIVE",
        "routingPreference": "TRAFFIC_UNAWARE",
    }
    headers = {
        "X-Goog-Api-Key": key,
        "X-Goog-FieldMask": "originIndex,destinationIndex,status,condition,duration,distanceMeters",
        "Content-Type": "application/json",
    }
    try:
        async with httpx.AsyncClient(timeout=25) as client:
            response = await client.post(ROUTE_MATRIX_URL, headers=headers, json=payload)
            response.raise_for_status()
            elements = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(502, "Driving routes provider unavailable") from exc

    if not isinstance(elements, list):
        raise HTTPException(502, "Unexpected driving routes response")

    by_index = {}
    for element in elements:
        if not isinstance(element, dict) or element.get("originIndex") != 0:
            continue
        idx = element.get("destinationIndex")
        if not isinstance(idx, int) or idx < 0 or idx >= len(candidates):
            continue
        if element.get("condition") != "ROUTE_EXISTS":
            continue
        status = element.get("status") or {}
        if isinstance(status, dict) and status.get("code", 0) not in (0, None):
            continue
        duration = _duration_minutes(element.get("duration"))
        distance = element.get("distanceMeters")
        if duration is None or not isinstance(distance, (int, float)) or distance < 0:
            continue
        if duration <= request.max_drive_minutes:
            by_index[idx] = (duration, round(distance / 1000, 1))

    result = []
    for idx, candidate in enumerate(candidates):
        if idx in by_index:
            minutes, distance = by_index[idx]
            result.append(candidate.model_copy(update={
                "drive_minutes": minutes, "distance_km": distance
            }))
    return result

async def filter_by_driving_time(candidates: list[Candidate], request: RecommendationRequest) -> list[Candidate]:
    if request.search_scope != "regional":
        return candidates
    selected = shortlist(candidates, request)
    return await routes_for_candidates(selected, request)
