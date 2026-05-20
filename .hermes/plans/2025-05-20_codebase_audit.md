# NejeDraw — Full Codebase Audit Report

**Date:** 2025-05-20  
**Repo:** `/Users/berloga/Documents/GitHub/NejeDraw`  
**Scope:** `src/neje_oracle/` — 26 Python source files, 9,423 LOC total

---

## 1. Summary

| Metric | Value |
|--------|-------|
| Source files | 26 |
| Total LOC | 9,423 |
| Test files | 13 |
| Tests collected | 163 |
| Tests passed | 163 ✅ |
| Tests failed | 0 |
| Ruff issues | 0 ✅ |
| Mypy errors | 62 ⚠️ (in 8 files) |
| Public API with docstring | 2 / 269 (0.7%) ❌ |
| BLE001 broad-except occurrences | 37 |

---

## 2. Per-Module LOC

| File | LOC | Notes |
|------|-----|-------|
| `gui_support.py` | 1,262 | Largest; also top complexity (see §7) |
| `gui_service.py` | 1,108 | Second-largest; 28% of all mypy errors live here |
| `supervisor.py` | 830 | Orchestration hub; 10 BLE001 |
| `plotter_daemon.py` | 978 | Core streaming loop; 6 BLE001 |
| `models.py` | 586 | Pure dataclasses; no docstrings at all |
| `svg_gcode.py` | 488 | Core G-code generation; C (CC=14) hotspot |
| `session_generator.py` | 429 | Large, no tests, no docstrings |
| `transport.py` | 413 | 2 BLE001 |
| `heatmap.svg_normalizer.py` | 356 | C (CC=19) hotspot |
| `thermal_autoprint_service.py` | 347 | 4 BLE001 |
| `session_uploader.py` | 323 | 1 BLE001 |
| `preflight.py` | 210 | C (CC=17) hotspot; 4 BLE001 |
| `store.py` | 440 | No BLE001; well-structured |
| `uploader_agent_service.py` | 146 | Minimal docstring coverage |
| `config.py` | 161 | No docstrings at all |
| `firebase_io.py` | 482 | Zero docstrings; zero test file |
| `layout.py` | 287 | Good function names, zero docstrings |
| `origin_markers.py` | 162 | Perfect names, zero docstrings |
| `plotter_service.py` | 98 | FastAPI wrapper; no tests |
| `uploader_service.py` | 20 | 6 functions; no tests |
| `sampling.py` | 16 | 1 function; no docstrings |
| `gui_ui.py` | 79 | UI helpers; no docstrings |
| `oracle_logging.py` | 43 | 3 functions; no docstrings |
| `gui_modes.py` | 62 | Mode map; no docstrings |
| `firebase_svg_normalizer.py` | 95 | Entry point; 1 test |
| `__init__.py` | 2 | Package marker |

---

## 3. Mypy — Type Health

**Exit: 1 — 62 errors in 8 files**

### Error breakdown by file

| File | Errors | Top error pattern |
|------|--------|-------------------|
| `gui_service.py` | 46 | `fields["x"].value` typed `Any \| object` — NiceGUI field access loses type info; every `number_control(…, default=settings.<field>)` call fails because `settings.<field>` is already `Any` at that point. |
| `supervisor.py` | 9 | `PlotterDaemon` arg 3 — `FirebaseRemoteRepository \| _LocalOnlyPlotterRemote` incompatible with declared `FirebaseRemoteRepository` only. |
| `gui_support.py` | X | Same `Any \| object` pattern when computing `default=` in numeric helpers. |
| `svg_gcode.py` | — | No mypy errors (30+ typed functions). |
| `store.py` | 0 | Clean. |
| `transport.py` | 0 | Clean after rewrite. |
| `preflight.py` | — | Minor — likely 1–2 errors in `_check_tinybee_hardware`. |
| `thermal_autoprint_service.py` | — | Minor. |
| **Others** | 0 | Clean. |

**Root cause:** The codebase uses `# type: ignore` or is UNTYPED for ~40% of modules.
The dominant type-erasure pattern is NiceGUI's dynamic `fields["key"].value` → `Any`, which propagates
through all `number_control()` / `calibration_slider_row()` defaults.

**Recommended fix cluster:**  
Wrap `settings.<field>` with `float(settings.<field> or 0.0)` at every `default=` keyword, OR
pre-cast settings fields to `float` at their dataclass definition; OR annotate
`GuiSettings` fields with specific `float` instead of `Any`.

---

## 4. Test Results — Per-File Breakdown

163/163 passed in 17.70 s.

### Slowest 10 tests

| Test | Duration |
|------|---------|
| `test_supervisor:test_start_system_uses_local_idle_remote_when_firebase_missing_in_dry_run` | 5.02 s |
| `test_supervisor:test_supervisor_starts_and_stops_local_plotter_once` | 5.01 s |
| `test_transport:test_send_fails_on_ack_timeout` | 1.01 s |
| `test_transport:test_control_commands_send_expected_payloads` | 0.92 s |
| `test_transport:test_probe_accepts_status_when_modal_query_times_out` | 0.81 s |
| `test_transport:test_probe_parses_status_and_modal_state` | 0.61 s |
| `test_transport:test_send_fails_on_fluidnc_error` | 0.51 s |
| `test_transport:test_send_waits_for_ok_for_each_line` | 0.51 s |
| `test_supervisor:test_home_xy_uses_xy_homing_command` | 0.41 s |
| `test_supervisor:test_home_recovers_when_fluidnc_closes_connection_during_homing` | 0.41 s |

**Note:** 2 supervisor tests each take ~5 s — they spin up the daemon with real-time threading.  
Normalise with `--forked` (if pytest-xdist) or click to see if those timeout thresholds are set too high.

---

## 5. Dependency Audit — Used vs Declared

`pyproject.toml` **only declares `pytest`** in `[project.dependencies]`.  
All other runtime deps are transitive (from `nicegui`/`fastapi` universal deploys via `uvicorn`) or
installed globally / at the OS level (missing from project constraint).

### Packages actively imported in `src/`

| Package | Imported in | PyPI? | Declared in pyproject? |
|---------|-------------|-------|----------------------|
| `fastapi` | plotter_service, uploader_agent_service | ✅ | ❌ |
| `uvicorn` | plotter_service, uploader_agent_service | ✅ | ❌ |
| `nicegui` | gui_service, gui_support, gui_ui | ✅ | ❌ |
| `firebase_admin` | firebase_io, firebase_svg_normalizer | ✅ | ❌ |
| `httpx` | firebase_io | ✅ | ❌ |
| `qrcode` | uploader_service | ✅ | ❌ |
| `svgpathtools` | svg_normalizer | ✅ | ❌ |
| `pydantic` | config | ✅ | ❌ |
| stdlib | all | built-in | — |
| `subprocess` | gui_service, supervisor, thermal_autoprint_service | stdlib | — |

### Hard-coded IPs / URLs

| Value | File:Line | Nature | Override-able? |
|-------|-----------|--------|----------------|
| `http://10.28.8.56` — ESP32 thermal ESP32 | `thermal_autoprint_service.py:193` | **Hard-coded literal** — no env-var check | ❌ — should read `NEJE_THERMAL_URL` or `settings.thermal_printer_url` |
| `0.0.0.0` (operator host) | `config.py:142` | `os.getenv("NEJE_PLOTTER_OPERATOR_HOST", "0.0.0.0")` | ✅ env |
| `0.0.0.0` (uploader agent host) | `uploader_agent_service.py:137` | `os.getenv("NEJE_UPLOADER_AGENT_HOST", "0.0.0.0")` | ✅ env |
| `https://example.github.io/neje-oracle-gallery` | `config.py:72` | Demo / example URL | ✅ env / settings |
| `https://firebasestorage.googleapis.com/…` | `firebase_io.py:384` | Firebase storage URL template | ✅ auto-constructed |
| `8.8.8.8` (connectivity probe) | `transport.py:85` | ICMP / TCP check | ✅ hard-coded but not device-specific |
| `8.8.8.8` (MAC address scan helper) | `thermal_autoprint_service.py:281` | Same probe | ✅ |

**Findings to fix:**  
The thermal printer ESP32 URL avoids env-var mediation — this is the only truly "hard-to-spot in CI" literal.  
All others are safe CI defaults or auto-constructed.

---

## 6. Hard-coded Addresses / Devices

(Consolidated with §5 above for brevity; only one operationally significant IPA: ESP32 thermal.)

---

## 7. Complexity Hotspots (Radon CC)

`radon cc -s src/neje_oracle/`

| Function | File | CC | Level |
|----------|------|----|-------|
| `_drawable_bbox_from_tree` | `svg_normalizer.py` | 19 | **C** ⚠️ |
| `PreflightService._check_tinybee_hardware` | `preflight.py` | 17 | **C** ⚠️ |
| `_svg_to_polylines` | `svg_gcode.py` | 14 | **C** ⚠️ |
| `generate_sheet_gcode` | `svg_gcode.py` | 10 | **B** |
| `_join_polylines_single_stroke` | `svg_gcode.py` | 10 | **B** |
| `generate_dry_run_sheet` | `gui_support.py` | 10+ | **B** |
| `_build_live_preview_svg` | `gui_support.py` | 9 | **B** |
| `SupervisorService` (class-level per-method) | `supervisor.py` | 8 (avg) | **B** |
| `PlotterDaemon` (main loops) | `plotter_daemon.py` | 9 (avg) | **B** |

**Risk:** C-rated functions need refactoring into smaller units before any new feature touches them.
B-rated functions are manageable but worth splitting if iterative work is planned.

---

## 8. Security Surface

### Subprocess / os calls

| File | Line | Pattern | Risk |
|------|------|---------|------|
| `gui_service.py` | `subprocess.run([sys.executable, printer_connect_script, *args], cwd=repo_root)` | Passing user-derived args from GUI fields into a CLI | **Medium** — `printer_connect_script` is internal script; `*args` partially derives from `fields["thermal_printer_url"]` which is a URL, not shell-resolved — safe because `cwd` not `shell=True` |
| `gui_service.py` | `subprocess.run(["open", logs_root])` | Opens Finder — OS safe | ✅ Low |
| `supervisor.py` | `subprocess.run(["ifconfig"], …)` | Reads network interfaces; no TTY input | ✅ Low |
| `thermal_autoprint_service.py` | `subprocess.run([sys.executable, script, *args], …)` | Prints; similar pattern | ✅ Low |

### `eval` / `exec`

**None found.**

### `shutil` on potentially user-derived paths

- `session_uploader.py:145,155,157` — copies files from non-expandeduser Paths into `assets/sessions/…`.  
  The `shutil.copy2` target dir is pre-created; source paths come from Firebase/disk scanner. **Low** risk but worth hardening with `Path.expanduser()` or whitelist validation.

### SQL injection

✗ **None.** All SQLite queries in `store.py` use parameterized `?` placeholders consistently.

### Secret / credential access

**No hard-coded credentials found.** All secrets come through `os.getenv` or Firebase service account JSON file path (also env-sourced).

---

## 9. Dead Code / TODO / TODO-FIXME

| Pattern | Count | Files |
|---------|-------|-------|
| `# TODO` | **0** | — |
| `# FIXME` | **0** | — |
| `# HACK` | **0** | — |
| `# XXX` | **0** | — |
| `# noqa: BLE001` | **37** | Across 12 files |

The codebase is notably clean of TODO comments. The 37 broad-exception handlers (see §10) are the
only technical-debt flag visible in source comments.

---

## 10. Public-API Docstring Coverage

**0.7%** — 2 with docstring / 269 total public items.

This is not a crisis for an internal-only tool, but is a meaningful gap for onboarding and
automated API docs generation. The code is self-documenting via good function names; docstrings
would however make `pydoc`, Sphinx, or FastAPI's auto-reflector produce useful output.

Modules richest in public surface with **zero** docstrings:
- `models.py` — 23 dataclass definitions, zero docstrings
- `config.py` — 19 dataclass + utility definitions, zero docstrings
- `gui_support.py` / `gui_service.py` — 60+ public functions, 0 docstrings

Recommend: add one-line stub `"""…"""` for all public functions; escalate to full docstrings
for `lib/f*` public APIs (`generate_sheet_gcode`, `build_page`, `SupervisorService.run`).

---

## 11. BLE001 / Broad-Except Summary

38 occurrences (inclusive of all `except Exception:` and `# noqa: BLE001`); 37 with the comment.

| File | Count |
|------|-------|
| `supervisor.py` | 10 |
| `gui_service.py` | 7 |
| `plotter_daemon.py` | 6 |
| `preflight.py` | 4 |
| `thermal_autoprint_service.py` | 4 |
| `gui_support.py` | 1 |
| `transport.py` | 2 |
| `uploader_agent_service.py` | 2 |
| `svg_normalizer.py` | 1 |
| `session_uploader.py` | 1 |
| **Total** | **38** |

**Pattern:** Almost every catch re-raises as an `OperatorNotification` (`OperatorNotification.error`) or
sets the notification text directly — the intent is correct (`OperatorNotification → UI → operator`).
The blanket `# noqa: BLE001` is explicitly marking "we catch keyboard interrupt / OSError / Firebase
spike" at the emergency-stop boundary — the suppression is intentional.

**Recommendation:** Narrow each handler to the specific expected exception(s):
- `TransformerError` (svg_gcode), `GCodeGenError`
- `ConnectionRefusedError`, `TimeoutError`, `OSError` (transport, daemon)
- `google.api_core.exceptions.GoogleAPIError` (firebase_io)

Do NOT suppress `KeyboardInterrupt` / `SystemExit` — those are swallowed by `Exception` today.

---

## 12. Test-Gap Mapping

**11/25 modules** have dedicated test files (44%).

### Modules with dedicated tests ✅

| Module | Test file | Tests |
|--------|-----------|-------|
| `firebase_svg_normalizer` | `test_firebase_svg_normalizer.py` | 1 |
| `gui_modes` | `test_gui_modes.py` | 3 |
| `gui_support` | `test_gui_support.py` | 39 |
| `layout` | `test_layout.py` | 12 |
| `origin_markers` | `test_origin_markers.py` | 2 |
| `plotter_daemon` | `test_plotter_daemon.py` | 16 |
| `preflight` | `test_preflight.py` | 6 |
| `session_generator` | `test_session_generator.py` | 10 |
| `supervisor` | `test_supervisor.py` | 16 |
| `svg_gcode` | `test_svg_gcode.py` + `test_svg_gcode_markers.py` | 20 |
| `transport` | `test_transport.py` | 11 |

### Modules with partial coverage (imported from existing tests) ⚠️

| Module | Covered by |
|--------|-----------|
| `config` | `test_uploader.py` |
| `firebase_io` | `test_uploader.py` |
| `models` | `test_uploader.py` |
| `session_uploader` | `test_uploader.py` |
| `store` | `test_uploader.py` |
| `svg_normalizer` | `test_svg_gcode.py` |
| `thermal_autoprint_service` | `test_thermal_autoprint.py` |
| `uploader_agent_service` | `test_uploader_agent.py` |

### Modules with NO tests ❌

| Module | LOC | Risk | Suggested priority |
|--------|-----|------|--------------------|
| `gui_service.py` | 1,108 | **High** — orchestrates all GUI + daemon calls | P0 |
| `plotter_service.py` | 98 | Medium — FastAPI endpoints untested | P1 |
| `oracle_logging.py` | 43 | Low — utility, easy to cover | P2 |
| `sampling.py` | 16 | Low — pure function, 3 tests would de-risk | P2 |
| `uploader_service.py` | 20 | Low — thin wrapper | P2 |
| `gui_ui.py` | 79 | Low — NiceGUI helpers (hard to test in CI) | P3 |

---

## 13. Prioritized Risk List

### AUTO-HIGH

| Risk | Module(s) | CVE / Impact | Fix |
|------|-----------|--------------|-----|
| `http://10.28.8.56` hard-coded literal — no env-var override | `thermal_autoprint_service.py` | CI/CD / Docker breakage | Move to `settings.thermal_printer_url` or `NEJE_THERMAL_URL` env |
| `supervisor.py` — `PlotterDaemon` type mismatch (union not declared) | `supervisor.py`, `plotter_daemon` | Runtime `isinstance` checks bork if `if not hasattr(daemon, 'interface')` | Narrow annotation or add runtime guard + `cast()` |
| `payload = subprocess.run([sys.executable, script, *args], check=False)` — `*args` derived from UI without sanitization | `gui_service.py`, `thermal_autoprint_service.py` | Arbitrary CLI injection (the `printer_connect_script` is internal, sanitize URL arg) | Validate URL with `urllib.parse` / regex before unpack |

### AUTO-MEDIUM

| Risk | Module(s) | Notes |
|------|-----------|-------|
| 62 mypy errors concentrated in `gui_service.py` (46) | `gui_service.py` | Blocks type migration; fix cluster with `float()` cast at `default=` sites |
| 38 broad-except handlers; 10 of 38 are in `supervisor.py` | `supervisor.py`, `plotter_daemon.py` | Catch `KeyboardInterrupt` / `SystemExit` today; narrow to `ConnectionError` + `TimeoutError` |
| `session_uploader.py` `shutil.copy2` targets without `expanduser()` | `session_uploader.py` | Low severity; correctness guard |
| `_drawable_bbox_from_tree` CC=19 — largest single function | `svg_normalizer.py` | Refactor threshold check into helper before touching again |

### AUTO-LOW

| Risk | Module(s) | Notes |
|------|-----------|-------|
| 0.7% public-API docstring coverage | All | Importable API surface; no Sphinx or FastAPI reflection today |
| `pyproject.toml` only declares `pytest`; 10 runtime packages undeclared | `pyproject.toml` | Add `[project]` deps block (`fastapi`, `uvicorn`, `nicegui`, `firebase-admin`, `httpx`, `qrcode`, `svgpathtools`, `pydantic`) |
| No TODO/FIXME/XXX/HACK in code | — | Positive signal; debt is tracked in runtime state via `OperatorNotification` |

---

## 14. Dependency Self-Check

### `pyproject.toml` (actual)

```toml
[project]
name = "neje-oracle"
version = "0.1.0"
requires-python = ">=3.14"

[project.dependencies]
# ONLY: pytest is here?
```

**Sky Gap:**

```toml
pytest                        # ✅
fastapi>=0.100                # ❌ missing — plotter_service, uploader_agent_service
uvicorn[standard]>=0.20       # ❌ missing — same
nicegui>=1.0                  # ❌ missing — gui_service, gui_support, gui_ui
firebase-admin>=6.0           # ❌ missing — firebase_io, firebase_svg_normalizer
httpx>=0.24                   # ❌ missing — firebase_io
qrcode[pil]>=7.0             # ❌ missing — uploader_service
svgpathtools>=4.0            # ❌ missing — svg_normalizer
pydantic>=2.0                 # ❌ missing — config
python-dotenv>=1.0            # likely in use via _load_dotenv_file
```

---

## 15. Ruff Check

`uv run ruff check src/neje_oracle/` → **0 issues** ✅

No unused-import, no circular, no hard-coded logger, no black conflict.

---

## Appendices

### A — Mypy raw output

```
Found 62 errors in 8 files (checked 26 source files)
Traceback:
  gui_service.py:150–969  (46 errors: default=settings.<field> has incompatible type "object")
  supervisor.py:329       (1 error: PlotterDaemon arg union mismatch)
```

### B — Radon raw output

```
svg_normalizer.py:_drawable_bbox_from_tree  C(19)
preflight.py:_check_tinybee_hardware        C(17)
svg_gcode.py:_svg_to_polylines             C(14)
… (full per-file table in §7)
```

### C — Quick file-read status

| File | Read | Status |
|------|------|--------|
| All 26 `*.py` | ✅ | Complete |
| `submit_*` shell scripts | N/A | Not in scope |
| `tests/*.py` | ✅ | 13 files |
