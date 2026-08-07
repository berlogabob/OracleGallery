# Oracle Gallery

Local exhibition system for TouchDesigner session folders, Firebase publication, a read-only Flutter Web receipt gallery, and FluidNC plotter output.

## Architecture

- Oracle Mac mini: runs TouchDesigner and the lightweight uploader agent only.
- MacBook operator station: runs `neje-gui`, the main supervisor for plotter control, system checks, logs, layout, scale, and test generation.
- Firebase: stores public session documents, public SVG/TXT/QR assets, and real user print jobs.
- Flutter Web: static GitHub Pages app at `https://berlogabob.github.io/OracleGallery/`, read-only against Firestore.
- Plotter/FluidNC: controlled locally from `neje-gui`; output is blocked until system checks pass, work zero is set, and FluidNC is Idle.

## EchoDraw

EchoDraw (by Andrey Dyakov) and Neje Oracle are now one project. EchoDraw contributed the NEJE→FluidNC hardware documentation and the real-time generative vision. Curated content lives in `echodraw/` (see `echodraw/README.md`); photo archives and vendored libraries remain in the [original repo](https://github.com/berlogabob/echodraw-project).

Machine geometry source of truth: [echodraw/hardware/GEOMETRY.md](echodraw/hardware/GEOMETRY.md).

- **Module 1 — Hardware/FluidNC plotter:** superseded by the working plotter stack here; hardware docs, FluidNC config, pen-holder designs and BOM are in `echodraw/hardware/` and `echodraw/bom/`.
- **Module 2 — Generative core** (p5.js pattern generator): live, embedded in the operator GUI's `6 GENERATIVE` tab. Webcam/ML-driven generation is still a roadmap item; the reserved block for it is `src/neje_oracle/blocks/realtime_preview/`. See "Pattern generator, line text, and image-to-line-art" below.
- **Module 3 — Flutter wrapper:** covered by the existing `public_gallery/` Flutter app.

## Pattern generator, line text, and image-to-line-art

Three generative/drawing features live in the operator GUI, each reachable from its own top-level tab:

- **Pattern generator (`6 GENERATIVE` tab)** — an embedded p5.js sketch (`echodraw/generative-core/web/sketch.js`) with an 11-generator library (`circles`, `waves`, `gridwalk`, `flowfield`, `mondrian`, `tribal`, `circuit`, `motiftile`, `isolines`, `text`, `weave`), each a seeded `(rng, params) -> shapes[]` function. Up to 5 layers can be stacked, each with its own generator, density, scale, and optional mask. The sketch runs in an iframe (`/generative/index.html`); the GUI's `PRINT CAPTURED SVG` button sends the captured frame to the plotter, and a `Stream to plotter` switch can auto-print each new frame on an interval.
- **Line text (same `6 GENERATIVE` tab, "Line text" card)** — single-stroke SHX engraving fonts (`src/neje_oracle/blocks/text/shx.py`, font files in `assets/fonts/shx/*.SHX`) rendered as one pen pass per letter, no fill. Pick a font and cap height, type multi-line text, see a live preview, then `PRINT TEXT` to send it through the direct-SVG print path.
- **Image → line art (`7 IMAGE` tab)** — upload a raster image (`src/neje_oracle/blocks/imaging/modes.py`) and convert it to single-pen polylines in one of four modes: `halftone` (dot size by darkness, shortest plot), `hatch` (parallel lines only where dark; `Detail` = line spacing mm), `dither` (Floyd-Steinberg, highest fidelity/longest plot), or `contour` (threshold-band outlines; `Detail` = band count). `Cell mm` sets sampling resolution, `Gamma`/`Invert` adjust tone mapping. The preview shows stroke/segment counts and an estimated plot time before `PRINT IMAGE` sends it to the plotter.

## Session Contract

TouchDesigner writes one folder per visitor:

```text
sessions_raw/<session_id>/
  <session_id>_plotter.svg
  <session_id>_receipt.txt
  READY
```

Current reference package shape:

```text
assets/sessions/20260505_155503/
```

Use `20260505_155503` as the latest known-good local example when validating copied Mac mini output. Older local session folders are temporary data: delete them only after the same `session_id` exists in Firestore and `sessions/<session_id>/artwork.svg` exists in Firebase Storage.

Generated fake user sessions use the same public-safe package shape, plus `metadata.json` with `origin=test_macbook`. Local filler material can also be generated as session-like folders with `origin=filler_macbook`; filler packages are local only and intentionally have `uploadToFirebase=false`.

Ignored by the public pipeline:

```text
*_visitor.png
*.wav
transcripts
raw audio
```

The uploader publishes only:

```text
sessions/<session_id>/artwork.svg
sessions/<session_id>/artwork_raw.svg
sessions/<session_id>/receipt.txt
sessions/<session_id>/qr.png
sessions/<session_id>/manifest.json
```

QR deep link:

```text
https://berlogabob.github.io/OracleGallery/#/session/<session_id>
```

Firestore distinguishes the route and image:

- `sessionUrl`: receipt page deep link.
- `qrUrl`: backward-compatible receipt page deep link.
- `qrImageUrl`: Firebase Storage URL for `qr.png`.
- `assetUrls.qr`: same QR PNG Storage URL.

Origin fields used by the operator GUI and debug views:

- `origin=real_macmini`: real TouchDesigner visitor session from the Mac mini.
- `origin=test_macbook`: generated test session from the MacBook GUI.
- `origin=test_macmini`: generated test session from a Mac mini test mode, if enabled later.
- `origin=filler_macbook`: local filler/base symbol used to fill empty cells.
- `tags`: searchable/filterable labels such as `real`, `test`, `generated`, `macmini`, `macbook`, `filler`.

## Quick Start

Install dependencies from the repo root:

```bash
uv sync --extra dev
cd public_gallery && flutter pub get
```

Start the main operator GUI:

```bash
uv run neje-gui
```

Double-click launcher:

```text
start_oracle_gui.command
```

Mac mini launcher:

```text
assets/sessions/START_ORACLE_UPLOADER.command
```

The Mac mini launcher should be the only operator action on the TouchDesigner computer. It starts the uploader agent; generation and plotter control stay in the MacBook GUI.

## Firebase

Project:

```text
oraclegallery
```

Required environment values for Python services:

```bash
NEJE_FIREBASE_PROJECT_ID=oraclegallery
NEJE_FIREBASE_STORAGE_BUCKET=oraclegallery.firebasestorage.app
NEJE_FIREBASE_CREDENTIALS=/absolute/path/to/serviceAccountKey.json
NEJE_GALLERY_BASE_URL=https://berlogabob.github.io/OracleGallery
```

Flutter uses the web config in `public_gallery/lib/firebase_config.dart`. The public app does not use Firebase Auth, does not use Firebase Storage SDK, and never writes to Firebase.

## Main Commands

Run all Python checks:

```bash
uv run python -m py_compile src/neje_oracle/*.py
uv run pytest
```

Run Flutter checks:

```bash
cd public_gallery
flutter analyze
flutter build web --base-href /OracleGallery/
```

Build GitHub Pages output into root `docs/`:

```bash
./scripts/build_gallery_docs.sh
```

Deploy is manual by pushing `main`; GitHub Pages serves from `main` branch `/docs`.

## Project Folder Map

- `src/neje_oracle/`: Python uploader, GUI supervisor, plotter daemon, FluidNC transport, SVG/G-code logic.
- `public_gallery/`: Flutter source for the read-only public gallery.
- `docs/`: built Flutter Web output served by GitHub Pages.
- `planning/`: running debt/audit tracker (`GRAPH_DEBT_TRACKER.md`); see "Documentation map" below.
- `assets/symbols/`: canonical 8 base SVG symbols and scale config.
- `assets/sessions/`: Mac mini uploader launcher plus optional ignored local session examples. `20260505_155503` is the current reference package shape.
- `firebase/`: Firestore/Storage rules and indexes.
- `archive/`: old briefs, screenshots, and conversation exports.
- `runtime/`, `spool/`, `sessions_public/`, logs, caches, audio, and zip files are local generated data and are ignored.
- `assets/generated_filler_sessions/`: optional local filler packages with session-folder shape; ignored.

## Entry Points & Launchers

**Active entry points** (see `[project.scripts]` in `pyproject.toml`):
- `neje-gui` → MacBook operator GUI
- `neje-uploader-agent` → Mac mini uploader
- `neje-generate-sessions` → Generate test sessions
- `neje-thermal-autoprint` → Thermal printer control
- `neje-normalize-firebase-sessions` → Firebase normalization

**Removed in Phase 1:**
- ~~`neje-uploader`~~ → Use `neje-uploader-agent` instead
- ~~`neje-plotter`~~ → Runs embedded in GUI, not standalone

## Operating Modes

- `TEST`: lab drawing mode for fake sessions and direct uploaded SVG prints.
- `EXHIBITION`: real uploader/session queue and real FluidNC output.
- Both modes send real G-code to FluidNC only after system checks pass, work zero is set, and FluidNC is Idle. `Generate G-code only` remains the non-printing diagnostic path.

Drawing stops automatically after each sheet. Replace material, then press `START PRINT` when the next sheet is ready. `EMERGENCY STOP` sends FluidNC feed hold `!` and disables print, but it is not a replacement for a physical emergency stop.
The GUI motion-speed controls write XY feed rates as G-code `F` values in mm/min. Acceleration is controlled by the saved FluidNC controller settings, not by inline print G-code.

## Documentation map

Day-to-day start/operate docs:
- `README.md` — this file: what the system is, architecture, quick start, entry points.
- `RUNBOOK.md` — operator/developer checklist: setup, launchers, GUI walkthrough, Firebase setup and deploy, smoke tests, troubleshooting.
- `MACOS_LAUNCHERS.md` — packaging/distributing the Mac mini uploader as a double-click `.app`/ZIP over WhatsApp.
- `assets/sessions/README_MACMINI_UPLOADER.md` — what ships inside the Mac mini uploader pack itself.
- `FIREBASE_SETUP.md` — folded into `RUNBOOK.md` §9 (Firebase Setup and Deploy).

Subsystem/module docs:
- `src/neje_oracle/blocks/README.md` — modular-monolith block architecture and import/dependency rules.
- `src/neje_oracle/blocks/realtime_preview/README.md` — status of the live drawing preview block (future home for webcam/ML generative work).
- `public_gallery/README.md` — Flutter Web public gallery: responsibilities, build, routes.
- `echodraw/README.md` — what's curated from the original EchoDraw project and where it lives.
- `echodraw/hardware/README.md` / `echodraw/hardware/GEOMETRY.md` — NEJE hardware spec; GEOMETRY.md is the single source of truth for machine dimensions.
- `echodraw/generative-core/README.md` — link to the author's p5.js pattern-sketch collection (more generator examples beyond the ones wired into the GUI).
- `echodraw/docs/explanatory-note.md` — original EchoDraw project explanatory note (background/vision, Jan 2026).
- `ESP32-BTN_Printer/README.md` — ESP32 button + thermal printer firmware: wiring, protocols, discovery, receipt JSON contract.
- `ESP32-BTN_Printer/TouchDesigner/README.md` — the TouchDesigner button-bridge project file and local test flow.

Evidence and reports (hardware acceptance / test records — historical by design, not living docs):
- `reports/THERMAL_PRINTER_ACCEPTANCE.md` — thermal receipt printer acceptance record with measured/verified results.
- `reports/MACMINI_UPLOADER_REPORT.md` — Mac mini uploader packaging test report and pass/fail procedure.
- `reports/PROJECT_REPORT.md` — draft scaffold for the course final report (subject mapping, placeholders for photos/evidence).
- `audit/2026-08-05-1008/report.md` + `screens.md` — UX/UI audit of the operator GUI (baseline findings and screen inventory).
- `planning/GRAPH_DEBT_TRACKER.md` — running log of graphify-driven codebase-debt and declutter work, round by round.

Reference/archive (not operational docs):
- `archive/README.md` — index of historical briefing material, not part of the runnable system.
- `assets/README.md` — index of narrative/design-system/wireframe source documents.
- `assets/WebsiteWireframe/Oracle_website_wireframe/uploads/oracle_wireframe_brief.md` — content/structure brief for the public website wireframes.
- `CLAUDE.md` — Claude Code / graphify tooling instructions for this repo (not user-facing).

If a doc above looks stale when you read it, prefer verifying against the code (`pyproject.toml`, the actual source file) over trusting the doc — and fix or remove it rather than letting it linger.
