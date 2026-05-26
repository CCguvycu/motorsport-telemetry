import csv
from pathlib import Path
from typing import Dict, List, Optional
from core.models import TelemetryPoint
from core.schema import FIELD_ALIASES, SPEED_UNIT_HINTS, REQUIRED_FIELDS
from ingestion.base import BaseIngester


class CSVIngester(BaseIngester):
    """
    Load telemetry from CSV files.

    Handles diverse column naming via FIELD_ALIASES (MoTeC, iRacing, AC, OBD-II).
    Auto-detects km/h or mph columns and converts to m/s.
    Silently skips rows with missing required values rather than raising on each.
    """

    def load(self, source: str) -> List[TelemetryPoint]:
        path = Path(source)
        if not path.exists():
            raise FileNotFoundError(f"Telemetry file not found: {source}")

        with open(path, newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            headers = list(reader.fieldnames or [])
            mapping = self._build_field_mapping(headers)

            missing = REQUIRED_FIELDS - set(mapping.keys())
            if missing:
                raise ValueError(
                    f"CSV missing required fields {missing}.  "
                    f"Found headers: {headers}"
                )

            speed_scale = self._detect_speed_scale(mapping.get("speed", ""))
            points: List[TelemetryPoint] = []

            for row_num, row in enumerate(reader, start=2):
                try:
                    pt = self._parse_row(row, mapping, speed_scale)
                    if pt is not None:
                        points.append(pt)
                except (ValueError, KeyError) as exc:
                    raise ValueError(f"Row {row_num}: {exc}") from exc

        points.sort(key=lambda p: p.timestamp)
        return points

    # ------------------------------------------------------------------ helpers

    def _build_field_mapping(self, headers: List[str]) -> Dict[str, str]:
        """Return {canonical_name: actual_csv_header} using alias matching."""
        lower_to_orig = {h.lower(): h for h in headers}
        mapping: Dict[str, str] = {}
        for canonical, aliases in FIELD_ALIASES.items():
            for alias in aliases:
                if alias.lower() in lower_to_orig:
                    mapping[canonical] = lower_to_orig[alias.lower()]
                    break
        return mapping

    def _detect_speed_scale(self, speed_col: str) -> float:
        """Return scale factor to convert the speed column to m/s."""
        for hint, scale in SPEED_UNIT_HINTS.items():
            if hint.lower() in speed_col.lower():
                return scale
        return 1.0  # assume m/s by default

    def _parse_row(
        self,
        row: Dict[str, str],
        mapping: Dict[str, str],
        speed_scale: float,
    ) -> Optional[TelemetryPoint]:

        def fval(field: str) -> Optional[float]:
            col = mapping.get(field)
            if col is None:
                return None
            raw = row.get(col, "").strip()
            return float(raw) if raw else None

        def ival(field: str) -> Optional[int]:
            v = fval(field)
            return int(v) if v is not None else None

        ts    = fval("timestamp")
        x     = fval("x")
        y     = fval("y")
        speed = fval("speed")

        if any(v is None for v in (ts, x, y, speed)):
            return None  # skip incomplete rows silently

        return TelemetryPoint(
            timestamp=ts,
            x=x,
            y=y,
            speed=max(0.0, speed * speed_scale),
            acceleration=fval("acceleration"),
            throttle=self._clamp01(fval("throttle")),
            brake=self._clamp01(fval("brake")),
            steering=fval("steering"),
            gear=ival("gear"),
            lap=ival("lap"),
        )

    @staticmethod
    def _clamp01(val: Optional[float]) -> Optional[float]:
        if val is None:
            return None
        return max(0.0, min(1.0, val))
