"""
2D top-down track visualisation utilities.
"""
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
import numpy as np
from typing import Optional, Tuple
from core.models import Track, DriverRun, AnalysisResult


def plot_track(
    track: Track,
    title: str = "Track Map",
    ax: Optional[plt.Axes] = None,
    show: bool = True,
) -> plt.Figure:
    """Render the reconstructed track centreline."""
    fig, ax = _get_ax(ax)
    xs, ys = track.xy
    ax.plot(xs, ys, "w-", linewidth=2, label="Centreline")
    ax.plot(xs[0], ys[0], "go", markersize=10, label="Start", zorder=5)
    ax.set_aspect("equal")
    _style_dark(fig, ax, title)
    ax.legend(facecolor="#1a1a2e", edgecolor="#333355", labelcolor="white")
    if show:
        plt.tight_layout()
        plt.show()
    return fig


def plot_speed_heatmap(
    run: DriverRun,
    analysis: AnalysisResult,
    title: str = "Speed Heatmap",
    ax: Optional[plt.Axes] = None,
    show: bool = True,
) -> plt.Figure:
    """Path coloured by normalised speed — hot = fast, cool = slow."""
    fig, ax = _get_ax(ax)

    pts    = np.array([[p.x, p.y] for p in run.telemetry])
    values = np.array(analysis.heatmap_values)
    cmap   = plt.get_cmap("plasma")

    for i in range(len(pts) - 1):
        ax.plot(
            [pts[i, 0], pts[i + 1, 0]],
            [pts[i, 1], pts[i + 1, 1]],
            color=cmap(values[i]),
            linewidth=3,
            solid_capstyle="round",
        )

    sm = plt.cm.ScalarMappable(cmap=cmap, norm=mcolors.Normalize(0, 1))
    sm.set_array([])
    cbar = fig.colorbar(sm, ax=ax)
    cbar.set_label("Normalised Speed", color="white")
    plt.setp(plt.getp(cbar.ax.axes, "yticklabels"), color="white")

    ax.set_aspect("equal")
    _style_dark(fig, ax, title)
    if show:
        plt.tight_layout()
        plt.show()
    return fig


def plot_line_comparison(
    run: DriverRun,
    reference: DriverRun,
    racing_line: Optional[np.ndarray] = None,
    title: str = "Line Comparison",
    ax: Optional[plt.Axes] = None,
    show: bool = True,
) -> plt.Figure:
    """Overlay actual vs reference vs ideal racing line."""
    fig, ax = _get_ax(ax)

    ref_pts = np.array([[p.x, p.y] for p in reference.telemetry])
    run_pts = np.array([[p.x, p.y] for p in run.telemetry])

    ax.plot(ref_pts[:, 0], ref_pts[:, 1], "c-",  linewidth=2,   label="Reference",       alpha=0.8)
    ax.plot(run_pts[:, 0], run_pts[:, 1], "y--", linewidth=1.5, label=run.driver_name,   alpha=0.8)

    if racing_line is not None:
        ax.plot(racing_line[:, 0], racing_line[:, 1], "r-", linewidth=2, label="Ideal Line", alpha=0.9)

    ax.set_aspect("equal")
    _style_dark(fig, ax, title)
    ax.legend(facecolor="#1a1a2e", edgecolor="#333355", labelcolor="white")
    if show:
        plt.tight_layout()
        plt.show()
    return fig


def plot_delta_annotations(
    track: Track,
    analysis: AnalysisResult,
    title: str = "Segment Delta Times",
    show: bool = True,
) -> plt.Figure:
    """Track map annotated with per-segment Δ time vs reference."""
    fig, ax = plt.subplots(figsize=(12, 8))
    xs, ys = track.xy

    ax.plot(xs, ys, color="#444466", linewidth=2, zorder=1)

    for sd in analysis.segment_deltas:
        seg = track.segments[sd.segment_index]
        mid = (seg.start_idx + seg.end_idx) // 2
        if mid < len(xs):
            colour = "#ff4444" if sd.delta > 0 else "#44ff88"
            sign   = "+" if sd.delta >= 0 else ""
            ax.annotate(
                f"{sign}{sd.delta:.3f}s",
                xy=(xs[mid], ys[mid]),
                fontsize=7,
                color=colour,
                ha="center",
                va="center",
                bbox=dict(boxstyle="round,pad=0.2", facecolor="#1a1a2e",
                          edgecolor=colour, alpha=0.85),
            )

    ax.set_aspect("equal")
    _style_dark(fig, ax, title)
    if show:
        plt.tight_layout()
        plt.show()
    return fig


# ── helpers ──────────────────────────────────────────────────────────────────

def _get_ax(ax: Optional[plt.Axes]) -> Tuple[plt.Figure, plt.Axes]:
    if ax is None:
        return plt.subplots(figsize=(12, 8))
    return ax.get_figure(), ax


def _style_dark(fig: plt.Figure, ax: plt.Axes, title: str) -> None:
    ax.set_facecolor("#1a1a2e")
    fig.patch.set_facecolor("#0f0f1a")
    ax.set_title(title, color="white", fontsize=14)
    ax.tick_params(colors="white")
    for spine in ax.spines.values():
        spine.set_edgecolor("#333355")
