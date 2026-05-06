# Oracle Gallery

Local exhibition system for TouchDesigner session folders, Firebase publication, a read-only Flutter Web receipt gallery, and FluidNC plotter output.

## Architecture

- Oracle Mac mini: runs TouchDesigner and the lightweight uploader agent only.
- MacBook operator station: runs `neje-gui`, the main supervisor for plotter control, preflight, logs, layout, scale, and test generation.
- Firebase: stores public session documents, public SVG/TXT/QR assets, and real user print jobs.
- Flutter Web: static GitHub Pages app at `https://berlogabob.github.io/OracleGallery/`, read-only against Firestore.
- Plotter/FluidNC: controlled locally from `neje-gui`; real output is disabled until preflight, work zero, ready check, and explicit arm.

## Session Contract

TouchDesigner writes one folder per visitor:

```text
sessions_raw/<session_id>/
  <session_id>_plotter.svg
  <session_id>_receipt.txt
  READY
```

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

## Operating Modes

- `TEST`: fake sessions, idle bank generation, dry-run G-code, no real FluidNC output.
- `EXHIBITION DRY`: real uploader/session queue, dry-run/spool only.
- `EXHIBITION REAL`: real uploader/session queue and real FluidNC output, gated by preflight, work zero, ready check, and `ARM REAL FLUIDNC`.

`STOP AFTER SHEET` is safe and waits for the current row/sheet boundary. `EMERGENCY STOP` sends FluidNC feed hold `!`, disables print, and disarms real mode, but it is not a replacement for a physical emergency stop.
