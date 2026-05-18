# Hermes Plan: Calibration G-code Density, Filler Production, And Cell Streaming

## Summary
- Add a Calibration-tab “G-code optimisation” section that controls SVG point density.
- Link point density to cell diameter: bigger cells produce smaller point spacing, so curves get more points and finer line precision.
- Keep production filler flow based on `Generate next filler`, not batch idle/filler banks.
- Phase symbol-by-symbol plotting safely: first keep row streaming stable, then add guarded cell streaming as the production path.
- Hide old batch generation from operator workflows now; prune old helpers only after symbol streaming is verified.

## Hermes / Goose Orchestration
- Hermes should create one goose task per subsystem, in this order:
  1. `calibration-density-controls`
  2. `effective-gcode-sampling`
  3. `hide-batch-generation-ui`
  4. `cell-streaming-mode`
  5. `dead-code-audit-and-prune-candidates`
  6. `test-and-report`
- Goose must work inside `/Users/berloga/Documents/GitHub/NejeDraw`.
- Goose must not revert existing dirty changes; inspect before editing because this tree already contains Mac mini uploader, preview, QR, filler, SVG, and Firebase changes.
- Each goose task should return changed files, test commands run, and remaining risks.

## Key Changes
- Calibration settings:
  - Add `sample_step_mm`, `sample_reference_cell_mm`, `sample_density_exponent`, `sample_min_step_mm`, and `sample_max_step_mm` to `GuiSettings` and `PlotterRuntimeConfig`.
  - Add a new Calibration card named `G-code optimisation`.
  - User-facing controls:
    - `Point spacing @ 80mm`, default `1.0`
    - `Cell density link`, default `1.0`, range `0.0..2.0`
    - `Min point spacing`, default `0.25`
    - `Max point spacing`, default `3.0`
  - Persist these values through `runtime/gui_settings.json` and `OracleRuntimeStore.save_plotter_config`.

- Sampling behavior:
  - Replace direct use of `PlotterSettings.sample_step_mm` in plotter runtime with config-derived effective spacing.
  - Formula:
    `effective_sample_step_mm = clamp(sample_step_mm * (sample_reference_cell_mm / cell_diameter_mm) ** sample_density_exponent, sample_min_step_mm, sample_max_step_mm)`
  - This makes `cell_diameter_mm > 80` produce denser G-code and `cell_diameter_mm < 80` produce lighter G-code.
  - Write `effective_sample_step_mm` and raw optimisation settings into the sheet manifest for debugging.

- Production filler flow:
  - Keep `Generate next filler` as the production fallback source when no real Mac mini sessions are pending.
  - Remove or hide operator-facing batch idle/filler generation controls from GUI production/test workflow.
  - Keep old batch helpers temporarily if tests/preflight still depend on them, but mark them non-production in code comments or report notes.

- Cell streaming mode:
  - Add a runtime config field such as `streaming_mode`, defaulting to `row` for compatibility first.
  - Implement `cell` mode behind that switch:
    - Build full calibration grid once.
    - Claim or generate exactly one item per next cell.
    - Generate G-code for one `SheetItem` and one `SheetPlacement`.
    - Send it as `sheet_<id>_cell_<index>.gcode`.
    - Update manifest after each cell, not only after each row.
  - After tests pass, set GUI production/exhibition default to `cell`; keep row mode available as fallback during testing.

- Dead/redundant code audit:
  - Identify old batch-only code: idle bank preflight, `generate_idle_symbols`, `create_idle_bank_from_gui`, `create_filler_packages_from_gui`, live fake session generator, generated idle/filler asset roots.
  - First hide production access and update wording so operators only see real queue plus `Generate next filler`.
  - Only delete helpers/tests when no CLI, preflight, or fallback path still imports them.

## Test Plan
- Add unit tests for effective sample spacing:
  - `80mm` cell keeps default `1.0mm`.
  - Bigger cell, for example `160mm`, produces denser spacing.
  - Min/max clamps are honored.
- Add GUI support tests:
  - G-code optimisation values persist and load.
  - `gui_settings_to_plotter_config` carries optimisation fields.
- Add plotter tests:
  - Manifest includes optimisation settings and effective sample spacing.
  - Row mode still passes existing tests.
  - Cell mode sends one G-code file per cell and updates progress/manifest per cell.
  - Cell mode uses real jobs first, then `Generate next filler` fallback behavior.
- Add cleanup tests:
  - Hidden batch generation no longer appears in production/exhibition GUI paths.
  - Existing CLI/helper tests remain only if retained.
- Run:
  - `uv run pytest tests/test_gui_support.py tests/test_svg_gcode.py tests/test_plotter_daemon.py`
  - `uv run pytest`

## Assumptions
- Bigger cell means more visual detail, so effective point spacing should get smaller as cell diameter increases.
- Production should use real Mac mini sessions first, then Firebase-tagged MacBook filler from `Generate next filler`.
- Batch idle/filler generation is no longer operator-facing production behavior, but should be removed gradually to avoid breaking tests or emergency fallback.
- Symbol-by-symbol streaming should be introduced behind a mode switch before becoming the default production path.
