"""Shared style settings so every figure looks like it belongs to the same paper."""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm

plt.rcParams.update({
    "font.family": "sans-serif",
    "font.sans-serif": ["DejaVu Sans", "Arial", "Helvetica"],
    "font.size": 11,
    "axes.linewidth": 1.0,
    "savefig.dpi": 300,
    "figure.dpi": 150,
    "savefig.facecolor": "white",
    "savefig.bbox": "tight",
    "savefig.pad_inches": 0.08,
})

INK = "#111318"
MUTED = "#555a63"
LINE = "#2b2e33"
FILL = "#eef2f8"
FILL2 = "#fde9e9"
ACCENT = "#1a4a7a"

GV_FONT = "Helvetica"
GV_GRAPH_ATTRS = dict(bgcolor="white", rankdir="LR", nodesep="0.45", ranksep="0.55", dpi="300")
GV_NODE_ATTRS = dict(fontname=GV_FONT, fontsize="12", color=LINE, fontcolor=INK)
GV_EDGE_ATTRS = dict(fontname=GV_FONT, fontsize="10.5", color=LINE, fontcolor=INK, arrowsize="0.8")
