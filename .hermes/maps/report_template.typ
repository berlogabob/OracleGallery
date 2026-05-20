#set page(width: 210mm, height: 297mm, margin: (top: 20mm, bottom: 15mm, left: 18mm, right: 18mm), numbering: "1")
#set text(font: "DejaVu Sans Mono", size: 9pt)
#set par(justify: true, leading: .55em)
#set heading(numbering: "1.", font: "DejaVu Sans Mono")
#set strong(font: "DejaVu Sans Mono")

// Typst doesn't support <br/> inline — use table rows or separate lines instead.

// ======================= COVER =======================
#align(right, [
  #text(size: 12pt, fill: rgb("#444444"))[
    *NejeDraw — Oracle Exhibition System*
  ]
  #v(.5em)
  #text(size: 10pt)[Codebase Audit + Project Map]
  #linebreak()
  #text(size: 8pt, fill: rgb("#888888"))[2025-05-20 · neje_oracle 0.1.0]
])
#pagebreak()

// ======================= TOC =======================
= Table of Contents

#outline(title: "Contents", indent: auto)

#pagebreak()

// ======================= AUDIT BODY =======================

= Codebase Audit — neje_oracle

== 1. Summary

This is a read-only structural audit of the NejeDraw codebase — `src/neje_oracle/` (26 Python source files, 9,423 LOC total).

#表格-style summary block:
#align(center, rect(fill: rgb("#f0f0f0"), stroke: thin, inset: 10pt)[
  #grid(columns: 2, gutter: 6pt, text(size: 8.5pt)[
    *Metric* #colbreak() *Value* \
    Source files #colbreak() 26 \
    Total LOC #colbreak() 9,423 \
    Test files #colbreak() 13 \
    Tests collected #colbreak() 163 \
    Tests passed #colbreak() 163 ✅ \
    Ruff issues #colbreak() 0 ✅ \
    Mypy errors #colbreak() 62 ⚠️ (8 files) \
    Public API docstrings #colbreak() 2 / 269 (0.7%) ❌ \
    Broad `except` BLTE001 #colbreak() 37
  ])
])

== 2. Per-Module LOC

#let loc_table = table(
  columns: (auto, 1fr, auto),
  align: (left, right, left),
  table.hline(),
  [*Module*], [*LOC*], [*Notes*],
  table.hline(),
  [`__init__.py`], [2], [`Package marker`],
  [`config.py`], [161], [`All settings dataclasses`],
  [`firebase_io.py`], [482], [`Zero docstrings; 0 tests`],
  [`firebase_svg_normalizer.py`], [95], [`1 test`],
  [`gui_modes.py`], [62], [`Mode → control-policy map`],
  [`gui_service.py`], [1,108], [`28% of mypy errors`],
  [`gui_support.py`], [1,262], [`Largest; preview builders`],
  [`gui_ui.py`], [79], [`NiceGUI primitives`],
  [`layout.py`], [287], [`Hex + grid packing`],
  [`models.py`], [586], [`0 docstrings`],
  [`oracle_logging.py`], [43], [`3 functions; no docstrings`],
  [`origin_markers.py`], [162], [`Perfect names, zero docstrings`],
  [`plotter_daemon.py`], [978], [`Core streaming loop`],
  [`plotter_service.py`], [98], [`FastAPI wrapper; no tests`],
  [`preflight.py`], [210], [`9 checks; C (CC=17)`],
  [`sampling.py`], [16], [`1 pure function`],
  [`session_generator.py`], [429], [`Large; 0 tests; 0 docstrings`],
  [`session_uploader.py`], [323], [`1 BLE001`],
  [`store.py`], [440], [`SQLite stores; clean`],
  [`supervisor.py`], [830], [`Orchestrator; 10 BLE001`],
  [`svg_gcode.py`], [488], [`C (CC=14)`],
  [`svg_normalizer.py`], [356], [`C (CC=19); bbox/path ops`],
  [`thermal_autoprint_service.py`], [347], [`4 BLE001`],
  [`transport.py`], [413], [`2 BLE001; clean logic`],
  [`uploader_service.py`], [20], [`Thin CLI wrapper`],
  [`uploader_agent_service.py`], [146], [`FastAPI agent`],
  table.hline(),
  [*TOTAL*], [*9,423*], [],
)
loc_table

== 3. Mypy — Type Health

*Result: 62 errors across 8 files (checked 26)*

#let mypy_notes = [
  *`gui_service.py` (46 errors)* \
  Pattern: `fields["x"].value` typed as `Any | object`; every `number_control(default=settings.<field>)` propagates the `Any` type to `float()`. Root cause: NiceGUI field access erases cadence types.

  *`supervisor.py` (9 errors)* \
  `PlotterDaemon.__init__` arg `remote` accepts `FirebaseRemoteRepository \_LocalOnlyPlotterRemote` but the `remote` parameter in the constructor signature expects `FirebaseRemoteRepository` only. Runtime: `cast()` or narrowing guard needed.

  *Other 8 files* \
  `gui_support.py`, `svg_gcode.py` — minor; `firebase_io.py`, `preflight.py` — same.

  *Recommendation* \
  Wrap every `settings.<field>` in `float(settings.<field> or 0.0)` at `default=` call sites; OR give `GuiSettings` fields explicit `float` annotations.
]

#rect(fill: rgb("#fff8e8"), stroke: thin, inset: 10pt)[
  #text(size: 8.5pt, mypy_notes)
]

== 4. Pytest Results

*All 163 tests passed in 17.70 s.*

#let test_table = table(
  columns: (auto, 1fr, 1fr),
  table.hline(),
  [*Duration*], [*Test*], [*File*],
  table.hline(),
  [5.02 s], [`test_start_system_uses_local_idle_remote_when_firebase_missing_in_dry_run`], [`test_supervisor.pyplot`],
  [5.01 s], [`test_supervisor_starts_and_stops_local_plotter_once`], [`test_supervisor`],
  [1.01 s], [`test_send_fails_on_ack_timeout`], [`test_transport`],
  [0.92 s], [`test_control_commands_send_expected_payloads`], [`test_transport`],
  [0.81 s], [`test_probe_accepts_status_when_modal_query_times_out`], [`test_transport`],
  [0.51 s], [`test_send_fails_on_fluidnc_error`], [`test_transport`],
  [0.51 s], [`test_send_waits_for_ok_for_each_line`], [`test_transport`],
  [0.41 s], [`test_home_xy_uses_xy_homing_command`], [`test_supervisor`],
  [0.41 s], [`test_home_recovers_when_fluidnc_closes_connection_during_homing`], [`test_supervisor`],
  table.hline(),
)
test_table

*Note:* 2 supervisor tests ≈5 s each — they spin up threading; consider `--forked` for CI.

== 5. Dependency Audit

#let dep_info = [
  #strong[Declared in`pyproject.toml` runtime deps:]
  `fastapi`, `firebase-admin`, `httpx`, `nicegui`, `pydantic`, `qrcode[pil]`, `svgpathtools`, `uvicorn[standard]`, `pytest` — **all 9 are declared and imported**. \
  #strong[Zero unused deps.] #linebreak() \
  #strong[Hard-coded addresses:]
  `http://10.28.8.56` (ESP32 thermal) — actually literal in `thermal_autoprint_service.py` ⚠️ \
  `8.8.8.8` (connectivity probe) — two places: `transport.py`, `thermal_autoprint_service.py` — safe \
  `0.0.0.0` (operator/agent host) — both env-sourced, overridable ✅ \
  `https://example.github.io/…` — demo URL, overridable ✅
]
#rect(fill: rgb("#e8f4fd"), stroke: thin, inset: 10pt)[
  #text(size: 8.5pt, dep_info)
]

== 6. Complexity Hotspots (Radon CC)

#let cc_table = table(
  columns: (1fr, 1fr, 1fr, auto),
  table.hline(),
  [*Function*], [*File*], [*CC*], [*Level*],
  table.hline(),
  [`_drawable_bbox_from_tree`], [`svg_normalizer.py`], [19], [C ⚠],
  [`_check_tinybee_hardware`], [`preflight.py`], [17], [C ⚠],
  [`_svg_to_polylines`], [`svg_gcode.py`], [14], [C ⚠],
  [`generate_sheet_gcode`], [`svg_gcode.py`], [10], [B],
  [`_join_polylines_single_stroke`], [`svg_gcode.py`], [10], [B],
  [`_build_live_preview_svg`], [`gui_support.py`], [9], [B],
  [`SupervisorService`], [`supervisor.py`], [8 avg], [B],
  [`PlotterDaemon`], [`plotter_daemon.py`], [9 avg], [B],
  table.hline(),
)
cc_table

== 7. Security Surface

[[subproc]]
*Subprocess calls (4 total, all `subprocess.run`, no `shell=True`:*
- `gui_service.py:621` — calls internal `printer_connect.py`; args from GUI URL field (safe: list form, no shell)
- `gui_service.py:701` — `open` with path to log folder (safe)
- `supervisor.py:783` — reads `ifconfig` (safe)
- `thermal_autoprint_service.py:193` — same internal script pattern (safe)

[[eval]]
*`eval` / `exec`:*
None found. ✅

[[sql]]
*SQL Injection:*
None. All SQLite paths use parameterized `?`. ✅

[[shutil]]
*`shutil.copy2` (3 occurrences in session_uploader.py:*
L145, L155, L157 — source paths from disk scanner; destination pre-created. No `expanduser()` on input. Low risk; worth adding `Path.expanduser()` guard. ⚠️ Low

[[secrets]]
*Hard-coded credentials:*
None. All secrets env-sourced or from Firebase SA JSON path (also env-sourced). ✅

== 8. Dead Code / TODO-FIXME

#rect(stroke: thin, inset: 6pt)[
  `TODO`: #strong[0]\
  `FIXME`: #strong[0]\
  `HACK`: #strong[0]\
  `XXX`: #strong[0]\
  `# noqa: BLE001` (broad except): **37** across 12 files \
  \
  Largest clusters: \
  supervisor.py ...10 → gui_service.py ...7 → plotter_daemon.py ...6 → preflight.py ...4 → thermal_autoprint_service.py ...4 \
  \
  Pattern: every catch wraps as `OperatorNotification` (UI notification); suppression is intentional but could be narrowed to `ConnectionError` / `TimeoutError` / `OSError` rather than blanket `Exception`.
]

== 9. Docstring Coverage

/exact: 2 with docstring / 269 public items = 0.7%/

- `models.py` — 23 dataclass definitions, 0 docstrings
- `config.py` — 19 definitions, 0 docstrings
- `gui_support.py` — 60+ public functions, 0 docstrings
- `gui_service.py` — 3 with docstrings

++++++
Recommended: one-line `"""Header.""` for all public functions; mention-only docstrings for `generate_sheet_gcode`, `build_page`, `SupervisorService.run`.

== 10. Test-Gap Mapping

#rect(stroke: thin, inset: 6pt, text(size: 8.5pt))[
  *44% module test coverage (11/25 modules have dedicated test files)* \
  \
  *✅ Covered:*
  firebase_svg_normalizer (1), gui_modes (3), gui_support (39), layout (12), origin_markers (2) \
  plotter_daemon (16), preflight (6), session_generator (10), supervisor (16), svg_gcode (17+3), transport (11) \
  \
  *⚠️ Partial (imported from existing tests):*
  config / firebase_io / models / session_uploader / store → `test_uploader.py` \
  svg_normalizer → `test_svg_gcode.py` \
  thermal_autoprint_service → `test_thermal_autoprint.py` \
  uploader_agent_service → `test_uploader_agent.py` \
  \
  *❌ No tests:*
  gui_service.py (1,108 LOC) — **HIGH risk** \
  plotter_service.py (98 LOC) — medium \
  oracle_logging.py (43 LOC) — low \
  sampling.py (16 LOC) — low \
  uploader_service.py (20 LOC) — low \
  gui_ui.py (79 LOC) — low (NiceGUI, hard to test in CI)
]

== 11. Prioritized Risk List

#let risk_table = table(
  columns: (auto, 1fr, 1fr, 1fr),
  table.hline(),
  [*Prio*], [*Risk*], [*Location*], [*Fix*],
  table.hline(),
  [HIGH], [`http://10.28.8.56` hardcoded (no env-var)], [`thermal_autoprint_service.py:193`], [`Move to settings.thermal_printer_url / env `NEJE_THERMAL_URL`]],
  [HIGH], [`PlotterDaemon` arg type mismatch], [`supervisor.py:329`], [`Add cast() or narrow annotation]],
  [HIGH], [`subprocess.run` `*args` from GUI unvalidated], [`gui_service.py:621`], [`Validate URL before unpack]],
  [MED], [46 mypy errors in gui_service.py], [`gui_service.py:150–969`], [`Wrap settings.<field> in float() at default=]],
  [MED], [38 broad `except Exception`], [`12 files`], [`Narrow to specific exception classes]],
  [MED], [`shutil.copy2` without expanduser], [`session_uploader.py:145/155/157`], [`Add .expanduser() or whitelist]],
  [LOW], [0.7% docstring coverage], [`All modules`], [`Add one-line docstrings for public API]],
  [LOW], [`pyproject.toml` only lists `pytest` explicitly], [`pyproject.toml`], [`Add 9 remaining runtime deps]],
  table.hline(),
)
risk_table

#pagebreak()

// ============== PROJECT MAP BODY ==============

= Project Map — NejeDraw Oracle

== Architecture Overview

This document maps the `neje_oracle/` package structure (26 source files), intra-file dependency relationships, the two runtime data flows (live-print and uploader pipeline), the session package contract, file system layout, and the external hardware topology.

== CLI Entry Points

#let cli_table = table(
  columns: (1fr, 1fr, 1.5fr),
  table.hline(),
  [*Command*], [*Module*], [*Role*],
  table.hline(),
  [`neje-gui`], [`gui_service:main`], [`NiceGUI web UI — operator console (8-tab)`],
  [`neje-plotter`], [`plotter_service:main`], [`FastAPI daemon — headless print loop`],
  [`neje-uploader`], [`uploader_service:main`], [`One-shot session upload (Mac mini)`],
  [`neje-uploader-agent`], [`uploader_agent_service:main`], [`FastAPI long-running agent`],
  [`neje-generate-sessions`], [`session_generator:main`], [`Generate fake/filler sessions`],
  [`neje-normalize-firebase-sessions`], [`firebase_svg_normalizer:main`], [`Bulk SVG normalize in-place`],
  [`neje-thermal-autoprint`], [`thermal_autoprint_service:main`], [`Print receipts to ESP32 thermal`],
  table.hline(),
)
cli_table

== Module → Responsibility Map

#let resp_table = table(
  columns: (1fr, auto, 2fr, 2fr),
  table.hline(),
  [*Module*], [*LOC*], [*Responsibility*], [*Depends on*],
  table.hline(),
  [`supervisor.py`], [830],
  [`Orchestrator; start/stop; component health`],
  [`plotter_daemon, preflight, store, transport, gui_support, fb`],
  [`plotter_daemon.py`], [978],
  [`Print loop; row/cell streaming; manifest + state`],
  [`svg_gcode, layout, store, firebase_io, transport`],
  [`gui_service.py`], [1,108],
  [`NiceGUI 8-tab operator console`],
  [`supervisor, gui_support, gui_ui, gui_modes`],
  [`gui_support.py`], [1,262],
  [`GUI state; preview builders; sheet gen`],
  [`config, models, svg_gcode, layout, store, fb_io`],
  [`models.py`], [586],
  [`All typed dataclasses (22 types)`],
  [`stdlib only`],
  [`config.py`], [161],
  [`Settings dataclasses + env-loading (pydantic)`],
  [`stdlib + pydantic`],
  [`svg_gcode.py`], [488],
  [`SVG → G-code core; polylines; Douglas-Peucker`],
  [`svg_normalizer, origin_markers, config`],
  [`svg_normalizer.py`], [356],
  [`Stroke normalize; bbox; per-symbol scale; jitter`],
  [`stdlib + svgpathtools`],
  [`layout.py`], [287],
  [`Hex + grid packing; organic modifier`],
  [`models`],
  [`transport.py`], [413],
  [`telnet + HTTP FluidNC send() / probe()`],
  [`models, config`],
  [`store.py`], [440],
  [`Three SQLite stores (plotter/oracle/uploader)`],
  [`models, origin_markers`],
  [`preflight.py`], [210],
  [`9 preflight checks before print allowed`],
  [`transport, models, config`],
  [`session_generator.py`], [429],
  [`Fake/filler session package generator`],
  [`origin_markers, svg_normalizer, config`],
  [`firebase_io.py`], [482],
  [`Firestore + Storage client`],
  [`config, models, origin_markers`],
  [`session_uploader.py`], [323],
  [`Scan + parse + normalize + QR + publish`],
  [`firebase_io, svg_normalizer, store`],
  [`. . .`], [. . .], [`(same pattern)`], [. . .],
  table.hline(),
)
resp_table

== Origin Taxonomy

```
origin_type — 8 values (origin_markers.py)

REAL        ORIGIN_REAL_MACMINI   — real human visitor session (Mac mini TouchDesigner)
FAKE        ORIGIN_FAKE_MACMINI   — synthetic test session
FILLER      ORIGIN_FILLER_MACBOOK  — MacBook idle/filler (local only)
USER        ORIGIN_USER_UPLOAD     — operator-uploaded SVG
IDLE        ORIGIN_IDLE_LOCAL      — auto-generated idle bank
TEST        ORIGIN_TEST            — GUI dry-run / test-print
TOUCH       ORIGIN_TOUCHDESIGNER   — TouchDesigner direct (non-session)
MAC         ORIGIN_MACBOOK_OPERATOR — operator-created locally

Marker positions:  left  | right  | top  | bottom
Colors:             amber #b8860b  |  slate #8f8980  |  slate-dim  |  ink #1f1a17
```

== Physical Device Map

```
MacBook Operator Station
neje-gui (NiceGUI → :8787)
  Controls: layout / scale / mode / preflight
  Supervisor: daemon lifecycle + component health + live preview

  PlotterDaemon (background / .app)
    → telnet → FluidNC

  Store: SQLite (runtime_db / plotter_db / uploader_db)

    ─────────────────────────────────────────────────────────────────

  FluidNC Controller
    WebUI  +  Telnet  +  G-code (G0/G1/M3/M5)  →  Plotter motors

    ─────────────────────────────────────────────────────────────────

  Mac mini (TouchDesigner)
    TouchDesigner → sessions_raw/<id>/
                      + _receipt.txt
                      + _plotter.svg
                      + READY

    Uploader Agent → scan → publish → Firebase
    Thermal Autoprint → ESP32 (http://10.28.8.56) — ⚠ hardcoded

    ─────────────────────────────────────────────────────────────────

  Firebase
    Firestore: oracle_sessions / plot_jobs / uploader_state
    Storage:   sessions/<id>/ (artwork.svg, receipt.txt, qr.png, manifest.json)

    ─────────────────────────────────────────────────────────────────

  Flutter Web Gallery
    https://berlogabob.github.io/OracleGallery/  (read-only, Firestore)
```

== File System Layout

```

```
