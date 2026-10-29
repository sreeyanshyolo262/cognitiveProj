"""Fig. 2 - Processing of a single voice command, including validation and undo."""
from graphviz import Digraph
from common import GV_FONT, FILL, FILL2, LINE, INK

g = Digraph("flowchart", format="png")
g.attr(bgcolor="white", rankdir="TB", nodesep="0.45", ranksep="0.45", dpi="300")
g.attr("node", fontname=GV_FONT, fontsize="12", fontcolor=INK, color=LINE, penwidth="1.3")
g.attr("edge", fontname=GV_FONT, fontsize="11", color=LINE, fontcolor=INK, arrowsize="0.8", penwidth="1.1")

box = dict(shape="box", style="rounded,filled", fillcolor=FILL, margin="0.2,0.12")
diamond = dict(shape="diamond", style="filled", fillcolor=FILL2, margin="0.15,0.1")
term = dict(shape="box", style="rounded,filled", fillcolor="white", margin="0.18,0.1")

g.node("a", "Spoken utterance a", **term)
g.node("transcribe", "Transcribe:  x̂ = R(a)", **box)
g.node("translate", "Translate:  c = T(x̂, M)", **box)
g.node("validsafe", "Valid and\nsafe?", **diamond)
g.node("repeat", "Ask user\nto repeat", **term)
g.node("undo", "Undo?", **diamond)
g.node("popundo", "Pop c_t, execute\nits inverse c_t^-1", **box)
g.node("exec", "Execute primitives", **box)
g.node("push", "Push c to memory M", **box)

g.edge("a", "transcribe")
g.edge("transcribe", "translate")
g.edge("translate", "validsafe")
g.edge("validsafe", "repeat", label="no")
g.edge("validsafe", "undo", label="yes")
g.edge("undo", "popundo", label="yes")
g.edge("undo", "exec", label="no")
g.edge("exec", "push")

g.render("figures/fig2_flowchart", cleanup=True)
print("wrote figures/fig2_flowchart.png")
