# Neje Oracle Orchestrator

This repository contains the local uploader, public Flutter gallery, plotter daemon, and test tooling for the Oracle exhibition system.

## Architecture

- Oracle Mac mini: TouchDesigner writes finished session folders; `neje-uploader-agent` lets the main GUI start/stop/monitor uploads to Firebase.
- Public web: `public_gallery/` is Flutter Web, built into root `docs/` for GitHub Pages.
- Plotter MacBook: `neje-gui` is the main supervisor. It starts/stops the local plotter daemon, controls print state, previews sheets, and monitors Mac mini uploader/Firebase/FluidNC.
- Test workflow: `neje-gui` in `TEST` mode creates fake Oracle sessions from the 8 base symbols, so Firebase upload and print queue behavior can be tested without running TouchDesigner.
- Operator GUI: `neje-gui` opens a local NiceGUI browser panel for generator controls, layout preview, scale correction, idle bank generation, preflight, logs, and plotter status.

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

The uploader ignores visitor photos, audio, transcript files, and `*_visitor.png`. It publishes normalized `artwork.svg`, raw backup `artwork_raw.svg`, `receipt.txt`, `qr.png`, and `manifest.json`. It also reads `session_log.csv` from the sessions root for `intensity`, `instability`, and `confidence`.

## Quick Start

Install dependencies with `uv`:

```bash
uv sync
```

Run the central operator GUI on the MacBook:

```bash
uv run neje-gui
```

On the real TouchDesigner Mac mini, launch exactly one file from the real sessions folder:

```text
assets/sessions/START_ORACLE_UPLOADER.command
```

It performs setup if needed and starts only `neje-uploader-agent`. For developer terminal debugging, the equivalent command is:

```bash
uv run neje-uploader-agent
```

Recommended operator flow:

1. Start `assets/sessions/START_ORACLE_UPLOADER.command` on the Mac mini.
2. Start `neje-gui` on the plotter/operator MacBook.
3. Select one GUI mode: `TEST`, `EXHIBITION DRY`, or `EXHIBITION REAL`.
4. Press `START SYSTEM`.
5. In `Plotter Console`, press `Connect / Probe`, then `Preflight`.
6. Use `EXHIBITION DRY` for normal queue/dry-run checks.
7. Use `EXHIBITION REAL` only after preflight has no critical failures, then press `Arm Real`, then `Start Print`.

GUI modes:

- `TEST`: fake sessions, idle bank generation, preview, and dry-run only. Physical FluidNC output is blocked.
- `EXHIBITION DRY`: real Mac mini/Firebase/queue flow, but sheets are written to local dry-run/spool only.
- `EXHIBITION REAL`: real queue and real FluidNC output. This mode requires preflight and explicit arming every time.

FluidNC control:

- Configure the plotter with `NEJE_PLOTTER_FLUIDNC_HTTP_URL=http://10.198.21.74` and `NEJE_PLOTTER_FLUIDNC_TELNET_HOST=10.198.21.74`.
- The GUI `Connect / Probe` action verifies both WebUI/HTTP and Telnet, then reads `?` status and `$G` modal state.
- WebUI online is not enough for real sending. Real G-code streaming requires Telnet port `23` and an `Idle` controller state.
- GUI jog/homing controls use FluidNC commands: `$H`, `$H=X`, `$H=Y`, `$X`, `$J=G91 G21 ...`, realtime `!`, `~`, and `Ctrl-X`.
- `EMERGENCY STOP` is software feed hold `!`; keep a physical emergency stop/power cut available.
- Printing is row-based: the daemon groups each sheet into rows, claims user jobs before every row, fills remaining row cells with idle symbols, and writes/sends `spool/<sheet>_row_XX.gcode`. Material reload is still sheet-based in v1.

Developer-only direct services are still available for debugging:

```bash
uv run neje-uploader
uv run neje-plotter
```

Developer-only CLI for fake sessions remains available, but operators should use the GUI `TEST` mode instead:

```bash
uv run neje-generate-sessions --mode user --count 1
```

Developer-only CLI for local idle/filling symbols also remains available; the operator path is GUI `TEST` mode:

```bash
uv run neje-generate-sessions --mode idle --count 8
```

Normalize already uploaded Firebase session SVGs in place, without writing first:

```bash
uv run neje-normalize-firebase-sessions --dry-run --limit 10
```

The legacy plotter daemon serves an operator dashboard on `http://localhost:8765/` by default. The preferred exhibition control path is `neje-gui`, which starts and supervises the local daemon directly.

## Double-click launchers for macOS

Use these files directly from Finder:

- `assets/sessions/START_ORACLE_UPLOADER.command` is the only file that should be placed in or launched from the real Mac mini TouchDesigner sessions folder. It performs setup if needed and starts only `neje-uploader-agent`.
- `start_uploader_agent.command` is a developer/root launcher for the same uploader agent, not the exhibition Mac mini operator path.
- `start_plotter_daemon.command` is a developer/backup launcher on the MacBook that drives the plotter.
- `start_oracle_gui.command` for the main supervised operator GUI.

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
- `assets/symbols/symbol_scales.json` manual per-symbol scale multipliers used by the test generator, uploader normalization, and Firebase reprocessing.
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

## SVG normalization

All new generated and uploaded session SVGs are converted to a canonical fixed canvas:

```text
viewBox="0 0 1000 1000"
data-neje-normalized="true"
data-neje-scale="<0.3..5.0>"
```

The fixed viewport is intentional. Scale values above `1.0` may overlap neighbouring cells and can produce G-code outside the packing circle; this is allowed for visual/print calibration. Legacy non-normalized SVG files are still bbox-fitted safely by the G-code fallback.

## Important Environment Variables

- `NEJE_FIREBASE_PROJECT_ID`, `NEJE_FIREBASE_STORAGE_BUCKET`, `NEJE_FIREBASE_CREDENTIALS`: Firebase Admin access for Python services.
- `NEJE_GALLERY_BASE_URL`: public GitHub Pages URL used in QR codes.
- `NEJE_ORACLE_RUNTIME_DB_PATH`: shared local supervisor/runtime SQLite used by GUI and plotter.
- `NEJE_ORACLE_LOGS_ROOT`: local folder for GUI/supervisor/preflight logs.
- `NEJE_MACMINI_AGENT_URL`: URL of the Mac mini uploader agent, for example `http://macmini.local:8790`.
- `NEJE_UPLOADER_SESSION_ROOT`: folder watched by the uploader and default target for generated user sessions.
- `NEJE_UPLOADER_AGENT_HOST`, `NEJE_UPLOADER_AGENT_PORT`: bind address for `neje-uploader-agent` on the Mac mini.
- `NEJE_PLOTTER_PLACEHOLDER_ROOT`: idle/filling symbol folder; `start_plotter_daemon.sh` prefers `assets/generated_idle_symbols` when it exists, then falls back to `assets/symbols`.
- `NEJE_PLOTTER_CELL_DIAMETER_MM`: physical packing cell diameter and the visible cell size in the operator preview.
- `NEJE_PLOTTER_CELL_GAP_MM`: physical empty distance between neighbouring cell circles.
- `NEJE_PLOTTER_LAYOUT_MODE`: `hex` or `grid`.
- `NEJE_GUI_HOST`, `NEJE_GUI_PORT`: local NiceGUI bind address, default `127.0.0.1:8787`.

## Verification

```bash
uv run pytest
cd public_gallery && flutter analyze
./scripts/build_gallery_docs.sh
```

The current GUI/supervisor tests cover mode mapping, preflight behavior, real FluidNC safety gates, runtime store persistence, GUI settings migration, plotter runtime config handoff, uploader agent control, FluidNC probe/ack streaming/control commands, and SVG/G-code helpers.
