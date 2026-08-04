# Graph-Debt Tracker

Source: graphify knowledge-graph audit of 2026-08-04 (baseline graph: 1,753 nodes / 4,756 edges / 109 communities).
Branch: `graph-debt`. Status legend: ⏳ pending · 🔄 in progress · ✅ done.

| # | Metric | Baseline (2026-08-04) | Target | Actual | Status |
|---|--------|-----------------------|--------|--------|--------|
| W1 | `blocks/gui/support.py` LOC | 1,298 | ≤ 800 | **798** (+ preview.py 504, settings_io.py 82) | ✅ |
| W1 | tests passing | 202 | all green | **204 passed** (202 + 2 new geometry tests) | ✅ |
| W2 | contradictory working-area claims | 3 docs disagree (255×420 vs 255×440 vs 250×440) | 0 — GEOMETRY.md single source | **0** — GEOMETRY.md authoritative; hardware README fixed to 255×420; root README links it | ✅ |
| W2 | sheet-vs-travel guard test | none | 1 test tracking sheet 440mm > Y-travel 420mm | **2 tests** in `tests/test_geometry_consistency.py` (width fits; height overshoot made visible) | ✅ |
| W3 | INFERRED graph edges audited | 0/22 flagged (16 unique after dedup) | all verdicts with file:line evidence | **16/16**: 1 CORRECT, 15 WRONG (LLM mistook injected test doubles for real deps) — `planning/GRAPH_EDGE_AUDIT.md` | ✅ |
| W4 | dead block stubs | 1 (`blocks/direct_print/`) | 0 | **0** — deleted, references cleaned, `grep -r direct_print src tests` empty | ✅ |
| info | god-node degree GuiSettings / SupervisorService / GuiContext | 89 / 83 / 78 | re-measured post-refactor | **92 / 83 / 78** (graph 2026-08-04b: 1,780 nodes / 4,828 edges / 114 communities) | ✅ |

## Reading the informational row

The W1 split reduced *file-level* debt (support.py −500 LOC) but, as expected for a mechanical extraction, did not reduce *class-level* coupling: `GuiSettings`'s degree even rose slightly (re-export edges from the two new modules). Actually shrinking the god **classes** (`GuiSettings`, `GuiContext`) would require an interface-level refactor — deliberately out of scope here; candidate for a future workstream.

## Open item carried forward

- **Hardware verification**: is the physical Y travel really 420mm, or was the machine modified for 440mm sheets? Until answered on the machine, `echodraw/hardware/GEOMETRY.md` documents the 20mm overshoot and `tests/test_geometry_consistency.py` keeps it visible.
