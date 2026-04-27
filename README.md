# Neje Oracle Orchestrator

This repository implements the split architecture for the exhibition system:

- `neje-uploader` runs on the TouchDesigner machine and only watches/export-publishes session folders to Firebase.
- `neje-plotter` runs on the MacBook and pulls print jobs from Firestore, fills sheets with placeholders, composes hex layouts, generates G-code, and exposes a tiny operator dashboard.
- `public_gallery/` is a Flutter Web app meant for GitHub Pages from the root `docs/` folder and read-only session display via Firebase.

The TouchDesigner machine does not do plot orchestration anymore. It only emits finished session folders, and the uploader publishes them.

## Session contract

Each finished TouchDesigner session folder must look like:

```text
sessions_raw/<session_id>/
  artwork.svg
  preview.png
  metadata.json   # optional
  READY           # optional but recommended
```

`metadata.json` can contain `title`, `summary`, `created_at`, and any extra JSON payload. Only `artwork.svg`, `preview.png`, QR, and a generated `manifest.json` are published.

## Python services

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

The plotter daemon serves an operator dashboard on `http://localhost:8765/` by default. After each printed sheet it enters `paused_for_reload`; press the dashboard button or `POST /operator/reload` to continue.

## Double-click launchers for macOS

Use these files directly from Finder:

- `start_oracle_uploader.command` on the Mac mini with TouchDesigner.
- `start_plotter_daemon.command` on the MacBook that drives the plotter.

Matching `.sh` files are included for Terminal/manual use. The launchers:

- enter the project folder automatically,
- load `.env` if it exists,
- check the required Firebase paths and folders before startup,
- keep the Terminal window open on failure so the operator can read the error.

Before using the double-click launchers, create a real `.env` from `.env.example` on each machine and fill in the machine-specific paths.

If you want machine-specific templates, start from:

- `.env.oracle.example` for the Mac mini uploader machine.
- `.env.plotter.example` for the MacBook plotter machine.

## Project folders

- `src/neje_oracle/` Python services, Firebase integration, plotting pipeline, launch scripts.
- `public_gallery/` Flutter Web public gallery for GitHub Pages.
- `docs/` built Flutter Web output served by GitHub Pages from `main`.
- `firebase/` Firestore/Storage rules and Firestore indexes.
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

## Verification

```bash
uv run pytest
cd public_gallery && flutter analyze
```
