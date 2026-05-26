"""
4-panel analysis dashboard.
"""
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
import numpy as np
from typing import Optional
from core.models import Track, DriverRun, AnalysisResult


def plot_full_dashboard(
    track: Track,
    run: DriverRun,
    reference: DriverRun,
    analysis: AnalysisResult,
    racing_line: Optional[np.ndarray] = None,
    show: bool = True,
) -> plt.Figure:
    """
    4-panel dashboard:
      [TL] Track map with line overlay
      [TR] Speed profile comparison
      [BL] Segment delta times bar chart
      [BR] Pedal trace (throttle / brake)
    """
    fig = plt.figure(figsize=(16, 10))
    fig.patch.set_facecolor("#0f0f1a")

    gs = gridspec.GridSpec(2, 2, figure=fig, hspace=0.38, wspace=0.28)
    ax_map   = fig.add_subplot(gs[0, 0])
    ax_speed = fig.add_subplot(gs[0, 1])
    ax_delta = fig.add_subplot(gs[1, 0])
    ax_pedal = fig.add_subplot(gs[1, 1])

    _panel_track_map(ax_map, track, run, reference, racing_line)
    _panel_speed_profile(ax_speed, run, reference)
    _panel_delta_bar(ax_delta, analysis)
    _panel_pedal_trace(ax_pedal, run)

    sign = "+" if analysis.total_delta >= 0 else ""
    fig.suptitle(
        f"Analysis ▸ {run.driver_name}  Lap {run.lap}  |  "
        f"Δ {sign}{analysis.total_delta:.3f}s vs {reference.driver_name}  |  "
        f"Consistency {analysis.consistency_score:.2f}",
        color="white",
        fontsize=13,
        fontweight="bold",
    )

    if show:
        plt.show()
    return fig


# ── panels ───────────────────────────────────────────────────────────────────

def _panel_track_map(ax, track, run, reference, racing_line):
    xs, ys = track.xy
    ax.plot(xs, ys, color="#444466", linewidth=1.5, label="Track", zorder=1)

    ref_pts = np.array([[p.x, p.y] for p in reference.telemetry])
    run_pts = np.array([[p.x, p.y] for p in run.telemetry])
    ax.plot(ref_pts[:, 0], ref_pts[:, 1], "c-",  linewidth=1.5, label="Reference",     alpha=0.7)
    ax.plot(run_pts[:, 0], run_pts[:, 1], "y--", linewidth=1.2, label=run.driver_name, alpha=0.7)

    if racing_line is not None:
        ax.plot(racing_line[:, 0], racing_line[:, 1], "r-", linewidth=1.5, label="Ideal", alpha=0.85)

    ax.set_aspect("equal")
    _dark_ax(ax, "Track Map")
    ax.legend(fontsize=7, facecolor="#1a1a2e", edgecolor="#444", labelcolor="white")


def _panel_speed_profile(ax, run, reference):
    run_t  = [p.timestamp for p in run.telemetry]
    run_v  = [p.speed * 3.6 for p in run.telemetry]
    ref_t  = [p.timestamp for p in reference.telemetry]
    ref_v  = [p.speed * 3.6 for p in reference.telemetry]

    ax.plot(ref_t, ref_v, "c-", linewidth=1.5, label="Reference",     alpha=0.8)
    ax.plot(run_t, run_v, "y-", linewidth=1.2, label=run.driver_name, alpha=0.8)

    ax.set_xlabel("Time (s)",    color="white", fontsize=9)
    ax.set_ylabel("Speed (km/h)", color="white", fontsize=9)
    _dark_ax(ax, "Speed Profile")
    ax.legend(fontsize=8, facecolor="#1a1a2e", edgecolor="#444", labelcolor="white")


def _panel_delta_bar(ax, analysis):
    indices = [d.segment_index for d in analysis.segment_deltas]
    deltas  = [d.delta          for d in analysis.segment_deltas]
    colours = ["#ff4444" if d > 0 else "#44ff88" for d in deltas]

    ax.bar(indices, deltas, color=colours, alpha=0.85)
    ax.axhline(0, color="white", linewidth=0.8, alpha=0.5)
    ax.set_xlabel("Segment",  color="white", fontsize=9)
    ax.set_ylabel("Δ time (s)", color="white", fontsize=9)
    _dark_ax(ax, "Segment Deltas  (red = slower)")


def _panel_pedal_trace(ax, run):
    times    = [p.timestamp       for p in run.telemetry]
    throttle = [p.throttle or 0.0 for p in run.telemetry]
    brake    = [p.brake    or 0.0 for p in run.telemetry]

    ax.fill_between(times, throttle,           alpha=0.65, color="#00cc66", label="Throttle")
    ax.fill_between(times, [-b for b in brake], alpha=0.65, color="#ff3333", label="Brake (inv)")
    ax.set_ylim(-1.1, 1.1)
    ax.set_xlabel("Time (s)", color="white", fontsize=9)
    ax.set_ylabel("Input",    color="white", fontsize=9)
    _dark_ax(ax, "Pedal Trace")
    ax.legend(fontsize=8, facecolor="#1a1a2e", edgecolor="#444", labelcolor="white")


def _dark_ax(ax, title: str) -> None:
    ax.set_facecolor("#1a1a2e")
    ax.set_title(title, color="white", fontsize=10)
    ax.tick_params(colors="white", labelsize=8)
    for spine in ax.spines.values():
        spine.set_edgecolor("#333355")
