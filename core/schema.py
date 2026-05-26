"""
Field alias mappings for normalizing diverse telemetry input formats
into the canonical TelemetryPoint schema.

Each key is a canonical field name; values are case-insensitive aliases
found in real-world telemetry software output (MoTeC, iRacing, AC, OBD-II).
"""
from typing import Dict, List

FIELD_ALIASES: Dict[str, List[str]] = {
    "timestamp": [
        "timestamp", "time", "time_s", "t", "elapsed",
        "session_time", "laptime", "Time",
    ],
    "x": [
        "x", "longitude", "lon", "lng", "pos_x",
        "gps_lon", "WorldPosition_x", "Longitude",
    ],
    "y": [
        "y", "latitude", "lat", "pos_y",
        "gps_lat", "WorldPosition_z", "Latitude",
    ],
    "speed": [
        "speed", "velocity", "spd", "speed_ms", "speed_kmh",
        "speed_mph", "vcar", "SpeedKmh", "v", "Speed",
    ],
    "acceleration": [
        "acceleration", "accel", "acc", "alon", "longitudinal_g",
        "accG", "acc_lon", "g_lon", "AccG",
    ],
    "throttle": [
        "throttle", "throttle_pos", "tps", "gas", "throttlepos",
        "throttle_pct", "Gas", "ThrottleRaw",
    ],
    "brake": [
        "brake", "brake_pos", "brake_pressure", "brakepos",
        "brake_pct", "Brake", "brake_bar", "BrakeRaw",
    ],
    "steering": [
        "steering", "steer", "steering_angle", "steerangle",
        "SteerAngle", "steering_deg", "Steer",
    ],
    "gear": [
        "gear", "currentgear", "gearpos", "CurrentGear",
        "Gear", "gear_num",
    ],
    "lap": [
        "lap", "lap_number", "lapnumber", "currentlap",
        "CurrentLap", "lap_num", "Lap",
    ],
}

# Columns whose names imply non-SI speed units → scale factor to m/s
SPEED_UNIT_HINTS: Dict[str, float] = {
    "speed_kmh": 1.0 / 3.6,
    "speedkmh":  1.0 / 3.6,
    "SpeedKmh":  1.0 / 3.6,
    "speed_mph": 0.44704,
    "speedmph":  0.44704,
}

REQUIRED_FIELDS = frozenset({"timestamp", "x", "y", "speed"})
OPTIONAL_FIELDS = frozenset({"acceleration", "throttle", "brake", "steering", "gear", "lap"})
ALL_FIELDS = REQUIRED_FIELDS | OPTIONAL_FIELDS
