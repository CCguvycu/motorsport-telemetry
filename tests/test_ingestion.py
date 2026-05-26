import csv
import os
import tempfile
import pytest
from ingestion.csv_loader import CSVIngester


def _csv(headers, rows):
    f = tempfile.NamedTemporaryFile(
        mode="w", suffix=".csv", newline="", delete=False, encoding="utf-8"
    )
    writer = csv.DictWriter(f, fieldnames=headers)
    writer.writeheader()
    writer.writerows(rows)
    f.close()
    return f.name


def test_load_basic_csv():
    path = _csv(
        ["timestamp", "x", "y", "speed"],
        [
            {"timestamp": "0.0", "x": "0.0",  "y": "0.0", "speed": "10.0"},
            {"timestamp": "0.1", "x": "1.0",  "y": "0.5", "speed": "11.0"},
        ],
    )
    try:
        pts = CSVIngester().load(path)
        assert len(pts) == 2
        assert pts[0].speed == pytest.approx(10.0)
        assert pts[1].x    == pytest.approx(1.0)
    finally:
        os.unlink(path)


def test_load_speed_kmh_converts_to_ms():
    path = _csv(
        ["timestamp", "x", "y", "speed_kmh"],
        [{"timestamp": "0.0", "x": "0.0", "y": "0.0", "speed_kmh": "72.0"}],
    )
    try:
        pts = CSVIngester().load(path)
        assert abs(pts[0].speed - 20.0) < 0.01  # 72 km/h = 20 m/s
    finally:
        os.unlink(path)


def test_missing_required_field_raises():
    path = _csv(
        ["timestamp", "x", "speed"],  # missing 'y'
        [{"timestamp": "0.0", "x": "0.0", "speed": "10.0"}],
    )
    try:
        with pytest.raises(ValueError, match="missing required fields"):
            CSVIngester().load(path)
    finally:
        os.unlink(path)


def test_alias_column_names():
    path = _csv(
        ["time", "longitude", "latitude", "vCar"],
        [{"time": "1.0", "longitude": "5.0", "latitude": "3.0", "vCar": "15.0"}],
    )
    try:
        pts = CSVIngester().load(path)
        assert pts[0].x     == pytest.approx(5.0)
        assert pts[0].y     == pytest.approx(3.0)
        assert pts[0].speed == pytest.approx(15.0)
    finally:
        os.unlink(path)


def test_throttle_clamped_above_1():
    path = _csv(
        ["timestamp", "x", "y", "speed", "throttle"],
        [{"timestamp": "0.0", "x": "0.0", "y": "0.0", "speed": "10.0", "throttle": "1.8"}],
    )
    try:
        pts = CSVIngester().load(path)
        assert pts[0].throttle == pytest.approx(1.0)
    finally:
        os.unlink(path)


def test_file_not_found_raises():
    with pytest.raises(FileNotFoundError):
        CSVIngester().load("does_not_exist.csv")


def test_incomplete_rows_skipped():
    path = _csv(
        ["timestamp", "x", "y", "speed"],
        [
            {"timestamp": "0.0", "x": "0.0", "y": "0.0", "speed": "10.0"},
            {"timestamp": "0.1", "x": "",    "y": "0.0", "speed": "11.0"},  # missing x
        ],
    )
    try:
        pts = CSVIngester().load(path)
        assert len(pts) == 1
    finally:
        os.unlink(path)
