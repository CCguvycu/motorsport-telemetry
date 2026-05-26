"""
Per-segment and per-lap performance metrics.
"""
import numpy as np
from typing import List, Tuple
from core.models import TelemetryPoint, Track, DriverRun, SegmentDelta


def map_telemetry_to_segments(
    run: DriverRun,
    track: Track,
) -> List[List[TelemetryPoint]]:
    """
    Bucket each telemetry point into the track segment it falls in.

    Uses nearest-neighbour projection onto the track polyline.

    Returns:
        List of length len(track.segments); each entry is the subset of
        telemetry points within that segment.
    """
    track_pts = np.array(track.points)  # (M, 2)
    n_segs = len(track.segments)
    buckets: List[List[TelemetryPoint]] = [[] for _ in range(n_segs)]

    # Build a lookup: track_point_index → segment_index
    pt_to_seg = np.empty(len(track_pts), dtype=int)
    for seg in track.segments:
        pt_to_seg[seg.start_idx : seg.end_idx + 1] = seg.index

    for tp in run.telemetry:
        pos = np.array([tp.x, tp.y])
        nearest = int(np.argmin(np.linalg.norm(track_pts - pos, axis=1)))
        buckets[pt_to_seg[nearest]].append(tp)

    return buckets


def segment_time(points: List[TelemetryPoint]) -> float:
    """Time span of a list of telemetry points (seconds)."""
    if len(points) < 2:
        return 0.0
    return points[-1].timestamp - points[0].timestamp


def segment_avg_speed(points: List[TelemetryPoint]) -> float:
    """Mean speed over a segment (m/s)."""
    if not points:
        return 0.0
    return float(np.mean([p.speed for p in points]))


def compute_segment_deltas(
    run: DriverRun,
    reference: DriverRun,
    track: Track,
) -> Tuple[List[SegmentDelta], float]:
    """
    Per-segment delta times: run vs reference.

    Returns:
        (list of SegmentDelta, cumulative total delta in seconds)
    """
    run_buckets = map_telemetry_to_segments(run, track)
    ref_buckets = map_telemetry_to_segments(reference, track)

    deltas: List[SegmentDelta] = []
    total = 0.0

    for seg in track.segments:
        i = seg.index
        actual_t = segment_time(run_buckets[i])
        ref_t    = segment_time(ref_buckets[i])
        delta    = actual_t - ref_t
        total   += delta

        speed_loss = segment_avg_speed(ref_buckets[i]) - segment_avg_speed(run_buckets[i])

        deltas.append(SegmentDelta(
            segment_index=i,
            actual_time=actual_t,
            reference_time=ref_t,
            delta=delta,
            speed_loss=speed_loss,
        ))

    return deltas, total


def compute_consistency_score(runs: List[DriverRun]) -> float:
    """
    Lap-to-lap consistency as 1 − (σ / μ) of lap times.
    Returns 1.0 for a single run or perfectly equal times.
    """
    if len(runs) < 2:
        return 1.0
    times = [r.lap_time for r in runs if r.lap_time is not None]
    if not times or np.mean(times) == 0:
        return 0.0
    cv = np.std(times) / np.mean(times)
    return float(max(0.0, 1.0 - cv))


def speed_heatmap(run: DriverRun) -> List[float]:
    """
    Per-telemetry-point speed normalised to [0, 1].
    0 = minimum speed in run, 1 = maximum.
    """
    speeds = np.array([p.speed for p in run.telemetry])
    s_min, s_max = speeds.min(), speeds.max()
    if s_max == s_min:
        return [0.5] * len(speeds)
    return ((speeds - s_min) / (s_max - s_min)).tolist()
