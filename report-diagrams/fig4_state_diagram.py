"""Fig. 4 - Task sequence for a "deliver" command (PICK, GOTO(target), DROP)."""
from graphviz import Digraph
from common import GV_FONT, FILL, LINE, INK

g = Digraph("states", format="png")
g.attr(bgcolor="white", rankdir="LR", nodesep="0.6", ranksep="0.75", dpi="300")
g.attr("node", shape="circle", style="filled", fillcolor=FILL, color=LINE,
       fontname=GV_FONT, fontsize="12", fontcolor=INK, penwidth="1.3", width="1.05", fixedsize="true")
g.attr("edge", fontname=GV_FONT, fontsize="10.5", color=LINE, fontcolor=INK, arrowsize="0.8", penwidth="1.1")

for n in ["Idle", "Pick", "Go to\ntarget", "Drop"]:
    g.node(n)

g.edge("Idle", "Pick", label="deliver")
g.edge("Pick", "Go to\ntarget", label="grasped")
g.edge("Go to\ntarget", "Drop", label="arrived")
g.edge("Drop", "Idle", label="released")

# "stop" returns to Idle from any state
for n in ["Pick", "Go to\ntarget", "Drop"]:
    g.edge(n, "Idle", label="stop", style="dashed", constraint="false")

g.render("figures/fig4_state_diagram", cleanup=True)
print("wrote figures/fig4_state_diagram.png")
