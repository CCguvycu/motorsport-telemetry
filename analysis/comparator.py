"""
High-level driver comparison interface.
"""
from typing import List, Optional
from core.models import DriverRun, Track, AnalysisResult
from analysis.metrics import (
    compute_segment_deltas,
    compute_consistency_score,
    speed_heatmap,
)


def compare_runs(
    run: DriverRun,
    reference: DriverRun,
    track: Track,
    all_runs: Optional[List[DriverRun]] = None,
) -> AnalysisResult:
    """
    Compare a driver run against a reference lap.

    Args:
        run:       the lap being analysed
        reference: the benchmark lap (e.g., session best)
        track:     reconstructed track geometry
        all_runs:  full list of laps for consistency scoring (optional)

    Returns:
        AnalysisResult with segment deltas, total delta, consistency, heatmap
    """
    segment_deltas, total_delta = compute_segment_deltas(run, reference, track)

    consistency = compute_consistency_score(
        all_runs if all_runs is not None else [run]
    )

    heatmap = speed_heatmap(run)

    return AnalysisResult(
        run=run,
        reference_run=reference,
        segment_deltas=segment_deltas,
        total_delta=total_delta,
        consistency_score=consistency,
        heatmap_values=heatmap,
    )
