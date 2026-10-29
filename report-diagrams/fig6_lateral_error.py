"""Fig. 6 - Theoretical lateral drift e_perp(d) = eps*d^2/(2b), b = 0.2 m."""
import numpy as np
from common import plt, INK, MUTED

b = 0.2
d = np.linspace(0, 10, 200)

fig, ax = plt.subplots(figsize=(4.6, 3.2))
for eps, ls in [(0.005, "-"), (0.01, "--"), (0.02, ":")]:
    e_perp = eps * d**2 / (2 * b)
    ax.plot(d, e_perp, ls, color=INK, lw=1.8, label=rf"$\epsilon = {eps}$")

ax.set_xlabel("Commanded distance $d$ (m)")
ax.set_ylabel(r"Lateral error $e_\perp$ (m)")
ax.set_xlim(0, 10)
ax.set_ylim(0, None)
ax.grid(True, color="#dde1e8", linewidth=0.7)
ax.set_axisbelow(True)
for spine in ("top", "right"):
    ax.spines[spine].set_visible(False)
ax.legend(frameon=False, loc="upper left")

fig.savefig("figures/fig6_lateral_error.png")
print("wrote figures/fig6_lateral_error.png")
