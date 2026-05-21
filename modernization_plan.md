# NejeDraw Current Stabilization And Modernization Plan

## Summary

Current checkout is no longer green. The repo now contains a partial modernization attempt that must be stabilized before continuing broader cleanup.

Current measured status:

- Git state: `plann.md` deleted; `pyproject.toml`, `uv.lock`, `config.py`, `gui_service.py`, `gui_support.py`, and `session_uploader.py` modified; `.github/`, `.pre-commit-config.yaml`, `.coverage`, `.hermes/pi_task_mypy.md`, and `modernization_plan.md` untracked.
- Python tests: failing during collection because `src/neje_oracle/session_uploader.py:68` contains literal `multi_line_replacement`.
- Mypy: blocked by two setup errors: invalid `[tool.mypy.overrides]` shape in `pyproject.toml`, and the same `session_uploader.py` syntax error.
- Complexity: still shows existing hotspots, plus `session_uploader.py` cannot be analyzed due syntax error.
- New CI/pre-commit files are not ready: Python CI uses `pytest --cov` without `pytest-cov`, masks failures with `|| true`/`continue-on-error`, ESP32 CI installs `espat:esp32` typo, and Flutter CI pins older `3.24.0` while local current is Flutter `3.41.6`.

## Key Changes

1. Stabilize the partial implementation first.
   - Replace the accidental `multi_line_replacement` line with the original intended `except Exception as exc:  # noqa: BLE001` block behavior.
   - Fix `pyproject.toml` mypy config using valid `[[tool.mypy.overrides]]` sections, or remove invalid module tables and keep a minimal global config.
   - Add missing dev dependency `pytest-cov` if CI keeps `pytest --cov`; otherwise use `coverage run -m pytest` consistently.
   - Add `.coverage` to `.gitignore` or remove it from the working tree before staging.

2. Repair the new CI workflows before treating them as modernization output.
   - Python CI must install `uv`, run `uv sync --extra dev`, and fail on `pytest`, coverage threshold, Ruff, and any configured hard gate.
   - Remove `continue-on-error` and `|| true` from required checks; use staged thresholds instead of ignored failures.
   - ESP32 CI must install `esp32:esp32`, install `ArduinoJson` and `NimBLE-Arduino`, and use `arduino-cli compile --fqbn esp32:esp32:esp32 <sketch>`.
   - Flutter CI should use stable Flutter without pinning below the repo’s current SDK, run from `public_gallery/`, and fail on `flutter analyze` and `flutter test`.

3. Finish the mypy cleanup with minimal, behavior-preserving changes.
   - Keep `GUI_DEFAULTS` compatibility, but stop scattering `cast(float, GUI_DEFAULTS[...])`; add typed helper accessors or typed constants in `gui_support.py`.
   - Replace the nested `float(float(float(...)))` in `gui_service.py` with one typed default access.
   - Keep the valid `config.py` return-type fix.
   - Fix `session_uploader.py`, `transport.py`, `firebase_io.py`, and plotter remote typing after tests are green.
   - Add a `PlotterRemote` protocol for the daemon dependency instead of forcing `_LocalOnlyPlotterRemote` into `FirebaseRemoteRepository`.

4. Continue staged quality hardening after green baseline.
   - Initial hard gates: Python tests pass, mypy config parses, coverage gate `65%`, Ruff check no syntax/config failures, Flutter analyze/test pass, ESP32 sketches compile.
   - Next ratchets: mypy zero errors, coverage `75%`, broad `except Exception` reduced to justified process/UI/thread boundaries, and no new `D` complexity functions.
   - Then refactor hotspots: `PlotterDaemon.run_cycle`, `gui_support` preview builders, `ThermalAutoprintService._process_pending`, `svg_normalizer` bbox logic, and `preflight` hardware checks.

## Test Plan

- Syntax/config smoke checks:
  - `python -m compileall src tests`
  - `python -c "import tomllib; tomllib.load(open('pyproject.toml','rb'))"`
  - `uv run mypy src/neje_oracle`
- Python verification:
  - `uv run pytest -q`
  - `uv run coverage run --source=src/neje_oracle -m pytest -q`
  - `uv run coverage report --fail-under=65`
  - `uv run ruff check src/neje_oracle tests`
- Frontend verification:
  - From `public_gallery/`: `flutter analyze`
  - From `public_gallery/`: `flutter test`
- Firmware verification:
  - `arduino-cli compile --fqbn esp32:esp32:esp32 ESP32-BTN_Printer/ESP32_BTN_Printer`
  - `arduino-cli compile --fqbn esp32:esp32:esp32 ESP32-BTN_Printer/ESP32_PrinterOnly`
  - `arduino-cli compile --fqbn esp32:esp32:esp32 ESP32-BTN_Printer/PrinterDiscovery`

## Assumptions

- Preserve all current local changes unless explicitly told to discard them.
- Treat the new `.github/` and `.pre-commit-config.yaml` files as draft work that should be corrected, not blindly accepted.
- Keep staged quality gates, but required CI jobs must fail when their staged threshold fails.
- Do not resume broad refactors until the syntax error, mypy config, tests, and workflow basics are repaired.
