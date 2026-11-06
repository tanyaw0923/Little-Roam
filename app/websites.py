"""Live Google Places website fallback for reviewed Place IDs.

Google websiteUri content is request-scoped: never persist it in Supabase.
Google Place IDs may be stored under the Maps Platform terms. Only fill missing
website URLs from an exact linked Place ID, never infer by fuzzy name matching.
"""
import asyncio
import logging
import os
import re
from urllib.parse import urlparse, quote

import httpx

logger = logging.getLogger(__name__)
PLACE_DETAILS_URL = "https://places.googleapis.com/v1/places/"
MAX_WEBSITE_LOOKUPS = 10
PLACE_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,250}$")


def valid_website_url(url: object) -> str | None:
    if not isinstance(url, str) or len(url) > 2048:
        return None
    parsed = urlparse(url.strip())
    if parsed.scheme not in ("https", "http") or not parsed.hostname:
        return None
    if parsed.username or parsed.password:
        return None
    host = parsed.hostname.lower()
    if host in ("localhost",) or host.endswith((".local", ".internal")):
        return None
    return url.strip()


def maps_search_url(candidate) -> str:
    """Clickable map search link is not equivalent to a venue website."""
    if candidate.google_place_id and PLACE_ID_PATTERN.fullmatch(candidate.google_place_id):
        return ("https://www.google.com/maps/search/?api=1&query="
                + quote(candidate.name, safe="")
                + "&query_place_id=" + quote(candidate.google_place_id, safe=""))
    return ("https://www.google.com/maps/search/?api=1&query="
            + quote(f"{candidate.name}, {candidate.address}", safe=""))


async def _website_from_place_id(client, place_id: str, key: str) -> str | None:
    if not PLACE_ID_PATTERN.fullmatch(place_id):
        return None
    response = await client.get(
        PLACE_DETAILS_URL + place_id,
        headers={"X-Goog-Api-Key": key, "X-Goog-FieldMask": "id,websiteUri"},
    )
    response.raise_for_status()
    data = response.json()
    if data.get("id") != place_id:
        return None
    return valid_website_url(data.get("websiteUri"))


async def enrich_websites(candidates):
    """Add Google Maps links and optional ephemeral websiteUri for exact IDs.

    Only use when WEBSITE_PROVIDER=google_places and GOOGLE_MAPS_API_KEY is set.
    Up to ten Place Details website lookups per request, for missing URLs only.
    Fail open if the provider returns an error or lacks a website.
    """
    updated = [c.model_copy(update={
        "google_maps_url": c.google_maps_url or maps_search_url(c),
        "website_source": ("google_places" if c.source == "google_places" else "curated")
                          if valid_website_url(c.website_url) else "unknown",
    }) for c in candidates]
    provider = os.getenv("WEBSITE_PROVIDER", "off").lower()
    if provider == "off":
        return updated, None
    if provider != "google_places":
        return updated, "Unsupported website provider; venue website fallback skipped."
    key = os.getenv("GOOGLE_MAPS_API_KEY")
    if not key:
        return updated, "Google Places website fallback not configured; missing website URLs remain unknown."
    targets = [
        (i, c.google_place_id)
        for i, c in enumerate(updated)
        if not valid_website_url(c.website_url)
        and isinstance(c.google_place_id, str)
        and PLACE_ID_PATTERN.fullmatch(c.google_place_id)
    ][:MAX_WEBSITE_LOOKUPS]
    if not targets:
        return updated, None
    async with httpx.AsyncClient(timeout=8) as client:
        async def resolve(index, place_id):
            try:
                return index, await _website_from_place_id(client, place_id, key)
            except (httpx.HTTPError, ValueError, TypeError) as exc:
                logger.warning("Venue website lookup failed (%s)", type(exc).__name__)
                return index, None
        responses = await asyncio.gather(*(resolve(i, place_id) for i, place_id in targets))
    missing = 0
    for index, url in responses:
        if url:
            updated[index] = updated[index].model_copy(update={"website_url": url, "website_source": "google_places"})
        else:
            missing += 1
    return updated, ("Some Google Places listings have no confirmed website; Maps links are provided instead."
                     if missing else None)
