"""
Segment classification: corners vs straights.

Threshold-based approach with a minimum-length guard to prevent fragmentation.
Corner entry / apex / exit sub-classification requires speed data and is handled
in the analysis layer where DriverRun data is available.
"""
import numpy as np
from typing import List
from core.models import TrackSegment, SegmentType

# A point is "in a corner" when its radius < 1/CORNER_THRESHOLD metres
CORNER_CURVATURE_THRESHOLD = 0.01   # 1/m  →  radius < 100 m
MIN_SEGMENT_LENGTH         = 10.0   # metres — merge shorter runs into neighbours


def classify_segments(
    points: np.ndarray,
    curvature: np.ndarray,
    arc_lengths: np.ndarray,
) -> List[TrackSegment]:
    """
    Partition the track into STRAIGHT / APEX segments.

    Args:
        points:      (N, 2) smoothed path
        curvature:   (N,) signed curvature values
        arc_lengths: (N,) cumulative arc length

    Returns:
        List of TrackSegment objects in track order
    """
    n = len(points)
    abs_kappa = np.abs(curvature)

    # 1 = corner, 0 = straight
    labels = (abs_kappa > CORNER_CURVATURE_THRESHOLD).astype(int)
    labels = _merge_short_segments(labels, arc_lengths, MIN_SEGMENT_LENGTH)

    segments: List[TrackSegment] = []
    seg_idx = 0
    i = 0

    while i < n:
        j = i + 1
        while j < n and labels[j] == labels[i]:
            j += 1

        end = min(j - 1, n - 1)
        seg_len   = float(arc_lengths[end] - arc_lengths[i])
        mean_kappa = float(np.mean(curvature[i : j]))
        seg_type  = SegmentType.STRAIGHT if labels[i] == 0 else SegmentType.APEX

        segments.append(TrackSegment(
            index=seg_idx,
            start_idx=i,
            end_idx=end,
            segment_type=seg_type,
            curvature=mean_kappa,
            length=seg_len,
        ))

        i = j
        seg_idx += 1

    return segments


def _merge_short_segments(
    labels: np.ndarray,
    arc_lengths: np.ndarray,
    min_length: float,
) -> np.ndarray:
    """
    Merge label runs shorter than min_length into their predecessor.
    Multiple passes handle cascading short segments.
    """
    labels = labels.copy()
    n = len(labels)

    for _ in range(5):  # up to 5 passes
        changed = False
        i = 0
        while i < n:
            j = i + 1
            while j < n and labels[j] == labels[i]:
                j += 1

            end_idx = min(j - 1, n - 1)
            seg_len = arc_lengths[end_idx] - arc_lengths[i]

            if seg_len < min_length:
                # Absorb into predecessor, or successor if at the start
                new_label = labels[i - 1] if i > 0 else (labels[j] if j < n else labels[i])
                labels[i:j] = new_label
                changed = True

            i = j

        if not changed:
            break

    return labels
