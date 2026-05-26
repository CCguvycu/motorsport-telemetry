"""
Theoretical minimum-time speed profile.

Uses the friction circle model with a 3-pass algorithm:
  1. Corner speed limits:  v_corner = √(μ_lat · g / |κ|)
  2. Forward pass:         limit entry speed by braking capability
  3. Backward pass:        limit exit speed by acceleration capability

This is mathematically equivalent to the method described in:
  Rucco, Notarstefano, Hauser — "An efficient minimum-lap-time formulation
  for autonomous vehicles" (2015).
"""
import numpy as np
from track.geometry import arc_length

GRAVITY    = 9.81   # m/s²
MU_LATERAL = 1.2    # lateral tyre friction  (racing slick on dry)
MU_LONG    = 1.1    # longitudinal tyre friction
MAX_SPEED  = 80.0   # m/s hard cap (~288 km/h)


def compute_minimum_time_speed_profile(
    path: np.ndarray,
    curvature: np.ndarray,
    v_initial: float = 0.0,
    mu_lateral: float = MU_LATERAL,
    mu_long: float = MU_LONG,
) -> np.ndarray:
    """
    Compute the theoretical minimum-time speed profile along a path.

    Args:
        path:       (N, 2) racing line (or any path)
        curvature:  (N,) signed curvature in 1/m
        v_initial:  entry speed in m/s (0 = unrestricted)
        mu_lateral: lateral friction coefficient
        mu_long:    longitudinal friction coefficient

    Returns:
        (N,) optimal speed profile in m/s
    """
    n       = len(path)
    s       = arc_length(path)
    ds      = np.diff(s)
    abs_kap = np.abs(curvature)
    a_max   = mu_long * GRAVITY

    # --- pass 1: corner speed limits from lateral g ---
    with np.errstate(divide="ignore", invalid="ignore"):
        v_corner = np.where(
            abs_kap > 1e-4,
            np.sqrt(mu_lateral * GRAVITY / abs_kap),
            MAX_SPEED,
        )
    v_corner = np.clip(v_corner, 0.0, MAX_SPEED)

    # --- pass 2: forward — entry speed limited by braking ---
    v_fwd    = v_corner.copy()
    v_fwd[0] = min(v_fwd[0], v_initial) if v_initial > 0 else v_fwd[0]

    for i in range(1, n):
        d         = ds[i - 1]
        v_reach   = min(np.sqrt(v_fwd[i - 1] ** 2 + 2 * a_max * d), MAX_SPEED)
        v_fwd[i]  = min(v_corner[i], v_reach)

    # --- pass 3: backward — exit speed limited by acceleration ---
    v_opt = v_fwd.copy()

    for i in range(n - 2, -1, -1):
        d         = ds[i]
        v_reach   = min(np.sqrt(v_opt[i + 1] ** 2 + 2 * a_max * d), MAX_SPEED)
        v_opt[i]  = min(v_opt[i], v_reach)

    return v_opt
