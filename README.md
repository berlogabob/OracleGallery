# Neje Oracle Orchestrator

This repository contains the local uploader, public Flutter gallery, plotter daemon, and test tooling for the Oracle exhibition system.

## Architecture

- Oracle Mac mini: TouchDesigner writes finished session folders; `neje-uploader` uploads safe public assets to Firebase and creates user print jobs.
- Public web: `public_gallery/` is Flutter Web, built into root `docs/` for GitHub Pages.
- Plotter MacBook: `neje-plotter` pulls user jobs from Firestore, fills remaining sheet cells with local idle symbols, writes G-code to `spool/`, and exposes an operator page.
- Test workflow: `neje-generate-sessions` creates fake Oracle sessions from the 8 base symbols, so Firebase upload and print queue behavior can be tested without running TouchDesigner.
- Operator GUI: `neje-gui` opens a local NiceGUI browser panel for generator controls, layout preview, scale correction, idle bank generation, and plotter status.

The TouchDesigner computer should only run TouchDesigner and the lightweight uploader. Plot orchestration stays on the plotter MacBook.

## Session contract

Each finished real or generated session folder must look like:

```text
sessions_raw/<session_id>/
  <session_id>_plotter.svg
  <session_id>_receipt.txt
  metadata.json   # optional
  READY           # optional but recommended
```

The uploader ignores visitor photos, audio, transcript files, and `*_visitor.png`. It publishes only `artwork.svg`, `receipt.txt`, `qr.png`, and `manifest.json`. It also reads `session_log.csv` from the sessions root for `intensity`, `instability`, and `confidence`.

## Quick Start

Install dependencies with `uv`:

```bash
uv sync
```

Run the uploader on the main machine:

```bash
uv run neje-uploader
```

Run the plotter daemon on the MacBook:

```bash
uv run neje-plotter
```

Run the local operator GUI:

```bash
uv run neje-gui
```

Generate one fake user session into the configured uploader sessions folder:

```bash
uv run neje-generate-sessions --mode user --count 1
```

Generate local idle/filling symbols with double circles:

```bash
uv run neje-generate-sessions --mode idle --count 8
```

The plotter daemon serves an operator dashboard on `http://localhost:8765/` by default. After each printed sheet it enters `paused_for_reload`; press the dashboard button or call `POST /operator/reload` to continue.

## Double-click launchers for macOS

Use these files directly from Finder:

- `start_oracle_uploader.command` on the Mac mini with TouchDesigner.
- `start_plotter_daemon.command` on the MacBook that drives the plotter.
- `start_oracle_gui.command` for the local generator/plotter operator GUI.
- `generate_test_sessions.command` to create fake user sessions from the repo root.
- `assets/sessions/GENERATE_TEST_SESSION.command` to create one fake user session directly in the real sessions folder.
- `assets/sessions/START_ORACLE_GUI.command` to launch the GUI from the real TouchDesigner sessions folder.
- `assets/sessions/SETUP_ORACLE_UPLOADER.command` and `assets/sessions/START_ORACLE_UPLOADER.command` are designed to live inside the actual TouchDesigner sessions folder on the Mac mini.

Matching `.sh` files are included for Terminal/manual use. The launchers:

- enter the project folder automatically,
- load `.env` if it exists,
- check the required Firebase paths and folders before startup,
- keep the Terminal window open on failure so the operator can read the error.

Before using the double-click launchers, create a real `.env` from `.env.example` on each machine and fill in the machine-specific paths.

If you want machine-specific templates, start from:

- `.env.oracle.example` for the Mac mini uploader machine.
- `.env.plotter.example` for the MacBook plotter machine.

Detailed operator instructions are in `RUNBOOK.md`.

## Project folders

- `src/neje_oracle/` Python services, Firebase integration, plotting pipeline, launch scripts.
- `public_gallery/` Flutter Web public gallery for GitHub Pages.
- `docs/` built Flutter Web output served by GitHub Pages from `main`.
- `firebase/` Firestore/Storage rules and Firestore indexes.
- `assets/symbols/` eight local idle/filling SVG symbols used by the plotter daemon.
- `assets/symbols/symbol_scales.json` manual per-symbol scale multipliers used by the test generator.
- `assets/generated_idle_symbols/` generated idle/filling SVGs with double circles; ignored by git.
- `archive/` old briefing artifacts and reference files that are not part of the runtime system.

## GitHub Pages

This repository is designed for GitHub Pages configured as:

- branch: `main`
- folder: `/docs`

Build the gallery locally before pushing:

```bash
./scripts/build_gallery_docs.sh
```

The build script writes Flutter output into `docs/` and creates `.nojekyll`.
The runtime Firebase web config is `docs/firebase-config.json`. Firebase Web config is public client configuration, so it can be committed. Do not commit the Python service account JSON.

## Firebase data model

- `sessions/{session_id}`: public session metadata and asset locations for Flutter Web.
- `plot_jobs/{session_id}`: print queue documents claimed by the MacBook daemon.

The uploader writes both documents. The plotter daemon only claims and updates `plot_jobs`, while mirroring `plotStatus` onto `sessions/{session_id}`.

## Important Environment Variables

- `NEJE_FIREBASE_PROJECT_ID`, `NEJE_FIREBASE_STORAGE_BUCKET`, `NEJE_FIREBASE_CREDENTIALS`: Firebase Admin access for Python services.
- `NEJE_GALLERY_BASE_URL`: public GitHub Pages URL used in QR codes.
- `NEJE_UPLOADER_SESSION_ROOT`: folder watched by the uploader and default target for generated user sessions.
- `NEJE_PLOTTER_PLACEHOLDER_ROOT`: idle/filling symbol folder; `start_plotter_daemon.sh` prefers `assets/generated_idle_symbols` when it exists, then falls back to `assets/symbols`.
- `NEJE_PLOTTER_CELL_DIAMETER_MM`: physical packing cell diameter and the visible cell size in the operator preview.
- `NEJE_PLOTTER_CELL_GAP_MM`: physical empty distance between neighbouring cell circles.
- `NEJE_PLOTTER_LAYOUT_MODE`: `hex` or `grid`.
- `NEJE_GENERATOR_COUNT`: count used by double-click test generator launchers.
- `NEJE_GUI_HOST`, `NEJE_GUI_PORT`: local NiceGUI bind address, default `127.0.0.1:8787`.

## Verification

```bash
uv run pytest
cd public_gallery && flutter analyze
./scripts/build_gallery_docs.sh
```
