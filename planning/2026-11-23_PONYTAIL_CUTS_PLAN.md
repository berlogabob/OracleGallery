# Ponytail cuts: tracker (2026-11-23)

Branch `ponytail-cuts`, worktree `../NejeDraw-ponytail`, cut from `cb6741d`. One task per loop,
executed by a Haiku subagent, verified and committed by the coordinator. Full plan and rationale:
the approved plan of 2026-11-23; dispositions are mirrored in `DISPOSITION_REGISTER.md`.

## Baseline (T0, measured in the worktree)

| Metric | Command | Baseline | Final |
|---|---|---|---|
| src lines | `git ls-files src \| xargs wc -l \| tail -1` | 29868 | |
| tests | `uv run pytest -q` | 846 passed, 0 failed | |
| coverage | `uv run coverage report` (gate >= 79) | 84% | |
| dead-code hits | `uvx vulture src scripts --min-confidence 60 \| grep -v -cE 'unused (variable\|attribute)'` | 20 | |
| ruff | `uv run ruff check . && uv run ruff format --check .` | clean | |
| mypy | `uv run mypy src` | 12 errors in 5 files (pre-existing; gate: no more than 12) | |

## Tasks

| | ID | Task | Disposition | Done when | Commit | src lines after | Acceptance output |
|---|---|---|---|---|---|---|---|
| [x] | T0 | Worktree, baseline, tracker, register rows | n/a | baseline filled, suite green | this commit | 29868 | 846 passed |
| [ ] | T1 | Delete `public_storage_url`, `default_filler_package_root`, `texture_to_svg`, `load_system_mode` | DELETE | `grep -rnw <name> src tests scripts` = 0 each; pytest, ruff green | | | |
| [ ] | T2 | Delete `blocks/realtime_preview/` | DELETE | dir gone; `grep -rn realtime_preview src README.md RUNBOOK.md pyproject.toml` = 0; pytest green | | | |
| [ ] | T3 | Delete duplicate `assets/WebsiteWireframe/Oracle Website Wireframes _standalone_.html` | DELETE | surviving copy md5 `bb1a4d0f02fb3be88b3e52f39ca7c384`; no reference to removed name | | | |
| [ ] | T4 | Remove `gui/modes.py`; importers use `shared.modes` | MERGE | file gone; `grep -rnE "gui\.modes\|from \.modes" src tests scripts` = 0; pytest green | | | |
| [ ] | T5 | Collapse `mode_policy()` to one return | MERGE | `test_gui_modes.py`, `test_system_checks.py` pass unedited; `shared/modes.py` <= 50 lines | | | |
| [ ] | T6 | Remove `gui/support.py` re-export shim (sub-commits a, b, c) | MERGE | `grep -c "noqa: E402" support.py` = 0; `support.py` <= 215 lines; pytest, ruff green; mypy <= 12 | | | |
| [ ] | T7 | `git mv ESP32-BTN_Printer/Grok-*.json archive/` | HIDE | no reference to old paths | | | |

## Marked for decision (no action taken)

| ID | Item | Why it is not cut |
|---|---|---|
| M1 | `ESP32_BTN_Printer.ino` (942 lines) vs `ESP32_PrinterOnly.ino` | 29 of 64 functions overlap by name; which sketch is flashed is a hardware fact, not a code fact |
| M2 | Test-only production functions: `is_printing`, `check_connection`, `parse_cell_progress_markers`, `preview_svg` (image.py), `_triangle_area`, `image_to_svg`, `png_to_field`, `image_to_motif_svg`, `text_svg`, `rename_material`, `get_session` | Tested capability; not certainly dead |
| M3 | `capture_z` in `gui/context.py` | Hardware path with one other reference |
| M4 | `ModePolicy.dry_run` / `real_output_required` are constant across modes | Removing them changes a public shape |
| M5 | 4-line `start_*.command` wrappers | Referenced by launcher installers; 8 lines |

## New issues found during the loops

| | ID | Found in | Issue | Disposition | Done when | Commit |
|---|---|---|---|---|---|---|

## Loop log

| Loop | Task | Worker | Result |
|---|---|---|---|
| 0 | T0 | coordinator | baseline recorded |
