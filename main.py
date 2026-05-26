"""
Motorsport Telemetry System — demo pipeline.

Usage:
    python main.py                    # uses bundled sample data
    python main.py path/to/data.csv   # load your own CSV
"""
import sys
import subprocess
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.stdout.reconfigure(encoding="utf-8")   # allow box-drawing chars on Windows

import numpy as np

from ingestion.csv_loader import CSVIngester
from ingestion.normalizer import detect_coordinate_type, gps_to_local
from track.reconstruction import reconstruct_track, extract_lap_points
from track.geometry import compute_curvature
from analysis.comparator import compare_runs
from optimization.racing_line import compute_racing_line
from optimization.speed_profile import compute_minimum_time_speed_profile
from visualization.comparison_plot import plot_full_dashboard
from core.models import DriverRun

SAMPLE_CSV = Path(__file__).parent / "data" / "sample" / "sample_telemetry.csv"


def load_telemetry(csv_path: Path):
    loader = CSVIngester()
    points = loader.load(str(csv_path))

    if detect_coordinate_type(points) == "gps":
        print("  [normalizer] GPS detected — projecting to local metric coordinates")
        gps_to_local(points)

    warnings = loader.validate(points)
    for w in warnings:
        print(f"  [warn] {w}")

    return points


def main():
    csv_path = Path(sys.argv[1]) if len(sys.argv) > 1 else SAMPLE_CSV

    if csv_path == SAMPLE_CSV and not SAMPLE_CSV.exists():
        print("Generating sample data...")
        SAMPLE_CSV.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            [sys.executable, str(SAMPLE_CSV.parent / "generate_sample.py")],
            check=True,
        )

    print("╔══ Motorsport Telemetry System ══╗")
    print(f"  Source : {csv_path.name}")

    all_points = load_telemetry(csv_path)
    print(f"  Points : {len(all_points)}")

    # Detect laps
    laps = sorted(set(p.lap for p in all_points if p.lap is not None))
    if not laps:
        for p in all_points:
            p.lap = 1
        laps = [1]
    print(f"  Laps   : {laps}")

    # ── track reconstruction ────────────────────────────────────────────
    lap1_pts = extract_lap_points(all_points, laps[0])
    print(f"\n[track] Reconstructing from lap {laps[0]}  ({len(lap1_pts)} pts)...")
    track = reconstruct_track(lap1_pts, name="Sample Circuit", smoothing=8.0)
    print(f"  Length   : {track.total_length:.1f} m")
    print(f"  Segments : {len(track.segments)}")

    seg_types = {}
    for s in track.segments:
        seg_types[s.segment_type.value] = seg_types.get(s.segment_type.value, 0) + 1
    for t, c in seg_types.items():
        print(f"    {t:<18}: {c}")

    # ── driver runs ─────────────────────────────────────────────────────
    runs = []
    for lap_num in laps:
        pts = extract_lap_points(all_points, lap_num)
        run = DriverRun(
            session_id=csv_path.stem,
            driver_name="Driver A",
            lap=lap_num,
            telemetry=pts,
        )
        runs.append(run)
        print(f"  Lap {lap_num}: {len(pts):4d} pts  |  {run.lap_time:.2f}s")

    reference    = runs[0]
    analysis_run = runs[-1] if len(runs) > 1 else runs[0]

    # ── analysis ────────────────────────────────────────────────────────
    print(f"\n[analysis] Lap {analysis_run.lap} vs reference (lap {reference.lap})...")
    analysis = compare_runs(analysis_run, reference, track, all_runs=runs)
    print(f"  Total delta  : {analysis.total_delta:+.3f}s")
    print(f"  Consistency  : {analysis.consistency_score:.3f}")

    worst = max(analysis.segment_deltas, key=lambda d: d.delta)
    best  = min(analysis.segment_deltas, key=lambda d: d.delta)
    print(f"  Worst segment: #{worst.segment_index}  Δ={worst.delta:+.3f}s  "
          f"speed loss={worst.speed_loss:.1f} m/s")
    print(f"  Best  segment: #{best.segment_index}   Δ={best.delta:+.3f}s")

    # ── optimisation ────────────────────────────────────────────────────
    print(f"\n[optim] Computing racing line ({50} iterations)...")
    track_arr  = np.array(track.points)
    racing_line = compute_racing_line(track_arr, half_width=5.0, n_iterations=50)
    kappa_rl    = compute_curvature(racing_line)
    v_opt       = compute_minimum_time_speed_profile(racing_line, kappa_rl)

    print(f"  Min speed : {v_opt.min():.1f} m/s  ({v_opt.min()*3.6:.1f} km/h)")
    print(f"  Max speed : {v_opt.max():.1f} m/s  ({v_opt.max()*3.6:.1f} km/h)")

    # ── visualisation ───────────────────────────────────────────────────
    print(f"\n[viz] Rendering 4-panel dashboard...")
    plot_full_dashboard(
        track=track,
        run=analysis_run,
        reference=reference,
        analysis=analysis,
        racing_line=racing_line,
        show=True,
    )


if __name__ == "__main__":
    main()
