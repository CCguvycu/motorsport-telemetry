"""
Generate synthetic telemetry CSV for a simplified oval-ish circuit.

Layout (top view):
  ─────────────────────────────
  Corner 2 ←  Straight 2  ← Corner 1
  (left)                      (right)
  Corner 2 →  Straight 1  → Corner 1
  ─────────────────────────────

  Straight length : 200 m
  Corner radius   : 75 m  (semicircle)
  Lap distance    : ~871 m
  Sample rate     : 50 Hz  (20 ms)
  Output          : 3 laps of data
"""
import csv
import math
import os
import random


GRAVITY    = 9.81
MU         = 1.1        # tyre friction
MAX_SPEED  = 60.0       # m/s cap (~216 km/h)
STRAIGHT_L = 200.0      # metres
CORNER_R   = 75.0       # metres
SAMPLE_HZ  = 50         # samples per second (used only for the CSV note)


# ── circuit geometry ──────────────────────────────────────────────────────

def build_circuit():
    """
    Return list of (x, y, curvature) for one closed lap.
    Curvature is signed (1/m); 0 on straights.
    """
    pts = []

    # Straight 1: (0,0) → (200, 0)  heading east
    n_s = 200
    for i in range(n_s + 1):
        pts.append((float(i), 0.0, 0.0))

    # Corner 1: right semicircle, centre=(200,75), angles -90° → +90°
    n_c = 157  # ≈ π*75 / 1.5  (≈1.5 m steps)
    cx, cy = STRAIGHT_L, CORNER_R
    for i in range(1, n_c + 1):
        a = -math.pi / 2 + math.pi * i / n_c
        pts.append((cx + CORNER_R * math.cos(a), cy + CORNER_R * math.sin(a),
                    1.0 / CORNER_R))

    # Straight 2: (200,150) → (0, 150)  heading west
    for i in range(1, n_s + 1):
        pts.append((float(STRAIGHT_L - i), 150.0, 0.0))

    # Corner 2: left semicircle, centre=(0,75), angles +90° → +270°
    cx, cy = 0.0, CORNER_R
    for i in range(1, n_c + 1):
        a = math.pi / 2 + math.pi * i / n_c
        pts.append((cx + CORNER_R * math.cos(a), cy + CORNER_R * math.sin(a),
                    1.0 / CORNER_R))

    return pts


def arc_lengths(pts):
    s = [0.0]
    for i in range(1, len(pts)):
        dx = pts[i][0] - pts[i - 1][0]
        dy = pts[i][1] - pts[i - 1][1]
        s.append(s[-1] + math.hypot(dx, dy))
    return s


# ── speed profile ─────────────────────────────────────────────────────────

def compute_speed_profile(pts, s):
    n = len(pts)
    a_max = MU * GRAVITY

    v_lim = []
    for k in (abs(p[2]) for p in pts):
        v_lim.append(min(MAX_SPEED, math.sqrt(MU * GRAVITY / k) if k > 1e-4 else MAX_SPEED))

    v = v_lim[:]

    # Forward pass (braking)
    for i in range(1, n):
        ds = s[i] - s[i - 1]
        v[i] = min(v[i], math.sqrt(v[i - 1] ** 2 + 2 * a_max * ds))

    # Backward pass (acceleration)
    for i in range(n - 2, -1, -1):
        ds = s[i + 1] - s[i]
        v[i] = min(v[i], math.sqrt(v[i + 1] ** 2 + 2 * a_max * ds))

    return v


# ── telemetry generation ──────────────────────────────────────────────────

def generate_lap(pts, speeds, s, lap_num, noise_seed, t_offset=0.0):
    rng = random.Random(noise_seed)
    rows = []
    t = t_offset

    for i, (wp, v) in enumerate(zip(pts, speeds)):
        if i > 0:
            ds = s[i] - s[i - 1]
            avg_v = (speeds[i] + speeds[i - 1]) / 2 + 1e-6
            t += ds / avg_v

        # Estimate pedal inputs from acceleration
        dv_next = (speeds[i + 1] - v) if i < len(speeds) - 1 else 0.0
        ds_next = (s[i + 1] - s[i]) if i < len(s) - 1 else 1.0
        accel   = dv_next / (ds_next / (v + 1e-6))

        throttle = max(0.0, min(1.0,  accel / (MU * GRAVITY) * 0.85 + rng.gauss(0, 0.02)))
        brake    = max(0.0, min(1.0, -accel / (MU * GRAVITY) * 0.90 + rng.gauss(0, 0.02)))

        kappa = abs(wp[2])
        steer = (math.degrees(math.atan(1.6 * kappa)) * (1 if wp[2] >= 0 else -1)
                 + rng.gauss(0, 0.3))

        # Small positional noise to simulate GPS scatter
        x = wp[0] + rng.gauss(0, 0.08)
        y = wp[1] + rng.gauss(0, 0.08)

        # Lap-to-lap speed variation
        v_noisy = max(0.0, v * (1 + rng.gauss(0, 0.008)))

        rows.append({
            "timestamp":   round(t, 4),
            "x":           round(x, 4),
            "y":           round(y, 4),
            "speed_kmh":   round(v_noisy * 3.6, 3),
            "acceleration":round(accel, 4),
            "throttle":    round(throttle, 3),
            "brake":       round(brake, 3),
            "steering":    round(steer, 3),
            "gear":        _gear(v_noisy),
            "lap":         lap_num,
        })

    return rows, t


def _gear(v_ms):
    kmh = v_ms * 3.6
    if kmh < 50:  return 2
    if kmh < 90:  return 3
    if kmh < 130: return 4
    if kmh < 180: return 5
    return 6


# ── main ──────────────────────────────────────────────────────────────────

def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    out_path   = os.path.join(script_dir, "sample_telemetry.csv")

    circuit = build_circuit()
    s       = arc_lengths(circuit)
    speeds  = compute_speed_profile(circuit, s)

    fields = ["timestamp", "x", "y", "speed_kmh", "acceleration",
              "throttle", "brake", "steering", "gear", "lap"]

    all_rows = []
    t_offset = 0.0

    for lap in range(1, 4):
        lap_rows, t_end = generate_lap(circuit, speeds, s, lap,
                                        noise_seed=lap * 17, t_offset=t_offset)
        all_rows.extend(lap_rows)
        t_offset = t_end + 0.5  # 0.5s gap between laps

    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(all_rows)

    n_pts    = len(circuit)
    lap_time = all_rows[n_pts - 1]["timestamp"] - all_rows[0]["timestamp"]
    print(f"Generated {len(all_rows)} rows -> {out_path}")
    print(f"Circuit: {s[-1]:.1f} m  |  3 laps  |  Approx lap time: {lap_time:.2f}s")
    print(f"Max speed: {max(v * 3.6 for v in speeds):.1f} km/h  "
          f"Min speed: {min(v * 3.6 for v in speeds):.1f} km/h")


if __name__ == "__main__":
    main()
