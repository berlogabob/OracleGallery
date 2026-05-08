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

## 2. Oracle Mac Mini: One Safe Uploader Launcher

The Mac mini should run only TouchDesigner and the lightweight uploader agent. The operator should launch one file and do nothing else on that machine:

```text
assets/sessions/START_ORACLE_UPLOADER.command
```

This single file performs setup if needed, writes/updates the repo `.env`, runs `uv sync`, validates Firebase/session paths, and starts only `neje-uploader-agent`. It must not generate fake sessions, open the GUI, or start the plotter.

The main GUI on the MacBook can then start, stop, restart, scan once, and monitor the uploader over the local network.

Required session folder shape:

```text
<sessions_root>/<session_id>/
  <session_id>_plotter.svg
  <session_id>_receipt.txt
  READY
```

The uploader ignores photos, audio, and transcripts. It publishes normalized SVG, raw SVG backup, receipt TXT, QR PNG, and manifest JSON.

Developer terminal start, only for debugging:

```bash
uv run neje-uploader-agent
```

There is no separate setup launcher anymore. There are no generator or GUI launchers in the real Mac mini sessions folder.

## 3. Test Generation

Use this when TouchDesigner is not running or when testing live Firebase upload and print queue behavior. The safe operator path is the main MacBook GUI in `TEST` mode.

Mac mini rule:

- `EXHIBITION DRY` / `EXHIBITION REAL`: Mac mini only uploads real TouchDesigner sessions.
- `TEST`: fake session generation is allowed only from the main GUI. The Mac mini uploader agent may upload those fake sessions if the GUI writes them into the watched folder.

Developer-only CLI:

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

If the uploader is already running, every generated user session will be uploaded to Firebase and will create a `plot_jobs/{session_id}` document.

## 4. Operator GUI

The GUI is the main NiceGUI supervisor panel. It starts/stops the local plotter daemon, controls print state, monitors Firebase/FluidNC/Mac mini uploader, and remains the source of truth for layout config.

Start from repository root:

```bash
uv run neje-gui
```

Double-click:

```text
start_oracle_gui.command
```

Default address:

```text
http://127.0.0.1:8787/
```

GUI sections:

- Top controls: `START SYSTEM`, `STOP SYSTEM`, current mode, dry/real transport, and calculated capacity.
- `Plotter Console` contains the plotter sequence: `Connect`, `Manual control`, then `Print`.
- Top mode selector: choose one mode only: `TEST`, `EXHIBITION DRY`, or `EXHIBITION REAL`.
- `TEST`: fake sessions, idle bank, preview, and dry-run only.
- `EXHIBITION DRY`: real sessions/uploader/queue, but physical FluidNC output is blocked and sheets go to dry-run/spool.
- `EXHIBITION REAL`: real sessions and real FluidNC output; `START PRINT` stays blocked until preflight has no critical failures, work zero is set, Ready Check passed, and the operator presses `ARM REAL FLUIDNC`.
- Layout: choose `hex` or `grid`, working field size, margin, cell diameter, and gap between neighbouring cell circles. Capacity is calculated automatically.
- Test mode: generate fake user session folders in `NEJE_UPLOADER_SESSION_ROOT`.
- Test mode: generate local mark-only idle SVG files in `assets/generated_idle_symbols`; rings are added later by print-time G-code.
- `Sheet Preview`: static schematic preview of current placement, not a plotter animation.
- `Plotter Status`: read local plotter runtime state, latest spool manifest, and confirm reload.
- `FluidNC Control`: check WebUI/Telnet/status, home, jog, unlock alarm, feed hold, resume, and soft reset.
- `Ready`: `Set Work Zero` saves current position as G54 X0 Y0 Z0; `Ready Check` raises Z, homes X/Y, returns to X0 Y0, and requires FluidNC `Idle`.
- `Logs`: shows the last local supervisor/preflight/uploader/plotter log lines from `logs/oracle_supervisor.log`.
- `Symbol Scale Correction`: edit `assets/symbols/symbol_scales.json` with global and per-symbol scale controls.
- Scale values can go up to `5.0`. Values above `1.0` intentionally may overlap neighbouring cells; use dry-run before enabling real FluidNC.

Important behavior:

- On launch, nothing starts automatically. Press `START SYSTEM` to start supervised components in safe mode.
- `START SYSTEM` creates a run baseline timestamp. Pending Firebase jobs older than that timestamp are marked `skipped`, tagged `baseline_skipped`, and hidden from the print queue.
- `START SYSTEM` starts the local plotter daemon, checks Firebase/FluidNC, and contacts `NEJE_MACMINI_AGENT_URL`.
- `PREFLIGHT` checks folders, symbols, idle bank, Firebase config, Mac mini/uploader path assumptions, TinyBee hardware assumptions, FluidNC, spool write access, and dry-run G-code generation.
- `CONNECT` auto-discovers FluidNC on the current hotspot subnet, then must show WebUI online, Telnet online, and controller state `Idle` before real print is armed.
- `ARM REAL FLUIDNC` is reset whenever the mode changes. It is never restored automatically after GUI restart.
- `START PRINT` is blocked until preflight has passed, work zero is set, and Ready Check has passed.
- The GUI writes layout settings to `runtime/oracle_runtime.sqlite3`; the plotter daemon reads this before every new sheet.
- If the Mac mini uploader agent is running and started, GUI-generated or TouchDesigner session folders are published to Firebase and become `plot_jobs`.
- `Generate dry-run sheet` writes local G-code and manifest to `spool/`; it does not send anything to the physical plotter.
- `STOP AFTER SHEET` is a safe stop. It prevents the next sheet from starting; it does not interrupt a FluidNC stream already in progress.
- `EMERGENCY STOP` sends FluidNC realtime feed hold `!`, disables print, and disarms real FluidNC. It is software safety only, not a replacement for a physical emergency stop.
- `Confirm reload` updates the local plotter runtime state in SQLite, equivalent to confirming reload in the operator dashboard.
- The GUI keeps settings in `runtime/gui_settings.json`.
- Real daemon streaming is row-based. It claims user jobs before every row, fills remaining row cells with idle symbols, and sends one row G-code file at a time. The physical reload workflow remains sheet-based.
- Rings are now a print-time overlay. Generated/uploaded SVGs are mark-only; the plotter G-code draws user rings as one circle and idle rings as two circles when the GUI `Rings` toggle is enabled.

FluidNC manual controls:

- `HOME ALL` sends `$H` and requires confirmation.
- `HOME X` / `HOME Y` send `$H=X` / `$H=Y`; use only if the FluidNC config supports single-axis homing.
- Jog buttons send `$J=G91 G21 X/Y... F...`; available steps are `1`, `5`, `10`, `25`, `50`, and `100 mm`.
- Manual jog/home commands pause print before moving and are blocked while G-code is actively streaming.
- `UNLOCK ALARM` sends `$X` only when the controller is in `Alarm`.
- `RESUME` sends realtime `~` only after a hold.
- `SOFT RESET` sends `Ctrl-X`, disables print, and should be treated as abort/reset.

## 5. Idle Symbol Bank

The plotter uses idle symbols to fill empty sheet cells. Original base symbols live in:

```text
assets/symbols/
```

Generate mark-only idle symbols:

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

Set values above or below `1.0` after visual tests. This changes the canonical symbol scale before upload, preview, and G-code. The physical packing is controlled by `NEJE_PLOTTER_CELL_DIAMETER_MM`; scale above `1.0` may deliberately cross cell boundaries for calibration.

## 6. SVG Normalization and Firebase Reprocessing

New session uploads are normalized automatically:

```text
viewBox="0 0 1000 1000"
data-neje-normalized="true"
data-neje-scale="<scale>"
```

The public `artwork.svg` is normalized. The original file is preserved as `artwork_raw.svg` in the same Firebase Storage session folder.

Dry-run existing Firebase sessions before writing:

```bash
uv run neje-normalize-firebase-sessions --dry-run --limit 10
```

Normalize one existing session:

```bash
uv run neje-normalize-firebase-sessions --session-id <session_id>
```

Force reprocessing if a session is already marked normalized:

```bash
uv run neje-normalize-firebase-sessions --session-id <session_id> --force
```

After upload, Firestore `svgUrl` gets a cache-busting version parameter so Flutter reloads the updated normalized SVG.

## 7. Plotter MacBook

Preferred exhibition start:

```bash
uv run neje-gui
```

Legacy direct daemon start for backup/debugging:

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
- User jobs are placed first on the next row.
- Empty row cells are filled with local idle symbols.
- The sheet capacity is always calculated automatically from field size, margin, layout mode, and cell diameter.
- `START PRINT` enables the next sheet. `STOP AFTER SHEET` prevents the next sheet but never interrupts a G-code stream already being sent.
- A row is atomic: new user jobs do not interrupt the current row, but can be claimed for the next row.
- After each sheet the daemon enters `paused_for_reload`.
- The operator replaces material and confirms reload in the dashboard.

Generated files:

```text
spool/*_row_*.gcode
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
NEJE_PLOTTER_USE_Z_SERVO=false
NEJE_PLOTTER_Z_DOWN_MM=0
NEJE_PLOTTER_Z_UP_MM=25
NEJE_PLOTTER_Z_FEED_MM_MIN=1000
NEJE_PLOTTER_WORK_ZERO_COMMAND="G10 L20 P1 X0 Y0 Z0"
NEJE_PLOTTER_TINYBEE_CONFIG_PATH=assets/tinybee.json
NEJE_PLOTTER_DRY_RUN=true
```

Set the GUI mode to `EXHIBITION REAL` only after dry-run G-code and layout are inspected. Then run `PREFLIGHT`, confirm there are no critical failures, press `ARM REAL FLUIDNC`, and only then press `START PRINT`.

## 8. Flutter Gallery and GitHub Pages

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
/#/cloth
/#/about
/#/library
/#/session/<session_id>
```

QR codes point to:

```text
https://berlogabob.github.io/OracleGallery/#/session/<session_id>
```

Firestore uses separate QR fields:

- `sessionUrl`: public receipt page link.
- `qrUrl`: backward-compatible public receipt page link.
- `qrImageUrl`: Firebase Storage URL for `qr.png`.
- `assetUrls.qr`: same QR PNG Storage URL.

## 9. Firebase Setup and Deploy

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

## 10. Smoke Tests

Uploader path:

```bash
uv run neje-uploader-agent
uv run neje-gui
```

In the GUI select `TEST`, press `START SYSTEM`, generate one test user session, then press `PREFLIGHT`.

Check Firebase:

- Storage has `sessions/<session_id>/artwork.svg`.
- Storage has `sessions/<session_id>/receipt.txt`.
- Storage has `sessions/<session_id>/qr.png`.
- Storage has `sessions/<session_id>/manifest.json`.
- Firestore has `sessions/<session_id>`.
- `sessions/<session_id>.sessionUrl` opens the receipt page.
- `sessions/<session_id>.qrImageUrl` opens the QR PNG.
- Firestore has `plot_jobs/<session_id>`.

Plotter dry-run path:

```bash
uv run neje-gui
```

In the GUI select `EXHIBITION DRY`, press `START SYSTEM`, press `PREFLIGHT`, press `Set Work Zero`, press `Ready Check`, then `START PRINT`.

Check:

- `spool/*_row_*.gcode` files were written.
- `spool/*.json` contains row entries and user items before placeholder items inside each row.
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

- select `TEST`;
- press `START SYSTEM`;
- press `PREFLIGHT` and confirm there are no critical failures for test mode;
- generate one user session and confirm a new session folder appears in `NEJE_UPLOADER_SESSION_ROOT`;
- generate idle bank and confirm `assets/generated_idle_symbols/*.svg` exists;
- open `Plotter`, generate dry-run sheet, and confirm `spool/*.gcode` and `spool/*.json` exist;
- open `Logs` and confirm supervisor/preflight lines are visible.

Exhibition dry-run smoke path:

```bash
uv run neje-uploader-agent
uv run neje-gui
```

Then in the GUI:

- select `EXHIBITION DRY`;
- press `START SYSTEM`;
- confirm `Mac mini uploader`, `Firebase`, `Plotter`, and `Queue` statuses are not `error`;
- press `PREFLIGHT`;
- press `Set Work Zero`;
- press `Ready Check`;
- press `START PRINT`;
- confirm generated sheets are written to `spool/` and physical FluidNC output remains blocked.

Real FluidNC smoke path:

- select `EXHIBITION REAL`;
- press `CONNECT` and confirm `WebUI online`, `Telnet online`, and `State: Idle`;
- press `PREFLIGHT`;
- confirm no critical failures and `FluidNC` is online;
- jog to the upper-left work origin, then press `Set Work Zero`;
- press `Ready Check`;
- press `ARM REAL FLUIDNC`;
- only then press `START PRINT`;
- use `STOP AFTER SHEET` for safe stop before the next sheet.

## 11. Troubleshooting

If SVG images show endless loading in the website, apply Storage CORS and hard-refresh the browser.

If uploader does nothing, check that the session folder has both `*_plotter.svg` and `*_receipt.txt`, or create `READY`.

If GUI-generated test sessions do not upload, confirm that `NEJE_UPLOADER_SESSION_ROOT` points to the same folder watched by `neje-uploader-agent`.

If a session uploads twice, check `runtime/uploader.sqlite3`; the uploader uses it to remember published source folders.

If plotter has no idle symbols, open GUI `TEST`, generate the idle bank, then return to `EXHIBITION DRY` or `EXHIBITION REAL`.

If plotter cannot claim Firebase jobs, check service account path and Firestore permissions.

If real plotting starts too early, do not use `EXHIBITION REAL`. Use `EXHIBITION DRY` until G-code and physical layout are confirmed. `EXHIBITION REAL` requires `PREFLIGHT` plus `ARM REAL FLUIDNC`.

If the GUI does not open, check `NEJE_GUI_HOST` and `NEJE_GUI_PORT`, then open `http://127.0.0.1:8787/` manually.

If GUI-generated sessions do not become Firebase jobs, start `assets/sessions/START_ORACLE_UPLOADER.command` on the Mac mini, press `START SYSTEM` in the MacBook GUI, and confirm Mac mini agent plus GUI use the same `NEJE_UPLOADER_SESSION_ROOT`.

If `START PRINT` is blocked, run `PREFLIGHT`, fix critical failures, confirm `FluidNC` is online, press `Set Work Zero`, press `Ready Check`, and in `EXHIBITION REAL` press `ARM REAL FLUIDNC`.

If FluidNC WebUI opens but GUI says FluidNC is not ready, check the Telnet side separately. The sender requires Telnet port `23`, a valid `?` status response, and state `Idle`; HTTP dashboard access alone is not enough. Android hotspot IPs can change, so use `CONNECT` in the GUI instead of relying on a remembered address.

If FluidNC state is `Alarm`, inspect the machine physically, then use `UNLOCK ALARM` only when safe.

If FluidNC state is `Hold`, use `RESUME` only when the tool path is safe to continue.

If a G-code stream fails with `error`, `ALARM`, disconnect, or timeout waiting for `ok`, the GUI disables print and disarms real FluidNC. Run `CONNECT`, inspect logs, and restart with dry-run before arming real output again.

If the Logs panel is empty, perform an action such as `PREFLIGHT` or `CHECK`, then refresh logs. Logs are written to `NEJE_ORACLE_LOGS_ROOT/oracle_supervisor.log`.
