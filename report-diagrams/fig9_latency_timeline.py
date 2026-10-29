"""Fig. 9 - Sequential stages making up the latency T (bar widths schematic,
not measured): Tasr, Tllm, then small Tval+Tcomm, then Tctrl."""
from common import plt, INK, MUTED, LINE

stages = [
    ("$T_{asr}$", 3.2, "#cfd9ea"),
    ("$T_{llm}$", 4.4, "#eef2f8"),
    ("val\ncomm", 0.7, "#e4e7ec"),
    ("$T_{ctrl}$", 1.0, "#dfe3e9"),
]

fig, ax = plt.subplots(figsize=(6.2, 1.9))
x = 0.0
for label, width, color in stages:
    ax.add_patch(plt.Rectangle((x, 0), width, 1, facecolor=color, edgecolor=LINE, linewidth=1.2))
    ax.text(x + width / 2, 0.5, label, ha="center", va="center", fontsize=10.5, color=INK)
    x += width

total = x
ax.annotate("", xy=(total, -0.55), xytext=(0, -0.55), arrowprops=dict(arrowstyle="-|>", color=INK, lw=1.2))
ax.text(total / 2, -0.85, "$t$", fontsize=11, color=INK, ha="center")

ax.annotate("end of speech", xy=(0, 0), xytext=(0, -1.4),
            ha="center", fontsize=9.5, color=MUTED,
            arrowprops=dict(arrowstyle="-", color=MUTED, lw=0.8))
ax.annotate("motion starts", xy=(total, 0), xytext=(total, -1.4),
            ha="center", fontsize=9.5, color=MUTED,
            arrowprops=dict(arrowstyle="-", color=MUTED, lw=0.8))

ax.set_xlim(-0.3, total + 0.3)
ax.set_ylim(-1.7, 1.3)
ax.axis("off")

fig.savefig("figures/fig9_latency_timeline.png")
print("wrote figures/fig9_latency_timeline.png")
