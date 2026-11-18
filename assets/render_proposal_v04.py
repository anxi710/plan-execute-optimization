"""Render the three English proposal diagrams with Matplotlib.

Run: python assets/render_proposal_v04.py
Requires: Matplotlib; no project dependency was added.
Exports: 300 dpi PNG, editable-text SVG, and embedded-font PDF.
"""

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.patches import FancyArrowPatch, Rectangle
from matplotlib.path import Path as MplPath


OUT = Path(__file__).resolve().parent
BLUE, BLUE2 = "#0F4D92", "#3775BA"
GREEN, PINK, RED = "#DDF3DE", "#F6CFCB", "#B64342"
GRAY, INK, LIGHT = "#767676", "#272727", "#CFCECE"
available_fonts = {font.name for font in font_manager.fontManager.ttflist}
font = next(name for name in ("Arial", "Helvetica", "DejaVu Sans") if name in available_fonts)
plt.rcParams.update({
    "font.family": [font, "sans-serif"],
    "font.size": 16,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.linewidth": 2,
    "legend.frameon": False,
    "svg.fonttype": "none",
    "pdf.fonttype": 42,
    "ps.fonttype": 42,
    "savefig.facecolor": "white",
})


def canvas(height):
    fig, ax = plt.subplots(figsize=(16.4, height))
    ax.set(xlim=(0, 16.4), ylim=(0, height))
    ax.set_aspect("equal")
    ax.set_axis_off()
    fig.subplots_adjust(left=0, right=1, bottom=0, top=1)
    return fig, ax


def text(ax, x, y, value, size=16, color=INK, weight="normal", ha="center", **kwargs):
    return ax.text(x, y, value, fontsize=size, color=color, weight=weight,
                   ha=ha, va="center", linespacing=1.35, zorder=4, **kwargs)


def box(ax, x, y, width, height, label=None, edge=GRAY, fill="white", size=16, lw=1.6):
    ax.add_patch(Rectangle((x, y), width, height, linewidth=lw,
                           edgecolor=edge, facecolor=fill, zorder=2))
    if label:
        text(ax, x + width / 2, y + height / 2, label, size=size)


def arrow(ax, start, end, color=INK, dashed=False, both=False, lw=1.8):
    ax.add_patch(FancyArrowPatch(start, end, arrowstyle="<->" if both else "-|>",
                                mutation_scale=17, linewidth=lw, color=color,
                                linestyle=(0, (5, 3)) if dashed else "-",
                                shrinkA=0, shrinkB=0, zorder=3))


def routed_arrow(ax, points, color=INK, dashed=False, lw=1.8):
    path = MplPath(points, [MplPath.MOVETO] + [MplPath.LINETO] * (len(points) - 1))
    ax.add_patch(FancyArrowPatch(path=path, arrowstyle="-|>", mutation_scale=17,
                                linewidth=lw, color=color, fill=False,
                                linestyle=(0, (5, 3)) if dashed else "-", zorder=3))


def export(fig, name):
    # Absolute canvas geometry keeps diagrams aligned across formats.
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    for ax in fig.axes:
        for item in ax.texts:
            bounds = item.get_window_extent(renderer)
            if not fig.bbox.contains(bounds.x0, bounds.y0) or not fig.bbox.contains(bounds.x1, bounds.y1):
                raise ValueError(f"Clipped text in {name}: {item.get_text()}")
    for ext in ("png", "pdf", "svg"):
        fig.savefig(OUT / f"{name}.{ext}", dpi=300, facecolor="white")
    plt.close(fig)
    print(name)


def fullplan_learning():
    fig, ax = canvas(6.2)
    text(ax, 0.45, 5.88, "Full-plan learning with a fixed Executor", 21, weight="bold", ha="left")

    text(ax, 1.35, 3.75, "Task +\nvisible state", 17)
    box(ax, 3.0, 2.65, 4.7, 2.2, edge=BLUE, lw=2.1)
    text(ax, 5.35, 4.44, "Planner", 21, BLUE, "bold")
    text(ax, 5.35, 4.05, "Only trainable policy", 14, BLUE2)
    text(ax, 5.35, 3.46, "Understanding · candidate construction\nEvidence checking · revision", 14.5)
    text(ax, 5.35, 2.96, "Single- or multi-call formation", 13, GRAY)
    text(ax, 5.35, 5.43, "Relevant experience  (optional)", 13, GRAY)
    arrow(ax, (5.35, 5.18), (5.35, 4.85), color=GRAY, dashed=True)

    box(ax, 8.5, 3.15, 1.7, 1.25, "One high-level\nfull-plan", edge=BLUE2, size=14.5)
    box(ax, 10.9, 3.15, 1.95, 1.25, "Frozen\nExecutor", size=16.5)
    box(ax, 13.65, 3.15, 2.2, 1.25, "Environment", size=15.5)
    arrow(ax, (2.3, 3.78), (3.0, 3.78))
    arrow(ax, (7.7, 3.78), (8.5, 3.78))
    arrow(ax, (10.2, 3.78), (10.9, 3.78))
    arrow(ax, (12.85, 3.78), (13.65, 3.78), both=True)

    box(ax, 8.1, 0.85, 3.3, 1.05, "Low-cost candidate\nevaluation", edge=BLUE2, fill=GREEN, size=16)
    box(ax, 3.65, 0.85, 3.65, 1.05, "Planner-only\nparameter update", edge=RED, fill=PINK, size=16)
    arrow(ax, (9.35, 3.15), (9.35, 1.9), color=RED, dashed=True)
    text(ax, 8.95, 2.43, "candidate", 12.5, RED, ha="right")
    routed_arrow(ax, [(14.75, 3.15), (14.75, 1.375), (11.4, 1.375)], RED, dashed=True)
    text(ax, 13.15, 1.72, "execution evidence", 13, RED)
    arrow(ax, (8.1, 1.375), (7.3, 1.375), color=RED, dashed=True)
    arrow(ax, (5.35, 1.9), (5.35, 2.65), color=RED, dashed=True)

    arrow(ax, (0.65, 0.3), (1.25, 0.3))
    text(ax, 1.45, 0.3, "Runtime", 12, ha="left")
    arrow(ax, (4.0, 0.3), (4.6, 0.3), color=RED, dashed=True)
    text(ax, 4.8, 0.3, "Training feedback", 12, RED, ha="left")
    arrow(ax, (8.3, 0.3), (8.9, 0.3), color=GRAY, dashed=True)
    text(ax, 9.1, 0.3, "Optional input", 12, GRAY, ha="left")
    export(fig, "fig1_fullplan_learning_v04")


def learning_loop():
    fig, ax = canvas(7.0)
    text(ax, 0.45, 6.63, "Candidate learning and held-out evaluation", 21, weight="bold", ha="left")
    text(ax, 0.45, 5.97, "(a) Training", 16, BLUE, "bold", ha="left")

    y, h = 4.35, 1.2
    nodes = [
        (0.45, 2.15, "Sample\ntraining tasks", GRAY, "white"),
        (3.15, 2.55, "Form strategic\nfull-plan candidates", BLUE, "white"),
        (6.25, 2.65, "Collect grounded\nevidence", BLUE2, GREEN),
        (9.45, 2.65, "Form learning signal\nwith uncertainty", BLUE2, GREEN),
        (12.7, 3.15, "Update\nPlanner only", RED, PINK),
    ]
    for x, w, label, edge, fill in nodes:
        box(ax, x, y, w, h, label, edge, fill, 15.5)
    for first, second in zip(nodes, nodes[1:]):
        arrow(ax, (first[0] + first[1], 4.95), (second[0], 4.95))
    text(ax, 4.425, 3.99, "Single- or multi-call", 12.5, GRAY)
    text(ax, 7.575, 3.86, "Full / partial execution\nor compatible training history", 12.5, GRAY)
    text(ax, 10.775, 3.86, "Optional: unsupported\nestimate ≠ failure", 12.5, GRAY)
    routed_arrow(ax, [(14.275, 4.35), (14.275, 3.05), (1.525, 3.05), (1.525, 4.35)], RED, dashed=True)
    text(ax, 7.9, 2.82, "Next training batch", 13, RED)
    text(ax, 7.575, 5.83, "Full execution records both success and cost", 12.5, GRAY)

    ax.plot([0.45, 15.85], [2.37, 2.37], color=LIGHT, linewidth=1.1)
    text(ax, 0.45, 2.03, "(b) Held-out evaluation", 16, BLUE, "bold", ha="left")
    test_nodes = [
        (0.75, 2.4, "Held-out task", GRAY),
        (4.25, 3.2, "Learned Planner\n(frozen)", BLUE),
        (8.55, 3.2, "Same frozen\nExecutor", GRAY),
        (12.85, 2.75, "Success +\ntotal cost", GRAY),
    ]
    for x, w, label, edge in test_nodes:
        box(ax, x, 0.72, w, 0.95, label, edge=edge, size=15)
    for first, second in zip(test_nodes, test_nodes[1:]):
        arrow(ax, (first[0] + first[1], 1.195), (second[0], 1.195))
    text(ax, 8.2, 0.28, "No test feedback enters learning.", 12.5, GRAY)
    export(fig, "fig2_learning_loop_v04")


def planner_centered_branch():
    fig, ax = canvas(6.4)
    text(ax, 0.45, 6.02, "Planner-centered online maintenance", 21, weight="bold", ha="left")
    text(ax, 0.45, 5.55, "Independent hypothesis — not a replacement for the main architecture", 14.5, RED, ha="left")

    text(ax, 1.65, 3.7, "Current visible state\n+ available evidence", 15.5)
    box(ax, 3.7, 2.6, 4.35, 2.2, edge=BLUE, lw=2.1)
    text(ax, 5.875, 4.3, "Planner", 21, BLUE, "bold")
    text(ax, 5.875, 3.55, "Maintains a whole or\nremaining-whole-plan", 16)
    text(ax, 5.875, 2.95, "Decides what to delegate next", 13, GRAY)
    box(ax, 10.25, 3.1, 2.1, 1.25, "Frozen\nExecutor", size=17)
    box(ax, 13.25, 3.1, 2.6, 1.25, "Real environment", size=15.5)
    arrow(ax, (2.95, 3.725), (3.7, 3.725))
    arrow(ax, (8.05, 3.725), (10.25, 3.725))
    text(ax, 9.15, 4.2, "Bounded execution\nrequest", 13)
    arrow(ax, (12.35, 3.725), (13.25, 3.725), both=True)
    routed_arrow(ax, [(14.55, 3.1), (14.55, 1.7), (5.875, 1.7), (5.875, 2.6)], BLUE)
    text(ax, 10.2, 2.07, "New observations + observed state changes", 15, BLUE)
    text(ax, 10.2, 1.3, "Real execution may advance the task; reset is not assumed.", 12.5, GRAY)

    ax.plot([0.45, 15.85], [0.88, 0.88], color=LIGHT, linewidth=1.1)
    text(ax, 0.6, 0.48, "Learning target remains open:", 13.5, BLUE, "bold", ha="left")
    text(ax, 5.0, 0.48, "Plan content · formation process · online maintenance", 13.5, ha="left")
    export(fig, "fig3_planner_centered_branch_v04")


if __name__ == "__main__":
    fullplan_learning()
    learning_loop()
    planner_centered_branch()
