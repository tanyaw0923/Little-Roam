"""Optional live opening-hours verification via Places API (New).

Only fetch a Place Details record when an exact Google Place ID is already
linked to the activity by trusted mapping, or comes directly from a Places result.
Never infer an ID from a name match; never persist third-party hours.
"""
import asyncio
import logging
import os
from datetime import datetime, timezone

import httpx

logger=logging.getLogger(__name__)
MAX_HOURS_REQUESTS=10
BASE="https://places.googleapis.com/v1/places/"
FIELD_MASK="id,businessStatus,currentOpeningHours.openNow"

async def _fetch_hours(client, place_id: str, api_key: str):
    if not place_id or len(place_id)>250 or not all(x.isalnum() or x in "-_" for x in place_id):
        return None
    response = await client.get(BASE+place_id, headers={
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": FIELD_MASK,
    })
    response.raise_for_status()
    data=response.json()
    if data.get("id")!=place_id:
        return None
    if data.get("businessStatus") == "CLOSED_PERMANENTLY":
        return "closed_now"
    value=(data.get("currentOpeningHours") or {}).get("openNow")
    if isinstance(value, bool):
        return "open_now" if value else "closed_now"
    return None

async def verify_hours(candidates):
    """Fail-open, bounded hours lookup. Returns updated items and a warning."""
    if os.getenv("HOURS_PROVIDER","off").lower()!="google_places":
        return candidates,None
    key=os.getenv("GOOGLE_MAPS_API_KEY")
    if not key:
        return candidates,"Hours verification not configured; hours status is unknown."
    # Only provider-backed IDs: curated attractions must be deliberately linked.
    allowed=[(i,c.google_place_id) for i,c in enumerate(candidates)
             if c.google_place_id][:MAX_HOURS_REQUESTS]
    if not allowed:
        return candidates,"No verified Google Place ID mappings; venue operating hours remain unknown."
    updated=list(candidates)
    async with httpx.AsyncClient(timeout=8) as client:
        async def lookup(index, place_id):
            try:
                return index,await _fetch_hours(client,place_id,key)
            except (httpx.HTTPError,ValueError,TypeError) as exc:
                logger.warning("Hours lookup unavailable: %s",type(exc).__name__)
                return index,None
        results=await asyncio.gather(*(lookup(i,pid) for i,pid in allowed))
    checked=datetime.now(timezone.utc).isoformat()
    for index,status in results:
        if status is not None:
            updated[index]=updated[index].model_copy(update={
                "hours_status":status,
                "hours_checked_at":checked,
                "hours_source_url":"https://www.google.com/maps/search/?api=1&query=Google&query_place_id=" + updated[index].google_place_id,
            })
    missing=sum(x is None for _,x in results)
    return updated, ("Some operating hours could not be confirmed and remain unknown." if missing else None)
