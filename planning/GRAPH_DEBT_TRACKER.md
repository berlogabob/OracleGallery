# Graph-Debt Tracker

Source: graphify knowledge-graph audit of 2026-08-04 (baseline graph: 1,753 nodes / 4,756 edges / 109 communities).
Branch: `graph-debt`. Status legend: ⏳ pending · 🔄 in progress · ✅ done.

| # | Metric | Baseline (2026-08-04) | Target | Actual | Status |
|---|--------|-----------------------|--------|--------|--------|
| W1 | `blocks/gui/support.py` LOC | 1,298 | ≤ 800 | **798** (+ preview.py 504, settings_io.py 82) | ✅ |
| W1 | tests passing | 202 | all green | **204 passed** (202 + 2 new geometry tests) | ✅ |
| W2 | contradictory working-area claims | 3 docs disagree (255×420 vs 255×440 vs 250×440) | 0 — GEOMETRY.md single source | **0** — GEOMETRY.md authoritative; root README links it. *(Corrected 2026-08-07 to 255×440 — see the resolved item below; this row originally recorded 255×420.)* | ✅ |
| W2 | sheet-vs-travel guard test | none | 1 test tracking sheet against Y travel | **3 tests** in `tests/test_geometry_consistency.py` (width fits; GUI and runtime defaults agree; 440mm sheet in 440mm travel leaves zero margin for the work-zero offset) | ✅ |
| W3 | INFERRED graph edges audited | 0/22 flagged (16 unique after dedup) | all verdicts with file:line evidence | **16/16**: 1 CORRECT, 15 WRONG (LLM mistook injected test doubles for real deps); root cause fixed in Round 2 (F1) by excluding `tests/`/`docs/` from the graph | ✅ |
| W4 | dead block stubs | 1 (`blocks/direct_print/`) | 0 | **0** — deleted, references cleaned, `grep -r direct_print src tests` empty | ✅ |
| info | god-node degree GuiSettings / SupervisorService / GuiContext | 89 / 83 / 78 | re-measured post-refactor | **92 / 83 / 78** (graph 2026-08-04b: 1,780 nodes / 4,828 edges / 114 communities) | ✅ |

## Reading the informational row

The W1 split reduced *file-level* debt (support.py −500 LOC) but, as expected for a mechanical extraction, did not reduce *class-level* coupling: `GuiSettings`'s degree even rose slightly (re-export edges from the two new modules). Actually shrinking the god **classes** (`GuiSettings`, `GuiContext`) would require an interface-level refactor — deliberately out of scope here; candidate for a future workstream.

## ~~Open item carried forward~~ — RESOLVED 2026-08-07

- **Hardware verification**: ~~is the physical Y travel really 420mm, or was the machine modified for 440mm sheets?~~ **Answered on the machine, 2026-08-07.** Y travel is **440 mm**, homing negative to 0, measured against the running FluidNC controller (`$CD` dump and `$SS` boot log) and cross-checked with `echodraw/hardware/configs/config.yaml`. The 420 figure came from a pre-servo draft config that was never flashed; `assets/tinybee.json` was correct all along.
  - **There is no 20 mm overshoot.** `echodraw/hardware/GEOMETRY.md` was rewritten with the measured values, and `tests/test_geometry_consistency.py` now carries `HARDWARE_TRAVEL_Y_MM = 440.0` with a comment recording that the old overshoot assertion was wrong.
  - The real constraint is tighter than a margin check: the default 250×440 sheet fits Y **exactly**, so sheet height *plus the work-zero offset* must stay within travel. With G54 at machine (5, 5) only 435 mm of Y remains. `test_default_sheet_height_has_no_y_margin` pins this.
  - This item stayed marked open for six days after it was answered, so the knowledge graph kept reporting it as a live question. Recording the resolution here is what removes it.

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

---

# Round 5 (2026-08-11): graph re-measured after the pattern-bank / pen-profile work

Graph: 1,733 nodes / 3,979 edges / 125 communities. Import cycles: **none**. Graph health: OK
(no dangling, missing, or collapsed edges).

| # | Metric | Round 2 (2026-08-05) | Now | Status |
|---|--------|----------------------|-----|--------|
| G1 | god-node degree `GuiContext` | 77 | **86** (+9) | ⏳ regressed |
| G1 | god-node degree `SupervisorService` | 54 | **60** (+6) | ⏳ regressed |
| G1 | god-node degree `GuiSettings` | 36 | **47** (+11) | ⏳ regressed |
| G1 | god-node degree `ComponentState` | 45 | **44** (−1) | ✅ flat |
| G2 | stale open item propagated into the graph | 1 (Y-travel, resolved 2026-08-07) | **0** — recorded above | ✅ |
| G3 | GUI controls bound to a `GuiSettings` field that never persist | 1 (`pen_width_mm`, silent for months) | **0**, and guarded by a test | ✅ |
| — | import cycles | 0 | **0** | ✅ |

## Why the god nodes grew

Two `GuiSettings` fields (`pen_down_dwell_ms`, `pen_profile`), the new
`shared/pen_profiles.py` which reads and writes them, `ctx.generate_pen_cal`, and the pen
pulls added to `pull_settings_from_fields` — plus the four drawing modes and the
frame-sheet work landed between the two measurements. Feature growth landing on the same
three classes, which is precisely the coupling Round 1 predicted the file split would not
fix (see "Reading the informational row" above).

**Still deliberately not refactoring them.** Shrinking the god *classes* needs an
interface-level change and belongs in its own workstream, with the graph measured before
and after. Recording the trend is the point of this row.

## What was done instead (G3)

`pull_settings_from_fields` is a hand-written field-by-field copy; a control missing from
it silently never persists, which is exactly how `pen_width_mm` ended up with a value on
`GuiSettings` and no working control. Measured across every workspace: 32 controls bind to
a `GuiSettings` field and all 32 now round-trip.

`test_every_gui_control_survives_a_settings_round_trip` in `tests/test_gui_workspaces.py`
now builds every workspace, writes a probe into each such control, and asserts it survives
the pull. That makes the failure mode impossible to ship without touching the god class —
the cheap half of the refactor, taken now.

## Open debt: the lift_budget triple-write path (feat/raw-artifacts)

The pen-lift budget is one operator concept written along three independent paths: the
IMAGE workspace passes it as a mode kwarg (`blocks/gui/workspaces/image.py` →
`blocks/imaging/modes.py`), the SKETCH workspace stamps it into the SVG as
`data-neje-lift-budget` (`blocks/gui/workspaces/generative.py::stamp_lift_budget`), and
`blocks/gcode/svg_gcode.py::_pen_lift_budget` re-parses that attribute at G-code time.
All three must agree on the `>= 1024 = off` sentinel; today a test pins each leg, but a
fourth print path would have to remember to join the convention by hand. Debt: fold the
sentinel + stamp/parse pair into one shared helper (natural home: `shared/pathops.py`)
before a new print path appears.
