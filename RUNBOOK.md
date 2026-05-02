# Oracle Runbook

This is the operator and developer checklist for running the Oracle system.

## 1. First Setup

Install `uv` and Flutter on the development machine. Then from the repository root:

```bash
uv sync --extra dev
```

Create `.env` from one of the templates:

```bash
cp .env.example .env
```

Use `.env.oracle.example` on the Mac mini with TouchDesigner and `.env.plotter.example` on the plotter MacBook. Do not commit the real `.env` or Firebase service account JSON.

Minimum shared Firebase values:

```bash
NEJE_FIREBASE_PROJECT_ID=oraclegallery
NEJE_FIREBASE_STORAGE_BUCKET=oraclegallery.firebasestorage.app
NEJE_FIREBASE_CREDENTIALS=/absolute/path/to/serviceAccountKey.json
NEJE_GALLERY_BASE_URL=https://berlogabob.github.io/OracleGallery
```

## 2. Oracle Mac Mini: Uploader

The uploader watches one folder and uploads finished session folders to Firebase.

Required session folder shape:

```text
<sessions_root>/<session_id>/
  <session_id>_plotter.svg
  <session_id>_receipt.txt
  READY
```

The uploader ignores photos, audio, and transcripts. It publishes only SVG, receipt TXT, QR PNG, and manifest JSON.

Terminal start:

```bash
uv run neje-uploader
```

Double-click start from repository root:

```text
start_oracle_uploader.command
```

Double-click start from the real TouchDesigner sessions folder:

```text
assets/sessions/SETUP_ORACLE_UPLOADER.command
assets/sessions/START_ORACLE_UPLOADER.command
```

On the real Mac mini, copy those two files into the real `sessions` folder. Run setup once, then run start during the exhibition.

## 3. Test Generator

Use this when TouchDesigner is not running or when testing live Firebase upload and print queue behavior.

Generate one fake user session into `NEJE_UPLOADER_SESSION_ROOT`:

```bash
uv run neje-generate-sessions --mode user --count 1
```

Generate repeated fake user sessions for real-time uploader testing:

```bash
uv run neje-generate-sessions --mode user --live --count 10 --interval-seconds 12
```

Generate fake user sessions into a specific folder:

```bash
uv run neje-generate-sessions --mode user --count 3 --output-root /absolute/path/to/sessions
```

Double-click from repository root:

```text
generate_test_sessions.command
```

Double-click from the real sessions folder:

```text
assets/sessions/GENERATE_TEST_SESSION.command
```

If the uploader is already running, every generated user session will be uploaded to Firebase and will create a `plot_jobs/{session_id}` document.

## 4. Operator GUI

The GUI is a local NiceGUI browser panel. It does not replace the uploader or plotter daemon; it controls generation, layout preview, idle bank creation, scale correction, and local plotter state.

Start from repository root:

```bash
uv run neje-gui
```

Double-click:

```text
start_oracle_gui.command
```

Double-click from the real sessions folder:

```text
assets/sessions/START_ORACLE_GUI.command
```

Default address:

```text
http://127.0.0.1:8787/
```

GUI sections:

- Top bar: choose `TEST MODE` or `EXHIBITION MODE`, choose `DRY RUN` or `REAL FLUIDNC`, then use `START PRINT` / `STOP AFTER SHEET`.
- Layout: choose `hex` or `grid`, working field size, margin, cell diameter, and gap between neighbouring cell circles. Capacity is calculated automatically.
- Test mode: generate fake user session folders in `NEJE_UPLOADER_SESSION_ROOT`.
- Test mode: generate local double-circle idle SVG files in `assets/generated_idle_symbols`.
- `Sheet Preview`: static schematic preview of current placement, not a plotter animation.
- `Plotter Status`: read local plotter runtime state, latest spool manifest, and confirm reload.
- `Symbol Scale Correction`: edit `assets/symbols/symbol_scales.json` with global and per-symbol scale controls.

Important behavior:

- If `neje-uploader` is running, GUI-generated user sessions are published to Firebase and become `plot_jobs`.
- `Generate dry-run sheet` writes local G-code and manifest to `spool/`; it does not send anything to the physical plotter.
- `STOP AFTER SHEET` is a safe stop. It prevents the next sheet from starting; it does not interrupt a FluidNC stream already in progress.
- `Confirm reload` updates the local plotter runtime state in SQLite, equivalent to confirming reload in the operator dashboard.
- The GUI keeps settings in `runtime/gui_settings.json`.

## 5. Idle Symbol Bank

The plotter uses idle symbols to fill empty sheet cells. Original base symbols live in:

```text
assets/symbols/
```

Generate double-circle idle symbols:

```bash
uv run neje-generate-sessions --mode idle --count 8
```

Output:

```text
assets/generated_idle_symbols/
```

If this folder exists and contains SVG files, `start_plotter_daemon.sh` uses it automatically. Otherwise the plotter falls back to `assets/symbols`.

Manual per-symbol scale correction:

```text
assets/symbols/symbol_scales.json
```

Set values above or below `1.0` after visual tests. This changes the inner symbol scale before final plotter normalization. The physical packing is controlled by `NEJE_PLOTTER_CELL_DIAMETER_MM`; the printed symbol is internally kept below the cell diameter to prevent overlap.

## 6. Plotter MacBook

Start in dry-run mode first:

```bash
NEJE_PLOTTER_DRY_RUN=true uv run neje-plotter
```

Double-click:

```text
start_plotter_daemon.command
```

Operator dashboard:

```text
http://localhost:8765/
```

Runtime behavior:

- The daemon claims user jobs from Firestore.
- User jobs are placed first on the next sheet.
- Empty cells are filled with local idle symbols.
- The sheet capacity is always calculated automatically from field size, margin, layout mode, and cell diameter.
- `START PRINT` enables the next sheet. `STOP AFTER SHEET` prevents the next sheet but never interrupts a G-code stream already being sent.
- A sheet is atomic: new user jobs do not interrupt a sheet already printing.
- After each sheet the daemon enters `paused_for_reload`.
- The operator replaces material and confirms reload in the dashboard.

Generated files:

```text
spool/*.gcode
spool/*.json
spool/cache/*.svg
```

Important print variables:

```bash
NEJE_PLOTTER_LAYOUT_MODE=hex
NEJE_PLOTTER_SHEET_WIDTH_MM=250
NEJE_PLOTTER_SHEET_HEIGHT_MM=440
NEJE_PLOTTER_SHEET_MARGIN_MM=0
NEJE_PLOTTER_CELL_DIAMETER_MM=80
NEJE_PLOTTER_CELL_GAP_MM=0
NEJE_PLOTTER_DRY_RUN=true
```

Set the GUI output mode to `REAL FLUIDNC` only after dry-run G-code and layout are inspected. The default path remains dry-run and operator-paused.

## 7. Flutter Gallery and GitHub Pages

The repository is configured for GitHub Pages from:

```text
branch: main
folder: /docs
```

Build locally before pushing:

```bash
./scripts/build_gallery_docs.sh
```

The public routes are:

```text
/#/
/#/about
/#/library
/#/session/<session_id>
```

QR codes point to:

```text
https://berlogabob.github.io/OracleGallery/#/session/<session_id>
```

## 8. Firebase Setup and Deploy

Deploy Firestore rules, indexes, and Storage rules:

```bash
npx firebase-tools deploy --project oraclegallery --config firebase/firebase.json --only firestore:rules,firestore:indexes,storage
```

Apply Storage CORS for SVG loading in Flutter Web:

```bash
zsh -c 'set -a; source .env; set +a; uv run python scripts/configure_storage_cors.py'
```

Expected result:

```text
Updated CORS for gs://oraclegallery.firebasestorage.app
```

## 9. Smoke Tests

Uploader path:

```bash
uv run neje-generate-sessions --mode user --count 1
uv run neje-uploader
```

Check Firebase:

- Storage has `sessions/<session_id>/artwork.svg`.
- Storage has `sessions/<session_id>/receipt.txt`.
- Storage has `sessions/<session_id>/qr.png`.
- Storage has `sessions/<session_id>/manifest.json`.
- Firestore has `sessions/<session_id>`.
- Firestore has `plot_jobs/<session_id>`.

Plotter dry-run path:

```bash
NEJE_PLOTTER_DRY_RUN=true uv run neje-plotter
```

Check:

- `spool/*.gcode` was written.
- `spool/*.json` contains user items before placeholder items.
- dashboard shows `paused_for_reload` after the sheet.

Full developer checks:

```bash
uv run pytest
cd public_gallery && flutter analyze
./scripts/build_gallery_docs.sh
```

GUI smoke path:

```bash
uv run neje-gui
```

Then in the browser:

- generate one user session;
- confirm a new session folder appears in `NEJE_UPLOADER_SESSION_ROOT`;
- generate idle bank and confirm `assets/generated_idle_symbols/*.svg` exists;
- generate dry-run sheet and confirm `spool/*.gcode` and `spool/*.json` exist;
- press `Refresh status`.

## 10. Troubleshooting

If SVG images show endless loading in the website, apply Storage CORS and hard-refresh the browser.

If uploader does nothing, check that the session folder has both `*_plotter.svg` and `*_receipt.txt`, or create `READY`.

If generated sessions do not upload, confirm that `NEJE_UPLOADER_SESSION_ROOT` points to the same folder used by the generator.

If a session uploads twice, check `runtime/uploader.sqlite3`; the uploader uses it to remember published source folders.

If plotter has no idle symbols, run:

```bash
uv run neje-generate-sessions --mode idle --count 8
```

If plotter cannot claim Firebase jobs, check service account path and Firestore permissions.

If real plotting starts too early, keep `NEJE_PLOTTER_DRY_RUN=true` until the G-code and physical layout are confirmed.

If the GUI does not open, check `NEJE_GUI_HOST` and `NEJE_GUI_PORT`, then open `http://127.0.0.1:8787/` manually.

If GUI-generated sessions do not become Firebase jobs, start `neje-uploader` and confirm GUI and uploader use the same `NEJE_UPLOADER_SESSION_ROOT`.
