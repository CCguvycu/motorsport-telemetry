from abc import ABC, abstractmethod
from typing import List
from core.models import TelemetryPoint


class BaseIngester(ABC):
    """Abstract base for all telemetry data ingesters."""

    @abstractmethod
    def load(self, source: str) -> List[TelemetryPoint]:
        """
        Load telemetry from source and return normalized, time-sorted TelemetryPoints.

        Args:
            source: file path, serial port, or URL depending on concrete ingester.

        Raises:
            ValueError: missing required fields or malformed data.
            FileNotFoundError: source path does not exist.
        """
        ...

    def validate(self, points: List[TelemetryPoint]) -> List[str]:
        """
        Sanity-check a loaded point list.  Returns warning strings (empty = clean).
        Does not raise — callers decide whether warnings are fatal.
        """
        warnings: List[str] = []

        if not points:
            return ["Dataset is empty"]

        # Temporal monotonicity
        for i in range(1, len(points)):
            if points[i].timestamp <= points[i - 1].timestamp:
                warnings.append(
                    f"Non-monotonic timestamp at index {i}: "
                    f"{points[i].timestamp} <= {points[i-1].timestamp}"
                )
                break

        # Physics sanity: 120 m/s ≈ 432 km/h (reasonable hard cap)
        MAX_SPEED = 120.0
        spikes = [i for i, p in enumerate(points) if p.speed > MAX_SPEED]
        if spikes:
            warnings.append(
                f"Speed > {MAX_SPEED} m/s at {len(spikes)} samples "
                f"(first at index {spikes[0]})"
            )

        # Coordinate spread — catches unit errors or static GPS
        xs = [p.x for p in points]
        ys = [p.y for p in points]
        if max(xs) - min(xs) < 1.0 or max(ys) - min(ys) < 1.0:
            warnings.append(
                "Coordinate spread < 1 unit — possible GPS noise or wrong units"
            )

        return warnings
