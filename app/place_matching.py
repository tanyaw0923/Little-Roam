"""Opt-in exact-name, nearby-coordinate match to Google Places (New).

Source records remain authoritative. Matching is request-scoped; only the
Google Place ID may be persisted by a separate manual curation workflow.
No Google text-search content is stored or auto-written to Supabase.
"""
import asyncio
import logging
import os
import re

import httpx

from .geo import straight_line_km

logger = logging.getLogger(__name__)
TEXT_SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"
MAX_MATCH_LOOKUPS = 5
MAX_DISTANCE_KM = 0.35
SEARCH_FIELD_MASK = "places.id,places.displayName.text,places.formattedAddress,places.location"


def _clean_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.casefold())


def confirmed_match(candidate, places: list[dict]) -> str | None:
    """Require exact normalized venue name AND verified proximity.

    Coordinates are from Little Roam's independently sourced activity record.
    Name-only matches (or missing coordinates) must not be accepted.
    """
    if candidate.latitude is None or candidate.longitude is None:
        return None
    expected = _clean_name(candidate.name)
    matches = []
    for place in places:
        if not isinstance(place, dict):
            continue
        place_id = place.get("id")
        from .websites import PLACE_ID_PATTERN
        if not isinstance(place_id, str) or not PLACE_ID_PATTERN.fullmatch(place_id):
            continue
        name = (place.get("displayName") or {}).get("text")
        location = place.get("location") or {}
        lat, lon = location.get("latitude"), location.get("longitude")
        if not isinstance(name, str) or _clean_name(name) != expected:
            continue
        if not all(isinstance(x, (int, float)) for x in (lat, lon)):
            continue
        separation = straight_line_km(candidate.latitude, candidate.longitude, lat, lon)
        if separation <= MAX_DISTANCE_KM:
            matches.append(place_id)
    # Do not pick arbitrarily among nearby duplicate listings.
    return matches[0] if len(matches) == 1 else None


async def match_missing_place_ids(candidates):
    """Optional cost-capped Places Text Search for independently geolocated venues."""
    if os.getenv("PLACE_MATCH_PROVIDER", "off").lower() != "google_places":
        return candidates, None
    key = os.getenv("GOOGLE_MAPS_API_KEY")
    if not key:
        return candidates, "Place matching unavailable; GOOGLE_MAPS_API_KEY missing."
    targets = [
        (i, c)
        for i, c in enumerate(candidates)
        if c.google_place_id is None
        and c.source == "curated"
        and c.latitude is not None and c.longitude is not None
    ][:MAX_MATCH_LOOKUPS]
    if not targets:
        return candidates, None
    updated = list(candidates)
    async with httpx.AsyncClient(timeout=10) as client:
        async def lookup(index, candidate):
            try:
                response = await client.post(
                    TEXT_SEARCH_URL,
                    headers={"X-Goog-Api-Key": key,
                             "X-Goog-FieldMask": SEARCH_FIELD_MASK,
                             "Content-Type": "application/json"},
                    json={"textQuery": f"{candidate.name}, {candidate.address}, Alberta, Canada",
                          "regionCode": "CA", "maxResultCount": 5},
                )
                response.raise_for_status()
                data = response.json()
                return index, confirmed_match(candidate, data.get("places") or [])
            except (httpx.HTTPError, ValueError, TypeError, KeyError) as exc:
                logger.warning("Exact venue match failed (%s)", type(exc).__name__)
                return index, None
        matched = await asyncio.gather(*(lookup(i, c) for i, c in targets))
    unresolved = 0
    for index, place_id in matched:
        if place_id:
            updated[index] = updated[index].model_copy(update={"google_place_id": place_id})
        else:
            unresolved += 1
    return updated, (
        f"{unresolved} venue(s) could not be confidently matched to Google Places; "
        "website and hours may remain unknown."
        if unresolved else None
    )
