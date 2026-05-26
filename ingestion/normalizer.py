"""
Coordinate normalization utilities.

GPS (lat/lon) → local metric (x, y in metres) via an equirectangular projection
centred on the session origin.  Error < 0.1 % for track-scale distances (< 10 km).
"""
import math
from typing import List, Optional
from core.models import TelemetryPoint

EARTH_RADIUS_M = 6_371_000.0


def gps_to_local(
    points: List[TelemetryPoint],
    ref_lat: Optional[float] = None,
    ref_lon: Optional[float] = None,
) -> List[TelemetryPoint]:
    """
    Project lat/lon → local x/y in metres.  Mutates and returns the list.

    Args:
        points:  list with x=longitude, y=latitude (degrees)
        ref_lat: origin latitude  (defaults to first point)
        ref_lon: origin longitude (defaults to first point)
    """
    if not points:
        return points

    lat0 = ref_lat if ref_lat is not None else points[0].y
    lon0 = ref_lon if ref_lon is not None else points[0].x
    lat0_rad = math.radians(lat0)

    for p in points:
        dlat = math.radians(p.y - lat0)
        dlon = math.radians(p.x - lon0)
        p.x = dlon * EARTH_RADIUS_M * math.cos(lat0_rad)
        p.y = dlat * EARTH_RADIUS_M

    return points


def detect_coordinate_type(points: List[TelemetryPoint]) -> str:
    """
    Heuristic: values within GPS bounds → 'gps', otherwise 'metric'.

    GPS: |longitude| ≤ 180, |latitude| ≤ 90
    """
    if not points:
        return "metric"
    if all(-180 <= p.x <= 180 and -90 <= p.y <= 90 for p in points):
        return "gps"
    return "metric"
