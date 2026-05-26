import numpy as np
import pytest
from track.geometry import arc_length, compute_curvature, compute_normals, resample_path


def make_straight(n=100, length=100.0):
    return np.column_stack([np.linspace(0, length, n), np.zeros(n)])


def make_circle(n=500, radius=50.0):
    t = np.linspace(0, 2 * np.pi, n, endpoint=False)
    return np.column_stack([radius * np.cos(t), radius * np.sin(t)])


# ── arc_length ─────────────────────────────────────────────────────────────

def test_arc_length_starts_at_zero():
    pts = make_straight()
    assert arc_length(pts)[0] == 0.0


def test_arc_length_straight():
    pts = make_straight(n=11, length=100.0)
    s = arc_length(pts)
    assert abs(s[-1] - 100.0) < 0.01


def test_arc_length_circle():
    pts = make_circle(n=1000, radius=50.0)
    s = arc_length(pts)
    assert abs(s[-1] - 2 * np.pi * 50.0) < 1.0


# ── curvature ──────────────────────────────────────────────────────────────

def test_curvature_straight_is_zero():
    pts = make_straight(n=100)
    kappa = compute_curvature(pts)
    assert np.allclose(kappa, 0.0, atol=1e-10)


def test_curvature_circle_magnitude():
    pts = make_circle(n=500, radius=50.0)
    kappa = compute_curvature(pts)
    interior = np.abs(kappa[50:-50])
    assert abs(interior.mean() - 0.02) < 0.005  # 1/50 = 0.02


def test_curvature_sign_left_turn():
    pts = make_circle(n=200, radius=30.0)
    kappa = compute_curvature(pts)
    assert np.mean(kappa[10:-10]) > 0  # counter-clockwise = positive


# ── normals ────────────────────────────────────────────────────────────────

def test_normals_unit_length():
    pts = make_circle(n=100)
    norms = compute_normals(pts)
    lengths = np.linalg.norm(norms, axis=1)
    assert np.allclose(lengths, 1.0, atol=1e-6)


def test_normals_perpendicular_to_path():
    pts = make_straight(n=50)
    norms = compute_normals(pts)
    dx = np.gradient(pts[:, 0])
    dy = np.gradient(pts[:, 1])
    tangents = np.column_stack([dx, dy])
    dot = np.einsum("ij,ij->i", norms[5:-5], tangents[5:-5])
    assert np.allclose(dot, 0.0, atol=1e-6)


# ── resample ───────────────────────────────────────────────────────────────

def test_resample_output_shape():
    pts = make_straight(n=50, length=100.0)
    out = resample_path(pts, 100)
    assert out.shape == (100, 2)


def test_resample_preserves_length():
    pts = make_straight(n=50, length=100.0)
    out = resample_path(pts, 200)
    s = arc_length(out)
    assert abs(s[-1] - 100.0) < 0.5
