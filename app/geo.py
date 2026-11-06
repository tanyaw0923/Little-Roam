"""Regional geographic search helpers.

Coordinate anchors are approximate municipal centres, not the user's address.
Distance is straight-line, not driving distance.
"""
from math import asin, cos, radians, sin, sqrt

# Conservative initial support. Add municipalities after validating anchors.
CENTRES = {
    ("AB", "calgary"): (51.0447, -114.0719),
    ("AB", "canmore"): (51.0890, -115.3590),
    ("AB", "banff"): (51.1784, -115.5708),
}


def origin_for(province: str, city: str) -> tuple[float, float] | None:
    return CENTRES.get((province.upper(), city.strip().lower()))


def straight_line_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Haversine geographic distance in kilometres."""
    earth_radius_km = 6371.0088
    p1, p2 = radians(lat1), radians(lat2)
    dp, dl = radians(lat2 - lat1), radians(lon2 - lon1)
    a = sin(dp / 2) ** 2 + cos(p1) * cos(p2) * sin(dl / 2) ** 2
    return 2 * earth_radius_km * asin(min(1.0, sqrt(a)))


def bounding_box(lat: float, lon: float, radius_km: float) -> tuple[float, float, float, float]:
    """Loose bounding box for a cheap database prefilter; always enforce haversine after."""
    lat_delta = radius_km / 110.57
    lon_delta = radius_km / max(1e-6, 111.32 * cos(radians(lat)))
    return lat - lat_delta, lat + lat_delta, lon - lon_delta, lon + lon_delta


def request_origin(request) -> tuple[float, float] | None:
    """Use verified postal-code origin when provided; otherwise the town centre."""
    if request._resolved_origin is not None:
        return request._resolved_origin
    return origin_for(request.province, request.city)
