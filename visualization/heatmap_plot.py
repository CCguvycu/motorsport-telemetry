"""
Braking and throttle zone overlay visualisations.
"""
import matplotlib.pyplot as plt
from core.models import DriverRun


def plot_braking_zones(
    run: DriverRun,
    title: str = "Braking Zones",
    threshold: float = 0.3,
    show: bool = True,
) -> plt.Figure:
    """
    Scatter points where brake > threshold over the driven path.

    Args:
        run:       driver run with brake telemetry
        threshold: brake value (0–1) above which to highlight
        show:      display immediately
    """
    fig, ax = plt.subplots(figsize=(12, 8))

    xs = [p.x for p in run.telemetry]
    ys = [p.y for p in run.telemetry]
    brake_vals = [p.brake or 0.0 for p in run.telemetry]

    ax.plot(xs, ys, color="#333355", linewidth=1.5, zorder=1, label="Path")

    braking_x = [xs[i] for i, b in enumerate(brake_vals) if b >= threshold]
    braking_y = [ys[i] for i, b in enumerate(brake_vals) if b >= threshold]

    if braking_x:
        ax.scatter(braking_x, braking_y, c="#ff3333", s=8, zorder=3,
                   label=f"Braking (>{threshold:.0%})", alpha=0.8)

    ax.set_aspect("equal")
    ax.set_facecolor("#1a1a2e")
    fig.patch.set_facecolor("#0f0f1a")
    ax.set_title(title, color="white", fontsize=12)
    ax.tick_params(colors="white")
    for sp in ax.spines.values():
        sp.set_edgecolor("#333355")
    ax.legend(facecolor="#1a1a2e", edgecolor="#444", labelcolor="white")

    if show:
        plt.tight_layout()
        plt.show()
    return fig


def plot_throttle_map(
    run: DriverRun,
    title: str = "Throttle Application",
    show: bool = True,
) -> plt.Figure:
    """Path coloured by throttle position (green = full throttle)."""
    import numpy as np
    import matplotlib.colors as mcolors

    fig, ax = plt.subplots(figsize=(12, 8))
    pts     = [[p.x, p.y] for p in run.telemetry]
    vals    = [p.throttle or 0.0 for p in run.telemetry]
    cmap    = plt.get_cmap("YlGn")

    for i in range(len(pts) - 1):
        ax.plot(
            [pts[i][0], pts[i + 1][0]],
            [pts[i][1], pts[i + 1][1]],
            color=cmap(vals[i]),
            linewidth=3,
            solid_capstyle="round",
        )

    sm = plt.cm.ScalarMappable(cmap=cmap, norm=mcolors.Normalize(0, 1))
    sm.set_array([])
    cbar = fig.colorbar(sm, ax=ax)
    cbar.set_label("Throttle", color="white")
    plt.setp(plt.getp(cbar.ax.axes, "yticklabels"), color="white")

    ax.set_aspect("equal")
    ax.set_facecolor("#1a1a2e")
    fig.patch.set_facecolor("#0f0f1a")
    ax.set_title(title, color="white", fontsize=12)
    ax.tick_params(colors="white")
    for sp in ax.spines.values():
        sp.set_edgecolor("#333355")

    if show:
        plt.tight_layout()
        plt.show()
    return fig
