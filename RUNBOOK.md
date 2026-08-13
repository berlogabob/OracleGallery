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

Reference package:

```text
assets/sessions/20260505_155503/
```

Treat `20260505_155503` as the latest known-good local package structure. Older copied session folders may be removed from `assets/sessions/` only after both checks pass:

```text
Firestore document exists: sessions/<session_id>
Storage artwork exists: sessions/<session_id>/artwork.svg
```

Do not delete local old folders that are missing either Firebase check; they may be the only remaining copy.

Developer terminal start, only for debugging:

```bash
uv run neje-uploader-agent
```

There is no separate setup launcher anymore. There are no generator or GUI launchers in the real Mac mini sessions folder.

## 3. Test Generation

Use this when TouchDesigner is not running or when testing live Firebase upload and print queue behavior. The safe operator path is the main MacBook GUI in `TEST` mode.

Mac mini rule:

- `EXHIBITION`: Mac mini only uploads real TouchDesigner sessions.
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

GUI layout:

- **Machine rail**, left, on every screen: jog, `HOME ALL`/`HOME X`/`HOME Y`, `PEN UP`/`PEN DOWN`,
  `SET WORK ZERO`, and the next action the machine is waiting for. Bringing the machine up
  never requires changing screens.
- **Status bar**, top: machine state (glyph and colour, so it reads without relying on colour),
  work position, work zero, Firebase, queue, sheet, then `STOP PRINT` and `EMERGENCY STOP`
  set apart at the far end.
- **Three screens**, replacing the seven numbered tabs:
  - `PRINT` — the run: `START PRINT`, live sheet state, system run, system check, queue.
  - `CREATE` — what gets drawn: generative sketch, texture nodes, line text, image conversion,
    frame sheet, motif import.
  - `SETUP` — the machine: connection and recovery, calibration and pen profiles, test prints,
    and a collapsed `Diagnostics` section holding the uploader, thermal printer and logs.
- **Run profile** selector, top right: `TEST` or `EXHIBITION`. This used to be inferred from
  whichever tab was open, so opening a tab to look at it silently rewrote Firebase policy.
- `TEST`: lab drawing mode for fake sessions and direct uploaded SVG prints. `START TEST PRINT` and `PRINT SVG` require preflight, work zero, and FluidNC connected/Idle.
- `EXHIBITION`: real sessions/uploader/queue and real FluidNC output. `START PRINT` stays blocked until preflight has no critical failures, work zero is set, and FluidNC is Idle.
- Layout: choose `hex` or `grid`, working field size, margin, cell diameter, and gap between neighbouring cell circles. Capacity is calculated automatically.
- Test mode: generate fake user session folders in `NEJE_UPLOADER_SESSION_ROOT`.
- Test mode: generate local mark-only idle SVG files in `assets/generated_idle_symbols`; rings are added later by print-time G-code.
- `Sheet Preview`: the layout as it will be plotted -- ring counts, cell geometry and the
  user/filler mix are the real ones. Which symbol lands in which cell is still chosen when
  the sheet is built, and the caption says so.
- `Plotter Status`: read local plotter runtime state and latest spool manifest.
- `FluidNC Control`: check WebUI/Telnet/status, home, jog, unlock alarm, feed hold, resume, and soft reset.
- `Ready`: `Set Work Zero` saves current XY position as G54 X0 Y0 without changing Z.
- `Logs`: shows the last local supervisor/preflight/uploader/plotter log lines from `logs/oracle_supervisor.log`.
- `Symbol Scale Correction`: edit `assets/symbols/symbol_scales.json` with global and per-symbol scale controls.
- Scale values can go up to `5.0`. Values above `1.0` intentionally may overlap neighbouring cells; use `Generate G-code only` before physical plotting.

Important behavior:

- On launch, nothing starts automatically. Press `START SYSTEM` to start supervised components in safe mode.
- `START SYSTEM` creates a run baseline timestamp. Pending Firebase jobs older than that timestamp are marked `skipped`, tagged `baseline_skipped`, and hidden from the print queue.
- `START SYSTEM` starts the local plotter daemon, checks Firebase/FluidNC, and contacts `NEJE_MACMINI_AGENT_URL`.
- `PREFLIGHT` checks folders, symbols, idle bank, Firebase config, Mac mini/uploader path assumptions, TinyBee hardware assumptions, FluidNC, spool write access, and G-code generation.
- `CONNECT` auto-discovers FluidNC on the current hotspot subnet. Telnet plus a valid `?` status response proves controller connection; WebUI/HTTP is shown as separate detail and does not block motion or print by itself.
- `START PRINT` is blocked until preflight has passed, work zero is set, and FluidNC is Idle.
- The GUI writes layout settings to `runtime/oracle_runtime.sqlite3`; the plotter daemon reads this before every new sheet.
- If the Mac mini uploader agent is running and started, GUI-generated or TouchDesigner session folders are published to Firebase and become `plot_jobs`.
- `Generate G-code only` writes local G-code and manifest to `spool/`; it does not send anything to the physical plotter.
- `PRINT SVG` on `SETUP` validates an Inkscape-style SVG, generates one sheet of G-code, and sends it directly to FluidNC after preflight, work zero, and Idle checks. It does not create a Firebase queue session.
- Drawing stops automatically after each sheet; press `START PRINT` only when the next sheet is loaded and ready.
- Motion speed controls write `G0 F...` and `G1 F...` feed rates in mm/min. `XY accel mm/s^2` is recorded in manifests only; generated print G-code uses the controller's saved acceleration settings.
- `EMERGENCY STOP` sends FluidNC realtime feed hold `!` and disables print. It is software safety only, not a replacement for a physical emergency stop.
- The GUI keeps settings in `runtime/gui_settings.json`.
- Real daemon streaming is row-based. It claims user jobs before every row, fills remaining row cells with idle symbols, and sends one row G-code file at a time.
- Rings are now a print-time overlay. Generated/uploaded SVGs are mark-only; the plotter G-code draws user rings as one circle and idle rings as two circles when the GUI `Rings` toggle is enabled.

FluidNC manual controls:

- `Home XY` sends `$H=XY` and requires confirmation.
- `Home X` / `Home Y` send `$H=X` / `$H=Y`; use only if the FluidNC config supports single-axis homing.
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

If this folder exists and contains SVG files, the plotter daemon uses it automatically. Otherwise it falls back to `assets/symbols`.

The GUI marks filler cells as `origin=filler_macbook`. Filler symbols are local and do not create Firestore `plot_jobs`.

For package-shape consistency, filler can also be generated as local session-like folders:

```bash
uv run neje-generate-sessions --mode filler --count 8
```

Output:

```text
assets/generated_filler_sessions/filler_<timestamp>_<n>/
  filler_<timestamp>_<n>_plotter.svg
  filler_<timestamp>_<n>_receipt.txt
  metadata.json
  READY
```

Filler packages intentionally contain no visitor photo, WAV, or transcript. They are local print material, not public Firebase sessions, and `metadata.json` includes `uploadToFirebase=false`.

Manual per-symbol scale correction:

```text
assets/symbols/symbol_scales.json
```

Set values above or below `1.0` after visual tests. This changes the canonical symbol scale before upload, preview, and G-code. The physical packing is controlled by `NEJE_PLOTTER_CELL_DIAMETER_MM`; scale above `1.0` may deliberately cross cell boundaries for calibration.

Origin dots:

- `Rings` controls user/filler circles.
- `Origin dots` controls the small printed origin marker.
- Dot positions distinguish origins on monochrome output: real Mac mini, test MacBook, test Mac mini, filler MacBook, and unknown.
- Preview filters update immediately. Print filters apply from the next row, never in the middle of a row.

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

The plotter daemon runs inside `neje-gui`; there is no separate daemon process or
launcher. The former `neje-plotter` entry point and `start_plotter_daemon.command` were
removed.

Operator dashboard:

```text
http://localhost:8765/
```

Runtime behavior:

- The daemon claims user jobs from Firestore.
- User jobs are placed first on the next row.
- Empty row cells are filled with local idle symbols.
- The sheet capacity is always calculated automatically from field size, margin, layout mode, and cell diameter.
- `START PRINT` enables one sheet. The daemon stops automatically when that sheet finishes.
- A row is atomic: new user jobs do not interrupt the current row, but can be claimed for the next row.
- After each sheet the daemon stops printing. Replace material, then press `START PRINT` when the next sheet is ready.

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
NEJE_PLOTTER_USE_Z_SERVO=true
NEJE_PLOTTER_PEN_UP=M5
NEJE_PLOTTER_PEN_DOWN="M3 S15"
NEJE_PLOTTER_Z_DOWN_MM=-25
NEJE_PLOTTER_Z_UP_MM=0
NEJE_PLOTTER_Z_FEED_MM_MIN=1000
NEJE_PLOTTER_WORK_ZERO_COMMAND="G10 L20 P1 X0 Y0"
NEJE_PLOTTER_TINYBEE_CONFIG_PATH=assets/tinybee.json
NEJE_PLOTTER_DRY_RUN=true
```

Working Z-axis baseline, confirmed on 2026-05-13:

- Keep `NEJE_PLOTTER_USE_Z_SERVO=true`.
- FluidNC exposes the TinyBee touch PWM servo as the Z axis.
- `$H=Z` is pen up/safe everywhere, including generated drawing G-code.
- `G0 Z-25` is fixed absolute pen down/contact everywhere; saved GUI/runtime Z-down values are ignored in Z-servo mode.
- GUI `Z Home / Pen up` sends `$H=Z`.
- GUI `Z- / Pen down` sends `G21`, `G90`, `G54`, `G0 Z-25`.
- Do not replace these buttons with `$J Z...` jog or `M3/M5`; both broke this hardware path.
- Do not auto-probe immediately after manual Z buttons; that looked like a FluidNC reconnect and disturbed operation.

This matches the known-good `/Users/berloga/Downloads/matrix_col12.nc` test file.

Use `Generate G-code only` to inspect layout before physical plotting. Then run `PREFLIGHT`, confirm there are no critical failures, set work zero, confirm FluidNC is Idle, and press `START PRINT`.

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

Firebase is used for public receipt data, public SVG/TXT/QR assets, and real user plot jobs. It is not used to control idle/filler printing, and the Flutter app is read-only (no Auth, no Storage SDK, no writes).

Project:

```text
Project ID: oraclegallery
Storage bucket: oraclegallery.firebasestorage.app
Gallery URL: https://berlogabob.github.io/OracleGallery
```

Enable Cloud Firestore and Firebase Storage. Firebase Auth and Cloud Messaging are not required.

Download the Firebase service account JSON and keep it outside git, then set:

```bash
NEJE_FIREBASE_PROJECT_ID=oraclegallery
NEJE_FIREBASE_STORAGE_BUCKET=oraclegallery.firebasestorage.app
NEJE_FIREBASE_CREDENTIALS=/absolute/path/to/serviceAccountKey.json
NEJE_GALLERY_BASE_URL=https://berlogabob.github.io/OracleGallery
```

Do not put the service account file in `public_gallery`, `docs`, or any committed folder. The public web config (safe to expose) lives in `public_gallery/lib/firebase_config.dart`.

Firestore contract — public session document `sessions/{session_id}` carries `sessionId`, `createdAt`, `status`, `plotStatus`, `markName`, `oracleText`, `themes`, `measures`, `svgUrl`, `receiptUrl`, `sessionUrl`, `qrUrl`, `qrImageUrl`, `assetUrls.*`, `assetPaths.*`, `origin`, `tags`, `visibleInLibrary`. `sessionUrl`/`qrUrl` are page links; `qrImageUrl`/`assetUrls.qr` are PNG Storage URLs. Print job document `plot_jobs/{session_id}` carries `sessionId`, `createdAt`, `status`, `priority`, `queue`, `svgStoragePath`, `svgUrl`, `origin`, `tags`, `visibleInQueue`.

Origin values actually used by the code (`shared/origin_markers.py`) and GUI/debug views: `real_macmini`, `test_macbook`, `test_macmini`, `filler_macbook` — see the Session Contract in `README.md`.

Firestore v1 rules (public read, no client writes):

```javascript
rules_version = '2';

service cloud.firestore {
  match /databases/{database}/documents {
    match /sessions/{sessionId} {
      allow read: if true;
      allow write: if false;
    }
    match /plot_jobs/{jobId} {
      allow read, write: if false;
    }
    match /{document=**} {
      allow read, write: if false;
    }
  }
}
```

Storage v1 rules follow the same pattern: public read under `sessions/{sessionId}/{fileName}`, no writes.

Deploy Firestore rules, indexes, and Storage rules:

```bash
npx firebase-tools deploy --project oraclegallery --config firebase/firebase.json --only firestore:rules,firestore:indexes,storage
```

If deployment fails with `serviceusage.services.use`, log in to the Firebase CLI with the Google account that owns the project or grant that account Service Usage Consumer/Owner on the Google Cloud project.

Apply Storage CORS for SVG loading in Flutter Web:

```bash
zsh -c 'set -a; source .env; set +a; uv run python scripts/configure_storage_cors.py'
```

Expected result:

```text
Updated CORS for gs://oraclegallery.firebasestorage.app
```

Manual verification: upload one session folder with SVG/TXT/READY, then confirm Storage has `artwork.svg`, `artwork_raw.svg`, `receipt.txt`, `qr.png`, `manifest.json`; confirm no visitor PNG/audio/transcript was uploaded; confirm `sessions/{id}.sessionUrl` opens `/#/session/<id>` and `sessions/{id}.qrImageUrl` opens the PNG; confirm `plot_jobs/{id}` exists for a real user session.

## 9. Pen Profiles and Calibration

Different instruments want different numbers. A profile is a named bundle of exactly the
instrument-dependent settings — `pen_width_mm`, `draw_rate`, `travel_rate`, `z_down_mm`,
`z_up_mm`, `z_feed_mm_min`, `pen_down_dwell_ms` — stored in `assets/pen_profiles.json`.
Sheet size, layout and sampling are deliberately not in a profile: those belong to the
machine and the job, so swapping pens must not disturb them.

Ships with `fineliner`, `gel` and `ballpoint`. **Those are starting points, not
measurements.** The calibration sheet is what turns them into real numbers.

Switch pens on `SETUP` → Motion speed → **Fitted pen**. Selecting a profile
overwrites only the fields above and pushes them live; there is no restart and no save
button, every control autosaves.

### Pen-down dwell

`pen_down_dwell_ms` pauses after the pen lands, before it moves. Gel and ballpoint ink
needs this or the first few millimetres of every stroke come out dry. `0` emits no `G4`
at all, so a fineliner's G-code is byte-identical to before the feature existed.

Emitted as `G4 P<seconds>` — GRBL and FluidNC read `P` in **seconds**, unlike Marlin. The
profile stores milliseconds because that is what you type; the conversion happens in one
place (`_dwell_command`) and is covered by a test, because getting it backwards would
turn a 150 ms dwell into 150 seconds on every stroke.

### The tune-adjust loop

1. Fit the pen. On `SETUP`, pick the nearest profile as a starting point.
2. On `SETUP` → Pen calibration → **GENERATE PEN CAL G-CODE**. It writes
   `pen_cal_<profile>.gcode` plus a manifest into the spool and reports the path.
3. Print it. Four blocks, each varying exactly one parameter, every row labelled with its
   own value:

   | Block | Read off |
   |---|---|
   | feed mm/min | the fastest row with no thinning or skipped segments |
   | pen-down Z mm | the shallowest row that inks fully, before the nib splays |
   | dwell ms | the shortest row with no dry stroke starts and no blobs |
   | geometry | line pairs: the finest pair still readable as two lines is your real `pen_width_mm`. Circles: the smallest that still closes. Corners: overshoot and rounding |

4. Type those numbers into `SETUP`, then **SAVE AS PROFILE** under a name that
   says which pen it is.
5. Regenerate and print once more to confirm.

The Z ladder is bounded to ±1 mm around the profile's current pen-down depth and clamped
to an absolute floor of −30 mm on every block, not just the ladder, so a mis-set depth
cannot drive the pen into the bed. The sheet is bounds-checked against the bed and raises
rather than clipping if the ladders are widened past what fits.

## 9a. Pattern Bank Paper Test

The pattern bank is covered by tests, but the defects that matter show up only on paper.
Every fix in commit 3b528bf came from plotting, not from the suite: pen-down dwell, dot
spacing and stroke ordering misbehave physically or not at all.

Build the evidence sheet:

```bash
uv run python scripts/build_bank_test_sheet.py
```

It writes `runtime/physical_tests/09_bank.svg`, sized to the current bed (sheet size minus
the direct-SVG origin), and prints the stroke count and estimated plot time. The geometry
comes from the real `sketch.js` bank generator run under Node, so what you plot is what
the sketch produces. `runtime/` is gitignored — the sheet is a local artefact, the script
is tracked, so it can be rebuilt after any defaults change.

Four bands, numbered by tick strokes down the left edge:

| Ticks | Band |
|---|---|
| 1 | `bank` generator at mix 0 |
| 2 | mix 50 |
| 3 | mix 100 |
| 4 | every motif in `assets/patterns/`, once, at generator-cell size |

Import a motif from a photo first (`CREATE` screen) if you have one — the sheet reads the
live bank, so it joins band 4 automatically, and a traced motif is the most informative
thing on the page.

Print it: `neje-gui` → `TESTS` tab → upload the SVG → `START SVG PRINT`.

### Inspection checklist

In the order things actually go wrong:

1. **Band 1 must look like a regular repeating tiling.** A visibly random field means the
   mix-0 round-robin picked up an `rng()` call and the predictability guarantee is broken.
   `test_bank_at_mix_zero_ignores_the_seed` should have caught that, so this also checks
   the test is honest.
2. **Doubled outlines** — each stroke drawn twice, slightly offset. An imported motif was
   traced with `contour` at more than 1 band. Clearest in band 4. Re-import it; the ingest
   default is already `bands=1`.
3. **Pen-down dwell blobs** — ink pooling where strokes start. Imported motifs carry far
   more and far shorter segments than hand-authored ones, so band 4 is where a pen-down
   timing problem shows first. Compare an imported motif against `arrowhead` or `lozenge`
   on the same band.
4. **Gaps where closed loops should close.** Contour loops that fail to meet mean
   `simplify_mm` was too high for that motif's scale at import.
5. **Surviving specks** — isolated dots near imported motifs in band 4 mean `despeckle_mm`
   was too low at import.
6. **Bounds** — nothing clipped, and the drawing starts at the origin inset from the
   top-left corner (`direct_svg_origin_x_mm` / `_y_mm`, currently 15/15). Anything else
   means the canvas arithmetic is off.
7. **Plot time against the script's estimate.** Much longer points at stroke ordering:
   pen-up moves leave no ink, so wasted travel is only measurable as time.

## 10. Smoke Tests

Uploader path:

```bash
uv run neje-uploader-agent
uv run neje-gui
```

In the GUI select `TEST`, press `START SYSTEM`, generate one test user session or upload an SVG to the queue, then press `PREFLIGHT`.

Check Firebase:

- Storage has `sessions/<session_id>/artwork.svg`.
- Storage has `sessions/<session_id>/receipt.txt`.
- Storage has `sessions/<session_id>/qr.png`.
- Storage has `sessions/<session_id>/manifest.json`.
- Firestore has `sessions/<session_id>`.
- `sessions/<session_id>.sessionUrl` opens the receipt page.
- `sessions/<session_id>.qrImageUrl` opens the QR PNG.
- Firestore has `plot_jobs/<session_id>`.

G-code-only diagnostic path:

```bash
uv run neje-gui
```

In the GUI select `EXHIBITION`, adjust the layout, then press `Generate G-code only`.

Check:

- `spool/*_row_*.gcode` files were written.
- `spool/*.json` contains row entries and user items before placeholder items inside each row.
- the generated files do not enable `print_enabled` or send commands to FluidNC.

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
- open `Plotter`, press `Generate G-code only`, and confirm `spool/*.gcode` and `spool/*.json` exist;
- open `Logs` and confirm supervisor/preflight lines are visible.

Exhibition smoke path:

```bash
uv run neje-uploader-agent
uv run neje-gui
```

Then in the GUI:

- select `EXHIBITION`;
- press `START SYSTEM`;
- confirm `Mac mini uploader`, `Firebase`, `Plotter`, and `Queue` statuses are not `error`;
- press `PREFLIGHT`;
- press `CONNECT` and confirm `Telnet online` plus `State: Idle`; WebUI/HTTP may be offline without blocking controller motion;
- jog to the upper-left work origin, then press `Set Work Zero`;
- only then press `START PRINT`.

## 11. Troubleshooting

If SVG images show endless loading in the website, apply Storage CORS and hard-refresh the browser.

If uploader does nothing, check that the session folder has both `*_plotter.svg` and `*_receipt.txt`, or create `READY`.

If GUI-generated test sessions do not upload, confirm that `NEJE_UPLOADER_SESSION_ROOT` points to the same folder watched by `neje-uploader-agent`.

If a session uploads twice, check `runtime/uploader.sqlite3`; the uploader uses it to remember published source folders.

If the test plotter queue needs lab material, open GUI `TEST` and use `Generate next filler`. For an uploaded Inkscape SVG, use `PRINT SVG` after preflight, work zero, and FluidNC Idle.

If plotter cannot claim Firebase jobs, check service account path and Firestore permissions.

If real plotting starts too early, use `EMERGENCY STOP`, inspect logs, and confirm `START PRINT` is still blocked unless preflight has passed, work zero is set, and FluidNC is Idle.

If the GUI does not open, check `NEJE_GUI_HOST` and `NEJE_GUI_PORT`, then open `http://127.0.0.1:8787/` manually.

If GUI-generated sessions do not become Firebase jobs, start `assets/sessions/START_ORACLE_UPLOADER.command` on the Mac mini, press `START SYSTEM` in the MacBook GUI, and confirm Mac mini agent plus GUI use the same `NEJE_UPLOADER_SESSION_ROOT`.

If `START PRINT` is blocked, run `PREFLIGHT`, fix critical failures, confirm `FluidNC` is online and Idle, then press `Set Work Zero`.

If FluidNC WebUI opens but GUI says FluidNC is not ready, check the Telnet side separately. The sender requires Telnet port `23`, a valid `?` status response, and state `Idle`; HTTP dashboard access alone is not enough. Android hotspot IPs can change, so use `CONNECT` in the GUI instead of relying on a remembered address.

If FluidNC state is `Alarm`, inspect the machine physically, then use `UNLOCK ALARM` only when safe.

If FluidNC state is `Hold`, use `RESUME` only when the tool path is safe to continue.

If a G-code stream fails with `error`, `ALARM`, disconnect, or timeout waiting for `ok`, the GUI disables print. Run `CONNECT`, inspect logs, and generate G-code only if layout needs inspection before starting again.

If the Logs panel is empty, perform an action such as `PREFLIGHT` or `CHECK`, then refresh logs. Logs are written to `NEJE_ORACLE_LOGS_ROOT/oracle_supervisor.log`.
