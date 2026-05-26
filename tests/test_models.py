import pytest
from core.models import TelemetryPoint, Track, DriverRun, TrackSegment, SegmentType


def _pt(ts=0.0, x=0.0, y=0.0, speed=10.0, **kw):
    return TelemetryPoint(timestamp=ts, x=x, y=y, speed=speed, **kw)


def test_telemetry_point_valid():
    p = _pt(speed=20.0, throttle=0.5, brake=0.2)
    assert p.speed == 20.0
    assert p.throttle == 0.5


def test_negative_speed_rejected():
    with pytest.raises(ValueError):
        _pt(speed=-1.0)


def test_throttle_above_1_rejected():
    with pytest.raises(ValueError):
        _pt(throttle=1.1)


def test_brake_below_0_rejected():
    with pytest.raises(ValueError):
        _pt(brake=-0.01)


def test_track_xy_property():
    track = Track(
        name="T",
        points=[(0.0, 0.0), (1.0, 0.0), (1.0, 1.0)],
        curvature=[0.0, 0.0, 0.1],
        segments=[],
        total_length=2.0,
    )
    xs, ys = track.xy
    assert xs == [0.0, 1.0, 1.0]
    assert ys == [0.0, 0.0, 1.0]


def test_track_empty_xy():
    track = Track(name="T", points=[], curvature=[], segments=[], total_length=0.0)
    xs, ys = track.xy
    assert xs == [] and ys == []


def test_driver_run_auto_lap_time():
    pts = [_pt(ts=float(i)) for i in range(10)]
    run = DriverRun(session_id="s1", driver_name="Alice", lap=1, telemetry=pts)
    assert run.lap_time == pytest.approx(9.0)


def test_driver_run_explicit_lap_time():
    pts = [_pt(ts=float(i)) for i in range(5)]
    run = DriverRun(session_id="s1", driver_name="Bob", lap=1,
                    telemetry=pts, lap_time=42.0)
    assert run.lap_time == 42.0


def test_driver_run_empty_telemetry():
    with pytest.raises(ValueError):
        DriverRun(session_id="s1", driver_name="Alice", lap=1, telemetry=[])
