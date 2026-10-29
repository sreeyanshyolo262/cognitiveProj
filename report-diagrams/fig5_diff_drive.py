"""Fig. 5 - Differential-drive model (top view) with track width b and wheel radius r."""
import numpy as np
from common import plt, INK, MUTED, LINE

fig, ax = plt.subplots(figsize=(4.2, 4.2))
ax.set_aspect("equal")
ax.axis("off")

b = 1.6   # track width (drawing units)
L = 1.2   # body length
r = 0.22  # wheel radius drawn as half-length of the wheel rectangle

# body (rounded square), centred at origin, heading = +y (up)
body = plt.Rectangle((-L / 2, -L / 2), L, L, facecolor="#eef2f8", edgecolor=LINE,
                      linewidth=1.3, joinstyle="round", zorder=2)
ax.add_patch(body)

# wheels: left and right, each a thin rectangle straddling the body sides
wheel_w, wheel_h = 0.16, 2 * r
left_wheel = plt.Rectangle((-L / 2 - wheel_w, -wheel_h / 2), wheel_w, wheel_h,
                            facecolor="#555a63", edgecolor=LINE, linewidth=1.0, zorder=3)
right_wheel = plt.Rectangle((L / 2, -wheel_h / 2), wheel_w, wheel_h,
                             facecolor="#555a63", edgecolor=LINE, linewidth=1.0, zorder=3)
ax.add_patch(left_wheel)
ax.add_patch(right_wheel)

# track-width dimension line (b), below the body
y_dim = -L / 2 - 0.55
ax.annotate("", xy=(L / 2 + wheel_w, y_dim), xytext=(-L / 2 - wheel_w, y_dim),
            arrowprops=dict(arrowstyle="<->", color=INK, lw=1.1))
ax.text(0, y_dim - 0.16, "b", ha="center", va="top", fontsize=13, style="italic", color=INK)
for x in (-L / 2 - wheel_w, L / 2 + wheel_w):
    ax.plot([x, x], [y_dim - 0.06, y_dim + 0.06], color=INK, lw=1.0)

# wheel radius dimension (2r), on the right wheel
ax.annotate("", xy=(L / 2 + wheel_w + 0.35, wheel_h / 2), xytext=(L / 2 + wheel_w + 0.35, -wheel_h / 2),
            arrowprops=dict(arrowstyle="<->", color=INK, lw=1.0))
ax.text(L / 2 + wheel_w + 0.45, 0, "2r", ha="left", va="center", fontsize=12, style="italic", color=INK)

# heading arrow theta (body forward direction = +y), from centre
ax.annotate("", xy=(0, L / 2 + 0.55), xytext=(0, 0),
            arrowprops=dict(arrowstyle="-|>", color=INK, lw=1.4))
ax.text(0.10, L / 2 + 0.55, r"heading $\theta$", fontsize=11, color=INK, va="center")

# body-frame velocity v, offset to the right of centre so it clears omega
vx = 0.32
ax.annotate("", xy=(vx, 0.32), xytext=(vx, -0.32),
            arrowprops=dict(arrowstyle="-|>", color="#1a4a7a", lw=1.6))
ax.text(vx + 0.14, 0.0, "v", fontsize=13, style="italic", color="#1a4a7a", va="center")

# angular velocity omega, curved arrow offset to the left of centre
th = np.linspace(0.55, 2.55, 60)
rad = 0.34
cx = -0.32
ax.plot(cx + rad * np.cos(th), rad * np.sin(th), color="#8a3b3b", lw=1.5)
ax.annotate("", xy=(cx + rad * np.cos(th[0]), rad * np.sin(th[0])),
            xytext=(cx + rad * np.cos(th[4]), rad * np.sin(th[4])),
            arrowprops=dict(arrowstyle="-|>", color="#8a3b3b", lw=1.5))
ax.text(cx - 0.14, 0.0, r"$\omega$", fontsize=13, color="#8a3b3b", va="center", ha="right")

# wheel angular speed labels
ax.text(-L / 2 - wheel_w - 0.05, wheel_h / 2 + 0.18, r"$\omega_L$", fontsize=12,
        style="italic", ha="right", color=INK)
ax.text(L / 2 + wheel_w + 0.05, wheel_h / 2 + 0.18, r"$\omega_R$", fontsize=12,
        style="italic", ha="left", color=INK)

ax.set_xlim(-2.1, 2.1)
ax.set_ylim(-1.7, 2.3)

fig.savefig("figures/fig5_diff_drive.png")
print("wrote figures/fig5_diff_drive.png")
