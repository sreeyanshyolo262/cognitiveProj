# Report figures

All nine figures referenced in the paper ("Voice-Controlled Pick-and-Drop
Rover"), rendered at 300 DPI and ready to drop into the IEEE template.
Everything — scripts and images — lives in this one folder.

| File | Paper figure | Content |
|---|---|---|
| `figures/fig1_architecture.png` | Fig. 1 | System architecture / pipeline block diagram |
| `figures/fig2_flowchart.png` | Fig. 2 | Per-utterance decision flowchart (validate, undo) |
| `figures/fig3_llm_output.png` | Fig. 3 | Example LLM structured-output snippet |
| `figures/fig4_state_diagram.png` | Fig. 4 | Deliver task state machine (Idle/Pick/Go/Drop) |
| `figures/fig5_diff_drive.png` | Fig. 5 | Differential-drive kinematic diagram |
| `figures/fig6_lateral_error.png` | Fig. 6 | Lateral drift vs. distance plot (Eq. 19) |
| `figures/fig7_command_memory.png` | Fig. 7 | FIFO command-memory buffer |
| `figures/fig8_undo_path.png` | Fig. 8 | Worked undo example on a short path |
| `figures/fig9_latency_timeline.png` | Fig. 9 | Latency stage timeline |

## Regenerating

```powershell
cd report-diagrams
.venv\Scripts\python fig1_architecture.py   # ...and so on for each fig*.py
```

Figures 1, 2 and 4 are built with Graphviz (`graphviz` Python package, needs
the `dot` executable on PATH — installed here via `scoop install graphviz`).
Figures 3, 5–9 are built with Matplotlib. `common.py` holds the shared fonts
and colors so every figure matches.

## Notes for whoever pastes these into the paper

- PNG at 300 DPI; re-render larger (edit `figsize`/`dpi` in the scripts) if a
  reviewer wants vector quality — swap `format="png"` for `"pdf"` in the
  Graphviz scripts, or `fig.savefig(..., format="pdf")` in the Matplotlib ones.
- Fig. 6's curves are the actual closed-form equation from the paper
  (`eps * d^2 / (2b)`, `b = 0.2`), not a mockup — if the real wheel-mismatch
  value or track width changes, edit the constants in `fig6_lateral_error.py`.
- Table IV (results) and Table V (failure modes) in the paper are plain
  tables, not figures — not included here since LaTeX/Word renders tables
  natively; ask if you'd also like those built as images.
