"""Great-circle distance — shared by the route planner's fake routing
client (straight-line estimate) and its nearest-charger lookup (no
routing engine call needed just to rank candidates by proximity).
"""

from __future__ import annotations

import math

EARTH_RADIUS_KM = 6371.0


def haversine_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    """`a`/`b` are `(lat, lng)` pairs in degrees."""
    lat1, lng1 = math.radians(a[0]), math.radians(a[1])
    lat2, lng2 = math.radians(b[0]), math.radians(b[1])
    d_lat = lat2 - lat1
    d_lng = lng2 - lng1
    h = math.sin(d_lat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(d_lng / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(h))
