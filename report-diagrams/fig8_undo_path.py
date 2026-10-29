"""Fig. 8 - Undo example: c1=MOVE(3), c2=TURN(90deg), c3=MOVE(2), then
c3^-1=MOVE(-2) retraces the last leg, returning the rover to its pose after c2."""
import numpy as np
from common import plt, INK, MUTED

fig, ax = plt.subplots(figsize=(4.6, 4.3))
ax.set_aspect("equal")

start = (0, 0)
after_c1 = (0, 3.0)          # c1: MOVE(3) forward along +y
after_c3 = (2.5, 3.0)        # c3: MOVE(2.5) along new heading (+x), drawn a bit long for clarity

# axes (small, schematic)
ax.annotate("", xy=(-0.7, 4.1), xytext=(-0.7, -0.5), arrowprops=dict(arrowstyle="-|>", color=MUTED, lw=1.0))
ax.text(-0.7, 4.2, "$y$", color=MUTED, fontsize=11, ha="center")
ax.annotate("", xy=(3.5, -0.5), xytext=(-1.0, -0.5), arrowprops=dict(arrowstyle="-|>", color=MUTED, lw=1.0))
ax.text(3.65, -0.5, "$x$", color=MUTED, fontsize=11, va="center")

c1_color, c2_color, c3_color, inv_color = INK, "#2f6b3a", INK, "#b33a3a"

# c1: start -> after_c1 (solid black)
ax.annotate("", xy=after_c1, xytext=start, arrowprops=dict(arrowstyle="-|>", color=c1_color, lw=2.0))

# c2: turn in place - quarter-circle arc swung to the upper-right of the corner,
# clear of both the incoming (vertical) and outgoing (horizontal) legs
rad = 0.45
th = np.linspace(np.pi / 2, 0, 40)
arc_x = after_c1[0] + rad * np.cos(th)
arc_y = after_c1[1] + rad * np.sin(th)
ax.plot(arc_x, arc_y, color=c2_color, lw=1.8)
ax.annotate("", xy=(arc_x[-1], arc_y[-1]), xytext=(arc_x[-4], arc_y[-4]),
            arrowprops=dict(arrowstyle="-|>", color=c2_color, lw=1.8))

# c3: after_c1 -> after_c3 (solid black, along +x)
ax.annotate("", xy=after_c3, xytext=after_c1, arrowprops=dict(arrowstyle="-|>", color=c3_color, lw=2.0))

# undo: c3^-1, dashed red, drawn as a slightly lower parallel segment retracing c3
y_inv = after_c1[1] - 0.35
ax.annotate("", xy=(after_c1[0] + 0.08, y_inv), xytext=(after_c3[0] - 0.08, y_inv),
            arrowprops=dict(arrowstyle="-|>", color=inv_color, lw=1.8, linestyle=(0, (5, 3))))

# waypoints
for p in (start, after_c1, after_c3):
    ax.plot(*p, "o", color=INK, ms=5.5, zorder=5)
ax.text(start[0] - 0.18, start[1] - 0.32, "start", fontsize=10, color=INK, ha="center")

# legend box (keeps the path itself uncluttered)
legend_x, legend_y, dy = 1.15, 2.05, 0.37
entries = [
    (c1_color, "-", r"$c_1 = (\mathrm{MOVE}, 3)$"),
    (c2_color, "-", r"$c_2 = (\mathrm{TURN}, 90^\circ)$"),
    (c3_color, "-", r"$c_3 = (\mathrm{MOVE}, 2)$"),
    (inv_color, "--", r"$c_3^{-1} = (\mathrm{MOVE}, -2)$ (undo)"),
]
for i, (color, ls, label) in enumerate(entries):
    y = legend_y - i * dy
    ax.plot([legend_x, legend_x + 0.32], [y, y], color=color, lw=2.0,
            linestyle="--" if ls == "--" else "-")
    ax.text(legend_x + 0.42, y, label, fontsize=9.3, color=INK, va="center")

ax.set_xlim(-1.2, 3.8)
ax.set_ylim(-1.0, 4.3)
ax.axis("off")

fig.savefig("figures/fig8_undo_path.png")
print("wrote figures/fig8_undo_path.png")
