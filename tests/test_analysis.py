import pytest
from core.models import TelemetryPoint, DriverRun, Track, TrackSegment, SegmentType
from analysis.metrics import (
    segment_time,
    segment_avg_speed,
    speed_heatmap,
    compute_consistency_score,
)


def _pts(n=20, speed=20.0, t_start=0.0, x_start=0.0):
    return [
        TelemetryPoint(
            timestamp=t_start + i * 0.1,
            x=x_start + float(i),
            y=0.0,
            speed=speed,
            throttle=0.8,
            brake=0.0,
        )
        for i in range(n)
    ]


def _run(name="Driver", speed=20.0, lap=1):
    return DriverRun(session_id="s1", driver_name=name, lap=lap, telemetry=_pts(speed=speed))


# ── segment_time ──────────────────────────────────────────────────────────

def test_segment_time_basic():
    pts = _pts(n=10, t_start=5.0)
    assert abs(segment_time(pts) - 0.9) < 0.001


def test_segment_time_single_point():
    assert segment_time([_pts(n=1)[0]]) == 0.0


# ── segment_avg_speed ─────────────────────────────────────────────────────

def test_segment_avg_speed():
    pts = _pts(n=10, speed=30.0)
    assert segment_avg_speed(pts) == pytest.approx(30.0)


def test_segment_avg_speed_empty():
    assert segment_avg_speed([]) == 0.0


# ── speed_heatmap ─────────────────────────────────────────────────────────

def test_speed_heatmap_range():
    run = _run(speed=20.0)
    hm  = speed_heatmap(run)
    assert len(hm) == 20
    assert all(0.0 <= v <= 1.0 for v in hm)


def test_speed_heatmap_constant_speed():
    run = _run(speed=15.0)
    hm  = speed_heatmap(run)
    assert all(abs(v - 0.5) < 1e-9 for v in hm)


def test_speed_heatmap_min_max():
    from core.models import TelemetryPoint
    pts = [
        TelemetryPoint(timestamp=0.0, x=0.0, y=0.0, speed=10.0),
        TelemetryPoint(timestamp=0.1, x=1.0, y=0.0, speed=20.0),
        TelemetryPoint(timestamp=0.2, x=2.0, y=0.0, speed=30.0),
    ]
    run = DriverRun(session_id="s", driver_name="X", lap=1, telemetry=pts)
    hm  = speed_heatmap(run)
    assert hm[0]  == pytest.approx(0.0)
    assert hm[-1] == pytest.approx(1.0)


# ── consistency_score ─────────────────────────────────────────────────────

def test_consistency_single_run():
    assert compute_consistency_score([_run()]) == pytest.approx(1.0)


def test_consistency_identical_runs():
    runs = [_run(speed=20.0), _run(speed=20.0)]
    assert compute_consistency_score(runs) == pytest.approx(1.0)


def test_consistency_decreases_with_variance():
    from core.models import TelemetryPoint
    def make_run(lap_time):
        pts = [
            TelemetryPoint(timestamp=0.0,      x=0.0, y=0.0, speed=20.0),
            TelemetryPoint(timestamp=lap_time, x=1.0, y=0.0, speed=20.0),
        ]
        return DriverRun(session_id="s", driver_name="X", lap=1, telemetry=pts)

    consistent    = [make_run(40.0), make_run(40.0)]
    inconsistent  = [make_run(30.0), make_run(50.0)]
    assert compute_consistency_score(consistent) > compute_consistency_score(inconsistent)
