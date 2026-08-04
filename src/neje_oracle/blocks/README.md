# Modular Block Architecture

This package is a modular monolith. Each block owns one operational capability
and exposes a small import surface through its package and service modules.

## Dependency Rules

- `neje_oracle.shared` contains cross-block configuration, persistence, logging,
  common models, and small domain helpers. It must not import from `app` or
  `blocks`.
- `neje_oracle.blocks.*` may import `shared`.
- Non-GUI blocks must not import `neje_oracle.blocks.gui`.
- `neje_oracle.app` composes blocks into runnable applications and may import
  any block.
- There are no top-level compatibility wrappers; launchers, tests, and external
  scripts import directly from `neje_oracle.shared`, `neje_oracle.blocks.*`,
  or `neje_oracle.app`.

## Block Ownership

- `fluidnc`: FluidNC network transport, probing, and control commands.
- `gcode`: layout, sampling, SVG-to-G-code generation, and marker geometry.
- `symbols`: SVG normalization and generated symbol/session assets.
- `firebase`: Firebase Admin repository and remote SVG normalization.
- `macmini`: TouchDesigner/Mac mini session ingestion and uploader agent.
- `thermal_printer`: thermal autoprint and ESP32 receipt-printer integration.
- `plotter`: plotter daemon loop, sheet materialization, and progress tracking.
- `gui`: NiceGUI shell, GUI components, workspaces, modes, and UI state.
- `realtime_preview`: target home for live drawing preview projection.

`public_gallery/` remains the Flutter source app. `docs/` remains the committed
GitHub Pages build output and should only change when the Flutter app or its web
contract changes.
