"""Fig. 3 - Illustrative structured output produced by the translation step."""
from common import plt, INK, MUTED, LINE

user_line = 'User: "pick up the bottle and take it to the person"'
json_lines = [
    "LLM output:",
    "{",
    '  "commands": [',
    '    {"op": "pick"},',
    '    {"op": "goto", "target": "person"},',
    '    {"op": "drop"}',
    "  ]",
    "}",
]

fig, ax = plt.subplots(figsize=(4.4, 2.5))
ax.axis("off")
ax.set_xlim(0, 1)
ax.set_ylim(0, 1)

box = plt.Rectangle((0.02, 0.04), 0.96, 0.92, transform=ax.transAxes,
                     facecolor="#f6f7fa", edgecolor=LINE, linewidth=1.1, zorder=1)
ax.add_patch(box)

ax.text(0.06, 0.90, user_line, transform=ax.transAxes, fontsize=10.3,
        family="monospace", color=INK, va="top")
ax.plot([0.06, 0.94], [0.78, 0.78], transform=ax.transAxes, color=LINE, lw=0.8)

y = 0.70
for i, line in enumerate(json_lines):
    weight = "bold" if i == 0 else "normal"
    color = MUTED if i == 0 else INK
    ax.text(0.06, y, line, transform=ax.transAxes, fontsize=10.3,
            family="monospace", color=color, va="top", weight=weight)
    y -= 0.085

fig.savefig("figures/fig3_llm_output.png")
print("wrote figures/fig3_llm_output.png")
