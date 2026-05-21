# Oracle Gallery

Local exhibition system for TouchDesigner session folders, Firebase publication, a read-only Flutter Web receipt gallery, and FluidNC plotter output.

## Architecture

- Oracle Mac mini: runs TouchDesigner and the lightweight uploader agent only.
- MacBook operator station: runs `neje-gui`, the main supervisor for plotter control, system checks, logs, layout, scale, and test generation.
- Firebase: stores public session documents, public SVG/TXT/QR assets, and real user print jobs.
- Flutter Web: static GitHub Pages app at `https://berlogabob.github.io/OracleGallery/`, read-only against Firestore.
- Plotter/FluidNC: controlled locally from `neje-gui`; output is blocked until system checks pass, work zero is set, and FluidNC is Idle.

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
- `planning/`: working plans, fix notes, and design/update checklists.
- `assets/symbols/`: canonical 8 base SVG symbols and scale config.
- `assets/sessions/`: Mac mini uploader launcher plus optional ignored local session examples. `20260505_155503` is the current reference package shape.
- `firebase/`: Firestore/Storage rules and indexes.
- `archive/`: old briefs, screenshots, and conversation exports.
- `runtime/`, `spool/`, `sessions_public/`, logs, caches, audio, and zip files are local generated data and are ignored.
- `assets/generated_filler_sessions/`: optional local filler packages with session-folder shape; ignored.

Legacy backup paths:

- `neje-plotter`, `start_plotter_daemon.*`, and `src/neje_oracle/plotter_service.py` remain backup/debug entrypoints. Exhibition operation should start from `neje-gui`.
- `neje-uploader` and `src/neje_oracle/uploader_service.py` remain backup/debug entrypoints. The Mac mini should use `assets/sessions/START_ORACLE_UPLOADER.command`.

## Operating Modes

- `TEST`: lab drawing mode for fake sessions and direct uploaded SVG prints.
- `EXHIBITION`: real uploader/session queue and real FluidNC output.
- Both modes send real G-code to FluidNC only after system checks pass, work zero is set, and FluidNC is Idle. `Generate G-code only` remains the non-printing diagnostic path.

Drawing stops automatically after each sheet. Replace material, then press `START PRINT` when the next sheet is ready. `EMERGENCY STOP` sends FluidNC feed hold `!` and disables print, but it is not a replacement for a physical emergency stop.
The GUI motion-speed controls write XY feed rates as G-code `F` values in mm/min. Acceleration is controlled by the saved FluidNC controller settings, not by inline print G-code.
