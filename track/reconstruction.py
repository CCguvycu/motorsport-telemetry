"""
Reconstruct a Track object from raw telemetry points.
"""
import numpy as np
from typing import List, Optional
from core.models import Track, TelemetryPoint
from track.geometry import arc_length, smooth_path, compute_curvature, resample_path
from track.classifier import classify_segments


def reconstruct_track(
    points: List[TelemetryPoint],
    name: str = "Unknown Track",
    smoothing: float = 5.0,
    n_resample: Optional[int] = None,
) -> Track:
    """
    Build a Track from telemetry data.

    Pipeline:
        raw coords → [optional resample] → spline smooth → curvature → classify

    Args:
        points:     telemetry sorted by timestamp
        name:       label for the track
        smoothing:  spline smoothing factor (higher = smoother, less faithful)
        n_resample: if set, resample to this many uniformly-spaced points first

    Returns:
        Track with reconstructed geometry and classified segments
    """
    coords = np.array([[p.x, p.y] for p in points])

    if n_resample is not None and n_resample != len(coords):
        coords = resample_path(coords, n_resample)

    try:
        smooth = smooth_path(coords, smoothing=smoothing)
    except Exception:
        smooth = coords  # fall back to raw coords if scipy unavailable

    kappa = compute_curvature(smooth)
    s = arc_length(smooth)
    total_length = float(s[-1])

    segments = classify_segments(smooth, kappa, s)

    return Track(
        name=name,
        points=[(float(x), float(y)) for x, y in smooth],
        curvature=kappa.tolist(),
        segments=segments,
        total_length=total_length,
    )


def extract_lap_points(
    all_points: List[TelemetryPoint],
    lap_number: int,
) -> List[TelemetryPoint]:
    """Return only the TelemetryPoints for the given lap number."""
    lap_pts = [p for p in all_points if p.lap == lap_number]
    if not lap_pts:
        raise ValueError(f"No telemetry found for lap {lap_number}")
    return lap_pts
