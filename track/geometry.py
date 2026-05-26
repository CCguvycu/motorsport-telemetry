"""
Core geometric operations for track reconstruction.

All public functions accept and return numpy arrays.
"""
import numpy as np
from typing import Tuple


def arc_length(points: np.ndarray) -> np.ndarray:
    """
    Cumulative arc length along a polyline.

    Args:
        points: (N, 2) array of (x, y) coordinates

    Returns:
        (N,) array, starts at 0.0, monotonically increasing
    """
    diffs = np.diff(points, axis=0)
    seg_len = np.hypot(diffs[:, 0], diffs[:, 1])
    return np.concatenate([[0.0], np.cumsum(seg_len)])


def smooth_path(points: np.ndarray, smoothing: float = 5.0) -> np.ndarray:
    """
    Smooth a path using parametric B-spline interpolation.

    Higher smoothing values trade accuracy for smoothness (reduces sensor noise).

    Args:
        points: (N, 2) input path
        smoothing: spline smoothing factor passed to scipy splprep

    Returns:
        (N, 2) smoothed path evaluated at same arc-length parameter values
    """
    from scipy.interpolate import splprep, splev

    s = arc_length(points)
    u = s / s[-1]  # normalise to [0, 1]

    # Remove duplicate parameter values which cause splprep to fail
    _, unique = np.unique(u, return_index=True)
    u_clean = u[unique]
    pts_clean = points[unique]

    tck, _ = splprep(
        [pts_clean[:, 0], pts_clean[:, 1]],
        u=u_clean,
        s=smoothing,
        per=False,
        k=min(3, len(u_clean) - 1),
    )
    xs, ys = splev(u, tck)
    return np.column_stack([xs, ys])


def compute_curvature(points: np.ndarray) -> np.ndarray:
    """
    Signed curvature κ at each point via central finite differences.

    κ = (x′y″ − y′x″) / (x′² + y′²)^(3/2)

    Positive κ → left turn, negative κ → right turn.
    Endpoints use first-order one-sided differences (less accurate).

    Args:
        points: (N, 2) smoothed path

    Returns:
        (N,) curvature in 1/m
    """
    dx  = np.gradient(points[:, 0])
    dy  = np.gradient(points[:, 1])
    ddx = np.gradient(dx)
    ddy = np.gradient(dy)

    num   = dx * ddy - dy * ddx
    denom = (dx ** 2 + dy ** 2) ** 1.5

    with np.errstate(divide="ignore", invalid="ignore"):
        kappa = np.where(denom > 1e-10, num / denom, 0.0)

    return kappa


def compute_normals(points: np.ndarray) -> np.ndarray:
    """
    Unit normal vectors pointing left of the travel direction.

    Args:
        points: (N, 2) path array

    Returns:
        (N, 2) unit normals  (−dy, dx) / ‖…‖
    """
    dx = np.gradient(points[:, 0])
    dy = np.gradient(points[:, 1])
    mag = np.hypot(dx, dy)
    mag = np.where(mag < 1e-10, 1.0, mag)
    return np.column_stack([-dy / mag, dx / mag])


def resample_path(points: np.ndarray, n_points: int) -> np.ndarray:
    """
    Resample a path to exactly n_points with uniform arc-length spacing.

    Args:
        points: (N, 2) input path
        n_points: desired output count

    Returns:
        (n_points, 2) resampled path
    """
    from scipy.interpolate import interp1d

    s = arc_length(points)
    s_uniform = np.linspace(0.0, s[-1], n_points)
    fx = interp1d(s, points[:, 0], kind="linear")
    fy = interp1d(s, points[:, 1], kind="linear")
    return np.column_stack([fx(s_uniform), fy(s_uniform)])
