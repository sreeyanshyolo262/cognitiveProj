"""Fig. 7 - Command memory with K=4: push on the right, discard the oldest,
undo pops the newest and executes its inverse."""
from common import plt, INK, MUTED, LINE, FILL

fig, ax = plt.subplots(figsize=(6.0, 2.6))
ax.axis("off")
ax.set_xlim(-1.6, 7.0)
ax.set_ylim(-1.7, 1.6)
ax.set_aspect("equal")

labels = [r"$c_{t-3}$", r"$c_{t-2}$", r"$c_{t-1}$", r"$c_t$"]
w, h = 1.15, 0.9
xs = [0, 1.3, 2.6, 3.9]

for x, lab in zip(xs, labels):
    fc = "#fde9e9" if lab == r"$c_t$" else FILL
    box = plt.Rectangle((x, -h / 2), w, h, facecolor=fc, edgecolor=LINE, linewidth=1.3, zorder=2)
    ax.add_patch(box)
    ax.text(x + w / 2, 0, lab, ha="center", va="center", fontsize=13, color=INK)

# oldest / newest labels
ax.text(xs[0] + w / 2, h / 2 + 0.28, "oldest", ha="center", fontsize=10, color=MUTED)
ax.text(xs[-1] + w / 2, h / 2 + 0.28, "newest", ha="center", fontsize=10, color=MUTED)

# discard arrow (left)
ax.annotate("", xy=(-1.3, 0), xytext=(xs[0] - 0.08, 0),
            arrowprops=dict(arrowstyle="-|>", color="#8a3b3b", lw=1.6))
ax.text(-1.3, 0.28, "discard", ha="left", fontsize=10.5, color="#8a3b3b")

# push arrow (right), new c entering
ax.annotate("", xy=(xs[-1] + w + 0.1, 0), xytext=(xs[-1] + w + 1.1, 0),
            arrowprops=dict(arrowstyle="-|>", color="#1a4a7a", lw=1.6))
ax.text(xs[-1] + w + 1.15, 0.28, "new $c$", ha="left", fontsize=10.5, color="#1a4a7a")
ax.text(xs[-1] + w + 0.6, -0.42, "push", ha="center", fontsize=10.5, color="#1a4a7a")

# undo annotation, pointing at c_t
ax.annotate("", xy=(xs[-1] + w / 2, -h / 2 - 0.08), xytext=(xs[-1] + w / 2, -1.25),
            arrowprops=dict(arrowstyle="-|>", color="#8a3b3b", lw=1.4))
ax.text(xs[-1] + w / 2, -1.55, r"undo: pop $c_t$, run $c_t^{-1}$",
        ha="center", fontsize=10.5, color="#8a3b3b")

fig.savefig("figures/fig7_command_memory.png")
print("wrote figures/fig7_command_memory.png")
