"""Small spherical-earth helpers. Accurate enough for harbour-scale distances."""

import math

EARTH_RADIUS_M = 6_371_000.0
METERS_PER_NAUTICAL_MILE = 1852.0

Position = tuple[float, float]  # (latitude, longitude) in degrees


def distance_m(a: Position, b: Position) -> float:
    lat1, lon1, lat2, lon2 = map(math.radians, (*a, *b))
    h = (
        math.sin((lat2 - lat1) / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    )
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(h))


def bearing_deg(a: Position, b: Position) -> float:
    """Initial bearing from a to b, 0-360 degrees clockwise from north."""
    lat1, lon1, lat2, lon2 = map(math.radians, (*a, *b))
    y = math.sin(lon2 - lon1) * math.cos(lat2)
    x = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(lon2 - lon1)
    return math.degrees(math.atan2(y, x)) % 360


def move(origin: Position, bearing: float, meters: float) -> Position:
    lat1, lon1 = map(math.radians, origin)
    theta = math.radians(bearing)
    delta = meters / EARTH_RADIUS_M
    lat2 = math.asin(
        math.sin(lat1) * math.cos(delta) + math.cos(lat1) * math.sin(delta) * math.cos(theta)
    )
    lon2 = lon1 + math.atan2(
        math.sin(theta) * math.sin(delta) * math.cos(lat1),
        math.cos(delta) - math.sin(lat1) * math.sin(lat2),
    )
    return math.degrees(lat2), math.degrees(lon2)
