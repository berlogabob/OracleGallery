# Ponytail cuts: tracker (2026-11-23)

Branch `ponytail-cuts`, worktree `../NejeDraw-ponytail`, cut from `cb6741d`. One task per loop,
executed by a Haiku subagent, verified and committed by the coordinator. Full plan and rationale:
the approved plan of 2026-11-23; dispositions are mirrored in `DISPOSITION_REGISTER.md`.

## Baseline (T0, measured in the worktree)

| Metric | Command | Baseline | Final |
|---|---|---|---|
| src lines | `git ls-files src \| xargs wc -l \| tail -1` | 29868 | 29721 (-147) |
| tests | `uv run pytest -q` | 846 passed, 0 failed | 846 passed, 0 failed |
| coverage | `uv run coverage report` (gate >= 79) | 84% | 84%, gate passes |
| dead-code hits | `uvx vulture src scripts --min-confidence 60 \| grep -v -cE 'unused (variable\|attribute)'` | 20 | 16 (-4) |
| ruff | `uv run ruff check . && uv run ruff format --check .` | clean | clean |
| mypy | `uv run mypy src` | 12 errors in 5 files (pre-existing; gate: no more than 12) | 12 errors in 5 files (unchanged) |

## Tasks

| | ID | Task | Disposition | Done when | Commit | src lines after | Acceptance output |
|---|---|---|---|---|---|---|---|
| [x] | T0 | Worktree, baseline, tracker, register rows | n/a | baseline filled, suite green | this commit | 29868 | 846 passed |
| [x] | T1 | Delete `public_storage_url`, `default_filler_package_root`, `texture_to_svg`, `load_system_mode` | DELETE | `grep -rnw <name> src tests scripts` = 0 each; pytest, ruff green | 595b5fe | 29842 (-26) | greps 0/0/0/0; ruff clean; mypy 12; 198 passed |
| [x] | T2 | Delete `blocks/realtime_preview/` | DELETE | dir gone; `grep -rn realtime_preview src README.md RUNBOOK.md pyproject.toml` = 0; pytest green | 27a5d85 | 29836 (-6) | dir gone; grep 0; ruff clean; 96 passed |
| [x] | T3 | Delete duplicate `assets/WebsiteWireframe/Oracle Website Wireframes _standalone_.html` | DELETE | surviving copy md5 `bb1a4d0f02fb3be88b3e52f39ca7c384`; no reference to removed name | f63dd50 | 29836 (0) | kept copy md5 bb1a4d0f02fb3be88b3e52f39ca7c384; outer gone; 0 references outside this tracker |
| [x] | T4 | Remove `gui/modes.py`; importers use `shared.modes` | MERGE | file gone; `grep -rnE "gui\.modes\|from \.modes" src tests scripts` = 0; pytest green | 2a416f5 | 29821 (-15) | file gone; gui.modes grep 0; 'from .modes' in blocks/gui 0 (check scoped to blocks/gui: the original pattern also matched imaging/modes and shared/modes importers); ruff clean; mypy 12; tests passed |
| [x] | T5 | Collapse `mode_policy()` to one return | MERGE | `test_gui_modes.py`, `test_system_checks.py` pass unedited; `shared/modes.py` <= 50 lines | a52e599 | 29813 (-8) | tests pass unedited; ruff clean; modes.py 52 lines, not <= 50: the threshold was the coordinator's miscount, the specified shape yields 52 (was 60). Accepted at 52. |
| [x] | T6 | Remove `gui/support.py` re-export shim (sub-commits a, b, c) | MERGE | `grep -c "noqa: E402" support.py` = 0; `support.py` <= 215 lines; pytest, ruff green; mypy <= 12 | 957854a, aacfef4, 918cce2 | 29730 (-83) | noqa count 0; support.py 207 lines (<= 215); 5 gui modules import alone; full suite 846 passed; ruff clean; mypy 12 |
| [x] | T7 | `git mv ESP32-BTN_Printer/Grok-*.json archive/` | HIDE | no reference to old paths | ee03f2a | 29730 (0) | 2 files in archive/, 0 in ESP32-BTN_Printer/; md5 unchanged (2a9f4ec4…, 829c9a05…); 0 references to old paths |

## Marked for decision (no action taken)

| ID | Item | Why it is not cut |
|---|---|---|
| M1 | `ESP32_BTN_Printer.ino` (942 lines) vs `ESP32_PrinterOnly.ino` | 29 of 64 functions overlap by name; which sketch is flashed is a hardware fact, not a code fact |
| M2 | Test-only production functions: `is_printing`, `check_connection`, `parse_cell_progress_markers`, `preview_svg` (image.py), `_triangle_area`, `image_to_svg`, `png_to_field`, `image_to_motif_svg`, `text_svg`, `rename_material`, `get_session` | Tested capability; not certainly dead |
| M3 | `capture_z` in `gui/context.py` | Hardware path with one other reference |
| M4 | `ModePolicy.dry_run` / `real_output_required` are constant across modes | Removing them changes a public shape |
| M5 | 4-line `start_*.command` wrappers | Referenced by launcher installers; 8 lines |
| M6 | 4 of the 12 baseline mypy errors: `gui/context.py` ~284-288 reads `motif_gamma`, `motif_autocontrast`, `motif_invert`, which `GuiSettings` does not declare | Correctness, outside an over-engineering audit; needs a normal review. Present at cb6741d. |

## New issues found during the loops

| | ID | Found in | Issue | Disposition | Done when | Commit |
|---|---|---|---|---|---|---|
| [x] | N1 | T6a | `gui/settings_io.py` itself re-exports `load_symbol_scales` / `save_symbol_scales` from `shared/symbols.py` | MERGE | `grep -n "symbol_scales as" src/neje_oracle/blocks/gui/settings_io.py` = 0; importers use `shared.symbols`; pytest green | e27da2f (grep 0; 92 tests; 5 gui modules import alone) |
| [x] | N2 | T6a | `python -c "import neje_oracle.blocks.gui.preview"` alone fails with a circular ImportError; present at cb6741d, masked because `support` is always imported first | MERGE (expected to fall out of T6b) | that import exits 0 in a fresh process | aacfef4 (import exits 0) |

## Loop log

| Loop | Task | Worker | Result |
|---|---|---|---|
| 0 | T0 | coordinator | baseline recorded |
| 1 | T1 | haiku | pass first try; 2 orphaned imports in texture.py removed with it |
| 2 | T2 | haiku | pass first try; 3 doc mentions removed, roadmap sentence kept |
| 3 | T3 | haiku | pass first try |
| 4 | T4 | haiku | pass first try; acceptance pattern corrected by coordinator |
| 5 | T5 | haiku | pass; line threshold missed by 2 (estimate error, not worker error) |
| 6a | T6a | haiku | pass (957854a): 6 names re-pointed in 8 files, block deleted, support.py 288 -> 272; 123 tests pass, ruff clean, mypy 12. Raised N1 and N2. |
| 6b | T6b, N2 | haiku | pass (aacfef4): 4 preview names re-pointed in 3 files, 27-line block deleted, support.py 272 -> 245; all five gui modules import alone; 120 tests pass, ruff clean, mypy 12. N2 closed. |
| 6c | T6 | haiku | pass: 16 names re-pointed in 10 files, imports only. Worker ran rm -f on a mistyped path in the main checkout (.mypy_tail.txt); main checkout git status verified identical to session start. |
| 7 | T7 | haiku | pass first try |
| 8 | N1 | haiku | pass (e27da2f): 2 forwarding imports removed from settings_io, 3 importers re-pointed. Worker left 7 log files in /tmp; coordinator removed them. |
| 9 | final gate | coordinator | 846 passed; coverage 84%; ruff clean; mypy 12; dead-code hits 16; src 29721. No BLOCKED rows. Open: M1-M6 (decisions), merge of `ponytail-cuts`, `graphify update .` after merge. |

## Result

All T and N rows are closed; none blocked. Against `cb6741d`, excluding `planning/`: 30 files changed, 59 insertions, 393
deletions (src alone: 15 files, +25/-172). Three files removed (`gui/modes.py`, `realtime_preview/__init__.py`, its README),
one duplicate asset removed, two files moved to `archive/`. `gui.preview` now imports on its own, which it did not before.

Estimates that were off: the plan said about -130 src lines (actual -147), dead-code hits 19 to 15 (actual 20 to 16), and
`shared/modes.py` <= 50 lines (actual 52).
