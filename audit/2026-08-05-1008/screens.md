# Screens — audit run 2026-08-05-1008

App: Neje Oracle operator GUI (NiceGUI web, dry-run mode) at http://127.0.0.1:8787, branch uxui-cleanup (pre-dedup baseline). Device: Maestro Chromium (CLI fallback — MCP server held a dead driver session).

| Screen | How reached | Screenshot | Hierarchy |
|---|---|---|---|
| 01 Connection* | app boot (default/restored tab) | screens/01_connection.png | not captured |
| 02 Calibration | tap "2 CALIBRATION" | screens/02_calibration.png | not captured |
| 03 Tests | tap "3 TESTS" | screens/03_tests.png | not captured |
| 04 Work | tap "4 WORK" | screens/04_work.png | not captured |
| 05 Exhibition | tap "5 EXHIBITION" | screens/05_exhibition.png | not captured |
| 06 Generative | tap "6 GENERATIVE" | screens/06_generative.png | not captured |
| 07 Sketch page (iframe content, direct) | open /generative/index.html | screens/07_sketch_page.png | not captured |

*Screen 01 may show the workspace restored from the persisted `gui_workspace` (tests) rather than connection — subagents should judge by content, not filename.

## States coverage
- Error state: FluidNC offline toast visible in screenshots (dry-run, no controller on LAN).
- Loading: NiceGUI initial render observed during crawl waits.
- Empty: preview panel with placeholder content.

## NOT COVERED
- View hierarchies (Maestro web hierarchy requires a live session per screen; CLI run ends the session) — tap-target/alignment measurements are therefore pixel-based only.
- Real print flow (requires physical FluidNC).
- SVG file upload dialog (native file picker not drivable via Maestro web).
- Generative iframe interior interactions from the host page (iframe boundary); covered separately as screen 07.
- Public Flutter gallery (separate surface; out of this run's scope).
