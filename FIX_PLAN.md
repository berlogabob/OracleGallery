# Oracle urgent fix plan

Source: `FIX.md`

Date: 2026-05-05

Status updated: 2026-05-05

Legend:

- `[x]` done
- `[~]` partially done
- `[ ]` pending

## Core diagnosis

The most urgent blocker is FluidNC connectivity. The current code treats FluidNC as a raw TCP endpoint on `NEJE_PLOTTER_FLUIDNC_HOST:NEJE_PLOTTER_FLUIDNC_PORT`, defaulting to `fluidnc.local:23`.

Current implementation:

- `src/neje_oracle/transport.py` only uses `socket.create_connection(...)`.
- `check_connection()` only checks whether TCP port 23 opens.
- `send()` writes G-code lines blindly and does not wait for `ok`, `error`, `Alarm`, status, idle/run state, or WebUI availability.
- GUI checks call this same TCP-only path.
- User-visible FluidNC works at `http://10.198.21.74/#/dashboard`, which proves HTTP/WebUI reachability, not necessarily Telnet port 23 reachability.

This means the GUI can show FluidNC offline even when the dashboard works, and real streaming can fail even if the TCP port opens.

## Target exhibition flow

1. Mac mini runs TouchDesigner and only the uploader agent.
2. TouchDesigner creates a real session folder.
3. Uploader uploads raw session artifacts to Firebase.
4. MacBook GUI/supervisor detects the uploaded session, downloads SVG, normalizes it with current GUI scale settings, uploads normalized SVG back to Firebase, and only then releases the print job.
5. Plotter prints continuously by rows:
   - user jobs have priority at the next safe row boundary;
   - idle/filler symbols fill empty spaces;
   - no interruption in the middle of a symbol or row;
   - physical FluidNC output is enabled only after explicit checks and arming.
6. Flutter gallery shows the normalized public SVG and receipt page.

## Phase 0: Safety and reproducibility `[x]`

Goal: make failures visible before changing behavior.

- Add a clear diagnostics panel/state for FluidNC:
  - configured HTTP URL;
  - configured Telnet host/port;
  - HTTP reachable/not reachable;
  - Telnet reachable/not reachable;
  - handshake result;
  - last command response;
  - last transport error.
- Save every FluidNC check/send attempt to `logs/oracle_supervisor.log`.
- Update `.env.example` and `.env.plotter.example` to use the real machine shape:
  - `NEJE_PLOTTER_FLUIDNC_HTTP_URL=http://10.198.21.74`
  - `NEJE_PLOTTER_FLUIDNC_TELNET_HOST=10.198.21.74`
  - `NEJE_PLOTTER_FLUIDNC_TELNET_PORT=23`
  - `NEJE_PLOTTER_FLUIDNC_PROTOCOL=auto`
- Keep default real sending blocked until diagnostics pass.

Status:

- [x] FluidNC diagnostics are visible in `Plotter Console`.
- [x] HTTP URL, Telnet host/port, status, position, and messages are shown.
- [x] `.env.example` and `.env.plotter.example` use `10.198.21.74`.
- [x] Real sending remains blocked by mode, preflight, arm, and FluidNC `Idle` checks.
- [~] `NEJE_PLOTTER_FLUIDNC_PROTOCOL=auto` was not added; implementation uses Telnet for streaming and HTTP for diagnostics. This is intentional for the current fix.

Files:

- `src/neje_oracle/config.py`
- `src/neje_oracle/models.py`
- `src/neje_oracle/store.py`
- `src/neje_oracle/supervisor.py`
- `src/neje_oracle/gui_service.py`
- `.env.example`
- `.env.plotter.example`
- `RUNBOOK.md`

## Phase 1: Replace FluidNC transport with real protocol handling `[x]`

Goal: make FluidNC connection actually work and fail safely.

Implement a new transport layer:

- Split connection checks:
  - HTTP/WebUI check: verify `http://10.198.21.74` responds.
  - Telnet check: verify port 23 opens.
  - Handshake check: read FluidNC greeting or send a harmless status/probe command and parse response.
- Add protocol mode:
  - `auto`: prefer safe Telnet streaming if Telnet handshake works; otherwise report exactly what failed.
  - `telnet`: use line streaming with response handling.
  - `dry-run`: write only to spool.
  - optional later: `usb-serial` fallback if Wi-Fi is unstable.
- Replace blind `sendall()` loop with sender logic that:
  - sends one line or a bounded buffer;
  - waits for `ok`;
  - stops and marks job failed on `error`, `Alarm`, disconnect, timeout;
  - records progress based on acknowledged lines, not just written lines;
  - supports safe stop before the next row/sheet, not mid-command.
- Add a manual `FluidNC probe` action in GUI:
  - show WebUI online;
  - show Telnet online;
  - show controller state if available;
  - show required fix if Telnet is disabled.

Important implementation note:

- Reaching `http://10.198.21.74/#/dashboard` only proves HTTP is enabled.
- If Telnet is disabled in FluidNC settings, Python TCP streaming on port 23 will never work.
- The GUI must explain this directly instead of showing a generic offline status.

Files:

- Replace/extend `src/neje_oracle/transport.py`
- Add tests in `tests/test_transport.py`
- Update `src/neje_oracle/preflight.py`
- Update `src/neje_oracle/gui_support.py`
- Update `src/neje_oracle/supervisor.py`

Tests:

- Fake HTTP server reachable, Telnet closed -> GUI reports “WebUI online, Telnet closed”.
- Fake Telnet server sends `ok` -> send succeeds.
- Fake Telnet server sends `error` -> job fails and does not mark printed.
- Timeout waiting for `ok` -> job fails and logs exact command.

Status:

- [x] `FluidNCTransport.probe()` checks HTTP, Telnet, `?`, and `$G`.
- [x] `send()` waits for `ok` line-by-line.
- [x] `error`, `ALARM`, disconnect, and timeout fail the transport.
- [x] Progress is based on acknowledged G-code commands.
- [x] GUI has `Connect / Probe`.
- [x] Tests were added in `tests/test_transport.py`.
- [x] Plotter daemon disables print and does not mark jobs `printed` on transport failure.

## Phase 2: Make TEST mode fully functional `[~]`

Goal: TEST mode must be the place where every subsystem can be checked without exhibition risk.

Required behavior:

- TEST mode allows:
  - FluidNC diagnostics;
  - dry-run G-code generation;
  - optional real low-risk probe commands;
  - test session generation;
  - idle bank generation;
  - layout/scale tuning;
  - row preview and row progress.
- TEST mode does not send real drawing jobs unless a separate explicit test-send button is armed.
- EXHIBITION DRY uses real queues but dry-run only.
- EXHIBITION REAL uses real queues and real FluidNC only after preflight and arm.

GUI changes:

- Add a clear top-level step order:
  1. `CHECK CONNECTIONS`
  2. `PREFLIGHT`
  3. `GENERATE / LOAD QUEUE`
  4. `START PRINT`
  5. `STOP AFTER ROW/SHEET`
- Buttons must have short help text and disabled states explaining why they are disabled.

Files:

- `src/neje_oracle/gui_service.py`
- `src/neje_oracle/gui_ui.py`
- `src/neje_oracle/gui_modes.py`
- `src/neje_oracle/supervisor.py`

Status:

- [x] TEST mode can run FluidNC diagnostics/manual control.
- [x] TEST mode can run dry-run sheet generation.
- [x] TEST mode still supports fake sessions and idle bank.
- [x] Plotter UI sequence is now explicit: `Connect`, `Manual control`, `Print`.
- [~] A separate armed “real tiny test-send” action was not added; physical output remains intentionally gated.
- [x] Runtime/GUI now show current row and sheet progress. Preview highlight for current row is still pending.

## Phase 3: Reorganize GUI layout `[~]`

Goal: hardware/control on the left, symbols/generation on the right, preview in the center.

New layout:

- Left column: hardware and operations only:
  - `System`
  - `FluidNC`
  - `Plotter`
  - `Mac mini uploader`
  - `Logs`
- Center:
  - sheet/row preview;
  - current print state;
  - row and symbol progress.
- Right column: symbols only:
  - `Symbol scales`
  - `Test generator`
  - `Idle filler bank`
  - `Normalization queue`

Mode-specific visibility:

- `TEST`: right-side generator blocks are enabled.
- `EXHIBITION DRY`: test generator hidden or locked; normalization and real queue visible.
- `EXHIBITION REAL`: test generator hidden; only real queue/normalization/printing controls visible.

Files:

- `src/neje_oracle/gui_service.py`
- `src/neje_oracle/gui_ui.py`

Status:

- [x] Plotter/hardware control was compacted into `Plotter Console`.
- [x] Duplicated top print buttons and status pills were removed.
- [x] Plotter controls now fit better in the left column.
- [~] Full “hardware left / symbols right” re-layout is not complete. It is paused because current work is restricted to plotter/G-code/FluidNC/GUI.

## Phase 4: Refactor printing from whole-sheet streaming to row streaming `[~]`

Goal: match exhibition behavior: continuous row-based plotting.

Current behavior:

- `PlotterDaemon.run_cycle()` now builds a full sheet layout, groups it into rows, and streams one G-code file per row.
- Before each row it checks the user queue, places user jobs first, then fills remaining row cells with idle symbols.
- The physical sheet is still the reload unit: after all rows are streamed, daemon enters `paused_for_reload`.

Required behavior:

- Introduce explicit `PrintRow` and `PrintCell` model if row orchestration needs to become reusable outside `PlotterDaemon`.
- Build next printable row from:
  - user queue first;
  - idle/filler queue second.
- Stream row G-code as the atomic unit.
- New user session can become next row, but never interrupts a current symbol or row.
- Keep sheet reload logic for v1 physical workflow.
- Store progress as:
  - current sheet;
  - current row;
  - current symbol;
  - acknowledged G-code lines.

Files:

- `src/neje_oracle/models.py`
- `src/neje_oracle/layout.py`
- `src/neje_oracle/svg_gcode.py`
- `src/neje_oracle/plotter_daemon.py`
- `src/neje_oracle/store.py`
- `src/neje_oracle/gui_support.py`
- `src/neje_oracle/gui_service.py`

Tests:

- User jobs are placed before idle jobs at the next row boundary.
- New user job during row streaming waits until the next row.
- Stop command remains `Stop After Sheet` in v1; emergency stop/feed hold is the only immediate stop path.
- Failed row does not mark user job printed.

Status:

- [x] Basic row streaming implemented.
- [x] Layout grouping by row implemented.
- [x] User jobs are claimed before each row, so a late user job can enter the next row.
- [x] Row G-code progress and sheet progress are stored in runtime state and shown in GUI.
- [x] Related safety improvement completed: manual jog/home pauses print before movement and is blocked while G-code is actively streaming.
- [x] Transport failures do not mark user jobs `printed`.
- [ ] Explicit `PrintRow`/`PrintCell` dataclasses are not added yet; current implementation uses existing `SheetItem`/`SheetPlacement`.
- [ ] Current-symbol progress is not implemented yet; progress is row + acknowledged G-code lines.
- [ ] Preview does not yet highlight current row.

## Phase 5: Add Firebase normalization handoff on MacBook `[ ]`

Goal: real user SVGs must be normalized and scaled before gallery display and printing.

Current likely issue:

- Mac mini uploader publishes session artifacts directly.
- Plotter may consume user SVGs without MacBook normalization/scales.

Required pipeline:

- Mac mini uploader uploads raw SVG as `artwork_raw.svg`.
- Firestore session state becomes `uploaded_raw` or `needs_normalization`.
- MacBook supervisor watches Firebase for sessions needing normalization.
- MacBook downloads raw SVG.
- MacBook applies canonical normalization and GUI scale settings.
- MacBook uploads normalized `artwork.svg`.
- MacBook updates Firestore:
  - `status=published`;
  - `normalizationStatus=normalized`;
  - `svgUrl` points to normalized SVG with cache-busting;
  - plot job becomes `pending`.
- Flutter always reads normalized `svgUrl`.

Files:

- `src/neje_oracle/uploader.py`
- `src/neje_oracle/firebase_io.py`
- `src/neje_oracle/firebase_svg_normalizer.py`
- `src/neje_oracle/supervisor.py`
- `src/neje_oracle/gui_service.py`
- Firestore rules/docs if schema changes.

Tests:

- Raw upload does not become printable until normalized.
- Normalizer applies per-symbol scale from GUI config.
- Reprocessing one Firebase session updates Storage and Firestore.

Status:

- [ ] Not implemented in this FluidNC-focused pass.
- [ ] Existing uploader/normalizer utilities remain, but the supervisor handoff pipeline is not complete.

## Phase 6: Update Flutter gallery from WebsiteWireframe `[ ]`

Goal: use `assets/WebsiteWireframe` as the new site map/layout/style reference.

Inputs:

- `assets/WebsiteWireframe/Oracle_website_wireframe/Oracle Website Wireframes.html`
- `assets/WebsiteWireframe/Oracle_website_wireframe/Oracle Website Wireframes-print.html`
- Video URL: `https://youtu.be/kMwNTh0pS1k`

Required work:

- Review wireframe pages and extract:
  - site map;
  - page sections;
  - navigation;
  - visual hierarchy;
  - receipt/session layout.
- Update `public_gallery` Flutter app to match the new wireframe structure.
- Keep QR route stable:
  - `#/session/<id>`
- Add embedded video section using the provided YouTube URL.
- Keep gallery asset policy:
  - no visitor photos;
  - no audio;
  - no raw transcript;
  - only normalized SVG and receipt/public metadata.

Files:

- `public_gallery/lib/**`
- `public_gallery/pubspec.yaml` if new package is needed.
- `README.md`
- `RUNBOOK.md`

Tests:

- `cd public_gallery && flutter analyze`
- `./scripts/build_gallery_docs.sh`
- Manual check of home/about/library/session routes.

Status:

- [ ] Not implemented. User explicitly paused Flutter work during current plotter/G-code/FluidNC pass.

## Phase 7: Documentation and operator runbook `[~]`

Goal: make GUI usage obvious to a non-developer operator.

Required docs:

- One-page operator flow:
  - Mac mini: double-click only `assets/sessions/START_ORACLE_UPLOADER.command`.
  - MacBook: double-click `start_oracle_gui.command`.
  - In GUI: numbered steps from connection check to printing.
- FluidNC troubleshooting:
  - WebUI online but Telnet offline.
  - wrong IP;
  - wrong Wi-Fi;
  - Telnet disabled;
  - port blocked;
  - controller in alarm;
  - timeout waiting for `ok`;
  - USB fallback.
- TEST / EXHIBITION DRY / EXHIBITION REAL explanation.
- Recovery procedures:
  - stop after row/sheet;
  - reload material;
  - failed Firebase;
  - failed FluidNC;
  - restart Mac mini uploader.

Files:

- `README.md`
- `RUNBOOK.md`
- `.env.example`
- `.env.plotter.example`

Status:

- [x] FluidNC setup/troubleshooting documented.
- [x] Plotter Console sequence documented.
- [x] Manual jog/home safety behavior documented.
- [~] Full one-page operator flow should be revisited after row streaming and normalization handoff are implemented.

## Immediate implementation order

1. `[x]` FluidNC diagnostics and config split.
2. `[x]` Real Telnet handshake/ack sender with tests.
3. `[x]` GUI FluidNC panel and clearer button order.
4. `[~]` Move generator/scales/filler blocks to the right column.
5. `[ ]` Row-based print model.
6. `[ ]` Firebase normalization handoff.
7. `[ ]` Flutter wireframe update.
8. `[~]` Documentation update.

Do not start with Flutter or layout polish before FluidNC transport is fixed. If FluidNC transport is wrong, the rest of the operator GUI gives false confidence.
