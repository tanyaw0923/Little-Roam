"""Single live Places Details request per venue for URL and hours (optional).

Keeps Google Maps Platform content request-scoped; does not cache/store
websiteUri, hours, opening statuses, or Places search content in Supabase.
Returns independently sourced curated URLs unchanged.
"""
import asyncio
import logging
import os
from datetime import datetime, timezone
from urllib.parse import quote

import httpx

from .websites import valid_website_url, maps_search_url, PLACE_ID_PATTERN

logger = logging.getLogger(__name__)
PLACE_DETAILS_URL = "https://places.googleapis.com/v1/places/"
MAX_DETAILS_LOOKUPS = 10


def _mask(want_websites, want_hours):
    fields = ["id"]
    if want_websites:
        fields.append("websiteUri")
    if want_hours:
        fields.extend([
            "businessStatus",
            "currentOpeningHours.openNow",
            "currentOpeningHours.weekdayDescriptions",
            "regularOpeningHours.weekdayDescriptions",
        ])
    return ",".join(fields)


def parse_details(data: dict, place_id: str, want_websites: bool, want_hours: bool) -> dict:
    """Treat omitted provider fields as unknown; never guess business schedule."""
    if not isinstance(data, dict) or data.get("id") != place_id:
        return {}
    result = {}
    if want_websites:
        website = valid_website_url(data.get("websiteUri"))
        if website:
            result.update(website_url=website, website_source="google_places")
    if want_hours:
        current = data.get("currentOpeningHours") or {}
        regular = data.get("regularOpeningHours") or {}
        descriptions = current.get("weekdayDescriptions") or regular.get("weekdayDescriptions") or []
        if not isinstance(descriptions, list) or not all(isinstance(x, str) for x in descriptions):
            descriptions = []
        descriptions = [x[:150] for x in descriptions[:7]]
        business_status = data.get("businessStatus")
        open_now = current.get("openNow")
        status = ("permanently_closed" if business_status == "CLOSED_PERMANENTLY"
                  else "open_now" if open_now is True
                  else "closed_now" if open_now is False else "unknown")
        if status != "unknown" or descriptions:
            result.update(
                hours_status=status,
                hours_status_source="google_places" if status != "unknown" else "unknown",
                hours_status_checked_at=(datetime.now(timezone.utc).isoformat()
                                         if status != "unknown" else None),
                hours_source="google_places",
                published_weekly_hours=descriptions,
                hours_checked_at=datetime.now(timezone.utc).isoformat(),
                hours_source_url=("https://www.google.com/maps/search/?api=1&query=venue"
                                  "&query_place_id=" + quote(place_id, safe="")),
            )
    return result


async def enrich_place_details(candidates):
    """Add optional live URLs and hours in ONE Place Details call per venue.

    WEBSITE_PROVIDER / HOURS_PROVIDER toggle their fields individually.
    For missing IDs, enable PLACE_MATCH_PROVIDER=google_places separately.
    """
    want_websites = os.getenv("WEBSITE_PROVIDER", "off").lower() == "google_places"
    want_hours = os.getenv("HOURS_PROVIDER", "off").lower() == "google_places"
    result = [c.model_copy(update={
        "google_maps_url": c.google_maps_url or maps_search_url(c),
        "website_url": valid_website_url(c.website_url),
        "website_source": ("google_places" if c.source == "google_places" else "curated")
                          if valid_website_url(c.website_url) else "unknown",
    }) for c in candidates]
    if not (want_websites or want_hours):
        return result, None
    key = os.getenv("GOOGLE_MAPS_API_KEY")
    if not key:
        return result, "Google Places key unavailable; website or hours details remain unknown."
    # Approved official schedules take precedence; Google hours are fallback only.
    # Website details remain optional even when official hours exist.
    targets = [
        (index, c.google_place_id, bool(want_websites and not valid_website_url(c.website_url)),
         bool(want_hours and c.hours_source == "unknown"))
        for index, c in enumerate(result)
        if isinstance(c.google_place_id, str)
        and PLACE_ID_PATTERN.fullmatch(c.google_place_id)
        and ((want_hours and c.hours_source == "unknown")
             or (want_websites and not valid_website_url(c.website_url)))
    ][:MAX_DETAILS_LOOKUPS]
    if not targets:
        if want_hours and any(c.google_place_id is None and c.hours_source == "unknown" for c in result):
            return result, "Some venues lack verified Google Place IDs; operating hours remain unknown."
        return result, None
    async with httpx.AsyncClient(timeout=10) as client:
        async def fetch(index, place_id, get_website, get_hours):
            try:
                response = await client.get(
                    PLACE_DETAILS_URL + place_id,
                    headers={"X-Goog-Api-Key": key,
                             "X-Goog-FieldMask": _mask(get_website, get_hours)},
                )
                response.raise_for_status()
                return index, parse_details(response.json(), place_id, get_website, get_hours)
            except (httpx.HTTPError, TypeError, ValueError, KeyError) as exc:
                logger.warning("Live Google venue details failed (%s)", type(exc).__name__)
                return index, {}
        details = await asyncio.gather(*(fetch(*args) for args in targets))
    unresolved = 0
    for index, updates in details:
        if updates:
            result[index] = result[index].model_copy(update=updates)
        else:
            unresolved += 1
    return result, ("Some Google Places websites or hours were unavailable; unknown values are not inferred."
                    if unresolved else None)
