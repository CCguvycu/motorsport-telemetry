from dataclasses import dataclass
from typing import Optional, List, Tuple
from enum import Enum


@dataclass
class TelemetryPoint:
    """Normalized internal representation of a single telemetry sample."""
    timestamp: float        # seconds from session start
    x: float               # x coordinate (meters, track-local or projected lon)
    y: float               # y coordinate (meters, track-local or projected lat)
    speed: float           # m/s
    acceleration: Optional[float] = None  # longitudinal m/s²
    throttle: Optional[float] = None      # 0.0–1.0
    brake: Optional[float] = None         # 0.0–1.0
    steering: Optional[float] = None      # degrees, positive = left
    gear: Optional[int] = None
    lap: Optional[int] = None

    def __post_init__(self):
        if self.speed < 0:
            raise ValueError(f"Speed must be non-negative, got {self.speed}")
        if self.throttle is not None and not (0.0 <= self.throttle <= 1.0):
            raise ValueError(f"Throttle must be in [0,1], got {self.throttle}")
        if self.brake is not None and not (0.0 <= self.brake <= 1.0):
            raise ValueError(f"Brake must be in [0,1], got {self.brake}")


class SegmentType(Enum):
    STRAIGHT = "straight"
    CORNER_ENTRY = "corner_entry"
    APEX = "apex"
    CORNER_EXIT = "corner_exit"
    BRAKING = "braking"
    ACCELERATION = "acceleration"


@dataclass
class TrackSegment:
    """A classified, contiguous portion of the track."""
    index: int
    start_idx: int          # index into Track.points
    end_idx: int
    segment_type: SegmentType
    curvature: float        # mean signed curvature (1/m); |κ| = 1/radius
    length: float           # arc length in meters
    avg_speed: Optional[float] = None  # m/s, populated during analysis


@dataclass
class Track:
    """Reconstructed track geometry derived from a telemetry stream."""
    name: str
    points: List[Tuple[float, float]]  # (x, y) polyline
    curvature: List[float]             # signed curvature per point (1/m)
    segments: List[TrackSegment]
    total_length: float                # meters

    @property
    def xy(self) -> Tuple[List[float], List[float]]:
        if not self.points:
            return [], []
        xs, ys = zip(*self.points)
        return list(xs), list(ys)


@dataclass
class DriverRun:
    """A single driver session lap."""
    session_id: str
    driver_name: str
    lap: int
    telemetry: List[TelemetryPoint]
    lap_time: Optional[float] = None  # seconds

    def __post_init__(self):
        if not self.telemetry:
            raise ValueError("DriverRun must contain at least one telemetry point")
        if self.lap_time is None and len(self.telemetry) >= 2:
            self.lap_time = (
                self.telemetry[-1].timestamp - self.telemetry[0].timestamp
            )


@dataclass
class SegmentDelta:
    """Time delta between a driver and reference for one track segment."""
    segment_index: int
    actual_time: float    # seconds driver spent in segment
    reference_time: float # seconds reference spent in segment
    delta: float          # actual - reference  (positive = slower)
    speed_loss: float     # reference_avg_speed - actual_avg_speed  (m/s)


@dataclass
class AnalysisResult:
    """Full comparison result of a driver run against a reference lap."""
    run: DriverRun
    reference_run: DriverRun
    segment_deltas: List[SegmentDelta]
    total_delta: float       # cumulative delta (s)
    consistency_score: float # 0.0–1.0  (1.0 = perfect consistency across laps)
    heatmap_values: List[float]  # per telemetry point, normalized 0.0–1.0
