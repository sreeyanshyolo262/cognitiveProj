"""Fig. 1 - System architecture of the voice-controlled rover."""
from graphviz import Digraph
from common import GV_FONT, FILL, FILL2, LINE, INK

g = Digraph("architecture", format="png")
g.attr(bgcolor="white", rankdir="LR", nodesep="0.55", ranksep="0.7", dpi="300")
g.attr("node", shape="box", style="rounded,filled", fillcolor=FILL, color=LINE,
       fontname=GV_FONT, fontsize="13", fontcolor=INK, penwidth="1.3", margin="0.22,0.14")
g.attr("edge", fontname=GV_FONT, fontsize="11", color=LINE, fontcolor=INK, arrowsize="0.85", penwidth="1.1")

g.node("voice", "Voice input\n(Kotlin app)")
g.node("asr", "whisper.cpp\nASR")
g.node("llm", "LLM\ntranslator")
g.node("arduino", "Arduino\ncontroller")
g.node("motors", "Motors &\ngripper")
g.node("mem", "Command\nmemory M", shape="box", style="rounded,filled,dashed", fillcolor="white")
g.node("val", "Validation\nlayer V", shape="box", style="rounded,filled,dashed", fillcolor="white")

g.edge("voice", "asr", label="audio")
g.edge("asr", "llm", label="text")
g.edge("llm", "arduino", label="c", style="dashed")
g.edge("arduino", "motors", label="PWM")

g.edge("llm", "val", dir="none", style="dotted", constraint="false")
g.edge("llm", "mem", dir="both", style="dotted", constraint="false")
g.edge("val", "arduino", style="dashed", constraint="false",
       label="  every command passes\n  through validation first")

with g.subgraph() as s:
    s.attr(rank="same")
    s.node("mem")
    s.node("val")

g.render("figures/fig1_architecture", cleanup=True)
print("wrote figures/fig1_architecture.png")
