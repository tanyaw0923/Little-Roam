"""Postal-code origin lookup for Canadian regional searches.

The coordinate is an approximate postal-code geocode, not a household location.
Never log, persist or echo a submitted postal code.
Requires a separate Geocoding API-restricted server key.
"""
import os
import re

import httpx
from fastapi import HTTPException

POSTAL_RE = re.compile(r"^[ABCEGHJ-NPRSTVXY]\d[ABCEGHJ-NPRSTV-Z][ ]?\d[ABCEGHJ-NPRSTV-Z]\d$", re.I)
URL = "https://maps.googleapis.com/maps/api/geocode/json"

def normalize_postal_code(code: str) -> str:
    normalized = re.sub(r"\s+", "", code).upper()
    if not POSTAL_RE.fullmatch(normalized):
        raise ValueError("Enter a valid six-character Canadian postal code")
    return normalized[:3] + " " + normalized[3:]

async def resolve_postal_origin(postal_code: str, province: str) -> tuple[float, float]:
    code = normalize_postal_code(postal_code)
    # First version is explicitly Alberta-only for Bow Valley searches.
    if province != "AB" or not code.startswith("T"):
        raise HTTPException(422, "Postal-code regional search currently supports Alberta (T-prefix) postal codes only")
    key = os.getenv("GOOGLE_GEOCODING_API_KEY")
    if not key:
        raise HTTPException(503, "GOOGLE_GEOCODING_API_KEY is required for postal-code search")
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(URL, params={
                "components": f"postal_code:{code.replace(' ', '')}|country:CA",
                "key": key,
            })
            response.raise_for_status()
            data = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(502, "Postal-code geocoding unavailable") from exc
    status = data.get("status")
    if status == "ZERO_RESULTS":
        raise HTTPException(422, "Postal code could not be located")
    if status != "OK":
        raise HTTPException(502, "Postal-code geocoding provider failed")
    for result in data.get("results", []):
        if result.get("partial_match"):
            continue
        components = result.get("address_components") or []
        matching_code = any(
            "postal_code" in x.get("types", [])
            and x.get("long_name", "").replace(" ", "").upper() == code.replace(" ", "")
            for x in components)
        is_alberta = any(
            "administrative_area_level_1" in x.get("types", [])
            and x.get("short_name") == "AB"
            for x in components)
        is_canada = any("country" in x.get("types", []) and x.get("short_name") == "CA" for x in components)
        loc = (result.get("geometry") or {}).get("location") or {}
        lat, lon = loc.get("lat"), loc.get("lng")
        if matching_code and is_alberta and is_canada and isinstance(lat, (int,float)) and isinstance(lon,(int,float)):
            if 48.0 <= lat <= 60.1 and -120.1 <= lon <= -109.9:
                return float(lat), float(lon)
    raise HTTPException(422, "Postal code could not be verified in Alberta")
