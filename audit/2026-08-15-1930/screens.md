# Screen inventory — operator GUI at 1280×800 (sandbox port 8799)

Captured by `uv run python scripts/measure_gui.py --dump --out audit/2026-08-15-1930/screens`
(CDP-driven headless Chrome; Maestro's web driver cannot dump hierarchies).
Element dumps for every view: `screens/dump.json` (visible elements: tag, classes, text,
bounds, font size). Deterministic measurements: `measurements.json`.

| View | How reached | Screenshot |
|---|---|---|
| PRINT | top-bar tab PRINT | screens/print.png |
| CREATE (SKETCH) | tab CREATE (default source) | screens/create.png, screens/create_sketch.png |
| CREATE/TEXTURE | CREATE → segmented toggle TEXTURE | screens/create_texture.png |
| CREATE/IMAGE | CREATE → IMAGE | screens/create_image.png |
| CREATE/TEXT | CREATE → TEXT | screens/create_text.png |
| CREATE/SHEET | CREATE → SHEET | screens/create_sheet.png |
| CREATE/MOTIF | CREATE → MOTIF | screens/create_motif.png |
| SETUP (MACHINE) | tab SETUP (default section) | screens/setup.png, screens/setup_machine.png |
| SETUP/PEN | SETUP → PEN | screens/setup_pen.png |
| SETUP/SHEET | SETUP → SHEET | screens/setup_sheet.png |
| SETUP/VERIFY | SETUP → VERIFY | screens/setup_verify.png |
| SETUP/ADVANCED | SETUP → ADVANCED | screens/setup_advanced.png |

Persistent chrome on every view: top bar (ORACLE wordmark, 3 tabs, FluidNC state chip,
X/Y position readout, Require Firebase switch, STOP PRINT, EMERGENCY STOP) and the left
machine rail (Next action card, Manual motion card: jog cross, PEN UP/DOWN, HOME, SET WORK ZERO).

## NOT COVERED

- **Legend dialog** (PRINT `?`) and **stream arm dialog** (CREATE/SKETCH) — modals; exercised in the flow suite, no hierarchy dump.
- **Diagnostics expansion** (SETUP/ADVANCED) — collapsed by default; contents (Mac mini uploader, thermal printer, log viewer) not expanded in the dump.
- **Hardware-dependent states**: FluidNC connected/Idle/Run/Alarm chip states, live position readout, print-in-progress progress bar — sandbox has no plotter. Audited as rendered in the disconnected state only.
- **Firebase-backed queue states** — Require Firebase off in sandbox.
