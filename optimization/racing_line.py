"""
Racing line optimisation via minimum-curvature path.

The path is parameterised as:
    P(t) = centerline(t) + offset(t) * normal(t)
where offset(t) ∈ [−half_width, half_width].

We minimise ∫ κ² dt using gradient descent with numerical gradients
and a smoothness regulariser to prevent oscillation.

Reference algorithm: simplified variant of Braghin et al. (2008)
"Race Driver Model", Computer Methods in Applied Mechanics and Engineering.
"""
import numpy as np
from track.geometry import compute_curvature, compute_normals


def compute_racing_line(
    centerline: np.ndarray,
    half_width: float = 5.0,
    n_iterations: int = 200,
    learning_rate: float = 0.15,
    smoothing_weight: float = 0.4,
) -> np.ndarray:
    """
    Compute the minimum-curvature racing line.

    Args:
        centerline:       (N, 2) track centreline points
        half_width:       half the usable track width in metres
        n_iterations:     gradient descent steps
        learning_rate:    initial step size (decayed each iteration)
        smoothing_weight: weight for Laplacian regulariser

    Returns:
        (N, 2) optimised racing line
    """
    normals  = compute_normals(centerline)
    offsets  = np.zeros(len(centerline))  # start on centreline
    lr       = learning_rate

    for _ in range(n_iterations):
        path  = centerline + offsets[:, np.newaxis] * normals
        kappa = compute_curvature(path)
        grad  = _numerical_gradient(centerline, normals, offsets, kappa)

        # Laplacian smoothness: penalise rapid offset changes
        smooth_grad = np.gradient(np.gradient(offsets))

        offsets -= lr * (grad + smoothing_weight * smooth_grad)
        offsets  = np.clip(offsets, -half_width, half_width)
        lr      *= 0.995  # learning rate decay

    return centerline + offsets[:, np.newaxis] * normals


def _numerical_gradient(
    centerline: np.ndarray,
    normals: np.ndarray,
    offsets: np.ndarray,
    kappa: np.ndarray,
    eps: float = 0.1,
) -> np.ndarray:
    """
    Approximate ∂(Σκ²)/∂offset_i via forward finite differences.

    Evaluates every `step` points and interpolates the rest — keeps the
    O(N²) curvature recompute tractable for large N.
    """
    n    = len(offsets)
    grad = np.zeros(n)
    base = float(np.sum(kappa ** 2))

    step = max(1, n // 80)  # evaluate ~80 probes per iteration

    for i in range(0, n, step):
        offsets[i] += eps
        path_p  = centerline + offsets[:, np.newaxis] * normals
        kappa_p = compute_curvature(path_p)
        grad[i] = (float(np.sum(kappa_p ** 2)) - base) / eps
        offsets[i] -= eps

    if step > 1:
        computed = np.arange(0, n, step)
        grad     = np.interp(np.arange(n), computed, grad[computed])

    return grad
