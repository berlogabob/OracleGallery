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

---

# Round 2 (2026-08-05): graph findings fixed + auto-update installed

| # | Metric | Baseline | Target | Actual | Status |
|---|--------|----------|--------|--------|--------|
| F1 | audited-wrong INFERRED edges in graph | 15 (AST test-fixture noise, not cache) | ~0 | **0** — test-mock nodes gone entirely (`.graphifyignore` excludes `tests/` + `docs/`) | ✅ |
| F2 | FirebaseSettings degree / bridged communities | 55 / 11 | <40 / ≤6 | **18 / 7** (remaining bridges are its legitimate consumers; 7 vs 6 target = near miss, accepted) | ✅ |
| F3 | GuiSettings→plotter field mappings | 3 hand-written copies | 1 | **1** (`gui_settings_to_plotter_config` is the single source; output byte-identical) | ✅ |
| F4 | broken asset references / duplicate PDFs | 15+ dead citations, 4.6MB byte-dup, 5.9MB unreferenced | 0 / 0 | **0 / 0** — renamed HTML, fixed citations, deleted dup, archived 5.9MB | ✅ |
| F5 | zero-node JSON warning | 17 files | documented | Known graphify blind spot: `symbol_scales.json`, `tinybee.json`, `receipt_payload.json` etc. are load-bearing but Path-read, not imported. Intentionally untouched. | ✅ |
| M | graph auto-update | none | hook + CLAUDE.md | **installed**: post-commit hook (AST rebuild on code changes), post-checkout hook, merge driver, `## graphify` CLAUDE.md section. Doc/image changes still need `/graphify --update` manually. | ✅ |
| info | god nodes after curation | GuiSettings 92 · SupervisorService 83 · GuiContext 78 · DryTransport(!) 49 | — | GuiContext 77 · SupervisorService 54 · ComponentState 45 · GuiSettings **36**; no test mocks in list. Graph: 1,449 nodes / 3,327 edges / 116 communities | ✅ |

---

# Round 3 (2026-08-05): UX/UI declutter

| # | Metric | Baseline | Target | Actual | Status |
|---|--------|----------|--------|--------|--------|
| U2 | status-fact render sites (7 facts) | 18 | ≤ 9 | **9** (live-strip canonical; tests pills, exhibition Print/Mode, work Zero removed; detail metrics kept) | ✅ |
| U2 | inline mini-metric blocks | 6 | 0 | **0** — all via `ui.mini_metric()` | ✅ |
| U2 | inline helper-text class strings | 28 | ≤ 4 | **6** (helper def + generative.py + 4 handle-bound labels the helper can't serve) | ✅* |
| U2 | ghost components/ + dead CSS + dead helpers | 1+2+1 | 0 | **0** — also removed newly-dead status_pill/update_status_pill/STATUS_COLORS + .status-pill CSS | ✅ |
| U2/U3 | actions labeled "START PRINT" | 2 | 1 | **1** (generative → "PRINT CAPTURED SVG") | ✅ |
| U3 | stream toggles/loops/intervals across iframe | 2/2/2 | 1/1/1 | **1/1/1** — GUI switch drives the sketch via postMessage | ✅ |
| U3 | sketch design system | disjoint dark/blue | Oracle tokens | **Oracle tokens** (cream/ink/rust/borders) | ✅ |
| U4 | inline GoogleFonts calls | 36 | ≤ 6 | **2** (both ButtonStyle textStyles, justified) | ✅ |
| U4 | hand-rolled Border.all card sites | 13 | ≤ 2 | **1** (inside OracleCard itself) | ✅ |
| U4 | lookup impls / markName ternaries / dead routes | 2 / 5 / 1 | 1 / 1 / 0 | **1 / 1 / 0** (remaining ternary uses a different fallback by design) | ✅ |
| U1 | live audit baseline (app-audit, 7 screens, 2 flows) | — | measured | **39 findings: 1×sev-4, 8×sev-3, 22×sev-2, 8×sev-1; task success 100%; verdict NOT READY** — audit/2026-08-05-1008/report.md | ✅ |
| U5 | after-evidence | — | captured | screens-after/ crawl on decluttered build: pills card gone, single status source confirmed | ✅ |
| all | pytest / flutter analyze / flutter test / GUI boot | 204 / — / — / 200 | green | **204 passed / No issues / 6 passed / 200** | ✅ |

*Target ≤4 counted only workspace literals; the 6 measured include the helper definition and one file owned by a parallel workstream.

## Top open UX findings (next round candidates, from audit/2026-08-05-1008/report.md)
1. **sev-4 F-001**: FluidNC offline toast — raw `IP:port`, no retry, not dismissible, inconsistent across tabs.
2. **sev-3**: no success feedback after action buttons (jog/home/start).
3. **sev-3**: operator-facing jargon ("Z up legacy") + remaining button-style inconsistency (5 styles → consolidate to 2).

---

# Round 4 (2026-08-05): top audit findings fixed

| Finding | Fix | Evidence | Status |
|---|---|---|---|
| F-001 sev-4 — raw IP:port offline toast, no recovery, not dismissible, inconsistent | One friendly sticky toast per offline transition ("Plotter offline — check power and WiFi. Use CONNECT…"), DISMISS button, technical detail demoted to caption + logs; dedup flag reset on reconnect | audit/2026-08-05-1008/screens-fixes/03_tests.png shows the new toast | ✅ |
| sev-3 — no success feedback on actions | Jog/home/pen/work-zero actions now confirm ("Homed X", "Jogged X +10mm", …); failures unchanged | context.py `fluidnc_action(success_message=…)` | ✅ |
| sev-3 — "Z up/down legacy" jargon | Renamed "Pen-up Z (mm)" / "Pen-down Z (mm)", tooltips keep the legacy explanation | calibration.py | ✅ |
| sev-3 — 5 ad-hoc button styles | Two shared helpers (primary/safe) + danger for E-STOP; `color=positive` inline count → 0 | ui.py + 6 workspaces | ✅ |
| Tests | — | 204 passed; GUI boot 200 | ✅ |

Next audit run computes the formal trend against audit/2026-08-05-1008/findings.json (expect F-001 and the three sev-3s → fixed).
