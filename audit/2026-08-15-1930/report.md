# UX/UI Audit — Oracle Operator GUI (web, headless Chromium 1280x800 via CDP, sandbox :8799) — 2026-08-15

## Executive Summary

**Release verdict: NOT READY** — one severity-4 finding is open (F-001: the safety-critical stop/recovery buttons bypass the design system entirely, rendering white-on-gold at 1.7:1 contrast and two different "danger reds").

41 deduplicated findings (1 sev-4, 8 sev-3, 19 sev-2, 13 sev-1) from 69 raw findings across five audit dimensions, over 12 views. Task success is 4/4 flows (100%), and the app is structurally far healthier than the previous 7-tab IA — but the three most important issues are all in the safety path: **F-001** (stop buttons outside the button system, illegible labels, off-palette colors), **F-002** (four overlapping stop-family actions with no scope differentiation — EMERGENCY STOP / STOP PRINT / STOP SYSTEM / RESET-ABORT), and **F-003** (destructive RESET / ABORT sits 7–8px from the RESUME/UNLOCK recovery buttons an operator reaches for under alarm pressure).

## Background & Objectives

- **App:** Oracle Operator GUI (NiceGUI/Quasar operator panel for the Neje/FluidNC pen plotter), branch `redesign/operator-neutral`.
- **Trigger:** This is the **baseline audit for the neutral-theme redesign**. The prior audit (2026-08-05) targeted the now-dead 7-tab IA (Connection/Calibration/Tests/Work/Exhibition/Generative); the app has since collapsed to 3 screens (PRINT / CREATE / SETUP), so this run establishes the new baseline rather than a straight run-over-run comparison.
- **Device:** headless Chromium 1280x800 driven via CDP against the sandbox instance on port 8799.

## Methodology

- **Coverage:** 12 views audited (PRINT; CREATE with SKETCH/TEXTURE/IMAGE/TEXT/SHEET/MOTIF sources; SETUP with MACHINE/PEN/SHEET/VERIFY/ADVANCED sections), plus the persistent chrome (top bar + machine rail) present on every view. Inventory: `screens.md`; per-view element dumps in `screens/dump.json`.
- **Tools:** hierarchy dumps and screenshots via `scripts/measure_gui.py --dump` over CDP — Maestro's web driver cannot dump hierarchies, so measurement is CDP-based. Deterministic measurements in `measurements.json`, tuned for desktop: WCAG 2.5.8 24px target minimum, alignment near-miss detection, font-size census, and **token contrast computed directly from `tokens.py`** (15 token pairs, `measurements.json → token_contrast`).
- **Flow suite:** 4 CDP flows, all passed — navigate-all (14 steps), legend-dialog (3), text-preview (3), verify-gcode (3, produced a real G-code artifact). Results: `flows-results.json`.
- **Frameworks:** Nielsen 10 heuristics, UX laws (Fitts/Hick/Miller/Jakob), visual design (typography/color/Gestalt/WCAG), design-system consistency checks, 5 system states, ISO 9241-11 / HEART.
- **NOT covered** (from `screens.md`): legend and stream-arm modal hierarchies (exercised in flows, no dump); Diagnostics expansion on SETUP/ADVANCED (collapsed); all hardware-dependent states — FluidNC connected/Idle/Run/Alarm chip states, live position, print-in-progress — the sandbox has no plotter, so everything was audited in the disconnected state; Firebase-backed queue states (Require Firebase off in sandbox).

## Metrics

| Metric | Value | Previous (2026-08-05) | Δ |
|---|---|---|---|
| Task success rate | 4/4 flows = **100%** | 2/2 = 100% | = (suite doubled) |
| Avg steps per flow | 5.75 (14/3/3/3) | 8.0 | −2.25 |
| Avg time on task (automation) | 9.6 s | 13 s | −3.4 s |
| Errors / crashes in flows | 0 | 0 | = |
| Findings (deduped) | **41** | 39 | +2 (raw: 69 before dedupe) |
| — severity 4 | 1 | 1 | = |
| — severity 3 | 8 | 8 | = |
| — severity 2 | 19 | 22 | −3 |
| — severity 1 | 13 | 8 | +5 |
| Defect density | **3.42 / view** (41/12) | 5.57 / screen (39/7) | −2.15 |
| Severity-weighted total | 79 | 80 | −1 |

Previous-run verdict was NOT READY; note the IA changed completely between runs, so per-finding deltas are a **baseline reset** (see Trend), not a like-for-like trend.

### HEART scorecard

| Dimension | This audit | Signal |
|---|---|---|
| **H**appiness (proxy) | Severity-weighted findings = 79 (vs 80 prior, on a smaller, denser-per-view surface). 9 findings at sev ≥3, all frustration-grade: illegible stop buttons, misleading state chip, occluding toast. | Proxy only; real signal arrives via operator sessions (below). |
| **E**ngagement (proxy) | Friction in the highest-frequency loop: every CREATE parameter tweak requires a manual REFRESH PREVIEW press (F-029), one detour step per iteration; inconsistent with SETUP/ADVANCED's live filters. | Fixing F-029 is the single highest-leverage engagement change. |
| **A**doption (narrative) | First-session comprehension is hindered by jargon (F-011 WEBUI/TELNET/INPUTS/MODAL, F-021 font ID `zzBVFNTL`, F-033 FAIL/SKIP 0/177) and undesigned empty states (F-016, F-017). | — |
| **R**etention (narrative) | Recovery quality is the risk: the Next-action card gives the wrong unblock instruction while offline (F-005), and the state chip misreports offline as PAUSED (F-004). Trust in recovery is what keeps a remote/unattended operator using the tool. | — |
| **T**ask success (measured) | **100%** (4/4 flows), 0 errors, avg 5.75 steps / 9.6 s per flow. | Measured directly from `flows-results.json`. |

**Instrumentation now exists — no recommendation needed:** `src/neje_oracle/shared/telemetry.py` writes `logs/operator_events.jsonl` (task_start/ok/fail with durations, screen_switch) and `scripts/operator_report.py` summarizes per session. The next audit can therefore replace the H/E/T proxies above with real numbers from operator sessions (task success and durations for H/T, screen-switch and retry patterns for E).

## Key Findings

### Severity 4

**F-001 · sev 4 · DS-BTN-1 · screen: PRINT top bar (all views) + SETUP/MACHINE + PRINT run card** — The safety-critical stop/recovery controls are the only buttons outside the app's 3-intent button system: EMERGENCY STOP and STOP PRINT are raw `ui.button()` calls (`service.py:239,241`) on Quasar defaults `negative` #C10015 / `warning` #F2C037 instead of `danger_action_button()`/DANGER #8C2F1D; UNLOCK, RESET / ABORT (`connection.py:52,54`), STOP (`work.py:24`) and Confirm (`context.py:758`) bypass it the same way. Two different danger reds in one app; STOP PRINT/UNLOCK are white 14px on bright gold. Merged from 5 raw findings (DS-BTN-1 x2, DS-A11Y-1, VD-TYPE-3, VD-COL-3). Evidence: `screens/print.png`; white on #F2C037 = 1.7:1 (AA 4.5:1), CREAM on DANGER = 7.54:1 passes. Recommendation: route all six sites through the intent buttons and map Quasar warning/negative/positive → WARN/DANGER/OK in `ui.colors()`.

### Severity 3

**F-002 · sev 3 · LAW-HICK-1 · PRINT + SETUP/MACHINE** — Four stop-family actions with overlapping names and no scope hints (EMERGENCY STOP, STOP PRINT, STOP SYSTEM, RESET / ABORT); STOP SYSTEM is styled identically to START SYSTEM 40px above it, and SET WORK ZERO is a third identical solid primary on the same screen (merged: H4, VD-HIER-1). Evidence: `screens/print.png`, dump.json. Recommendation: one always-visible emergency action, outcome-based labels with consequence text, one solid primary per screen.

**F-003 · sev 3 · LAW-FITTS-2 · SETUP/MACHINE** — Destructive RESET / ABORT (danger-red filled, widest in row) sits 8px from RESUME and 7px from UNLOCK; an alarm-recovery miss lands on the destructive action. Evidence: `screens/setup_machine.png`; UNLOCK 62x32 @(418,260), RESUME 68x34 @(487,259), RESET / ABORT 106x32 @(563,260). Recommendation: ≥24px separation + confirm/press-and-hold.

**F-004 · sev 3 · H1 · persistent chrome, all views** — Disconnected state communicated by four conflicting signals: chip says 'OPERATOR PAUSED' while actually offline; bare 'Not ready' with no reason; 'Blocked while G-code streams.' shown permanently when nothing streams; jog buttons enabled while offline; and the paused state is named three ways (OPERATOR PAUSED / print paused / START SYSTEM–RESUME) with no control carrying the chip's wording (merged: NAV-5, ST-IDLE). Evidence: `screens/print.png`, identical captions across all 12 dumps. Recommendation: connection-state-first chip vocabulary (OFFLINE/CONNECTING/IDLE/RUN/PAUSED), state-driven captions, disabled jog while offline.

**F-005 · sev 3 · ST-ERROR · Next-action card, all views** — While offline, the Next-action card instructs 'Jog to the paper origin, then SET WORK ZERO' and its blockers line ('work zero · print paused') omits the connection — the one blocker that makes jogging impossible; the banner says the opposite ('press CONNECT on SETUP'). Evidence: `screens/print.png`; 0 of 12 views list connection as a blocker. Recommendation: rank 'plotter offline' first and switch Next-action copy to the connect instruction until reachable. *(Kept separate from F-004: distinct fix in the blocker-ranking logic.)*

**F-006 · sev 3 · H1 · offline toast, all views** — The persistent 'Plotter offline' toast floats over interactive content everywhere: covers half of REFRESH PREVIEW on CREATE, the filename/progress strip on PRINT (whose status line is clipped below an overflow-hidden 800px viewport, unreachable), and the Random coarse/fine sliders on SETUP/ADVANCED; dismissing it removes the offline warning entirely (merged from 4 dimensions: H1, IXD-VIS, VD-RESP-1, ST-ERROR). Evidence: `screens/create_texture.png`; DISMISS @(846,746) in all 12 dumps. Recommendation: reserved banner strip or top-bar slot that reflows content; toasts for transient events only.

**F-007 · sev 3 · H5 · SETUP/VERIFY, CREATE/IMAGE, CREATE/MOTIF** — Prerequisite-gated primaries render fully enabled next to their own 'No SVG/image/picture selected' text (START SVG PRINT, PRINT IMAGE, SAVE TO BANK). Evidence: `screens/setup_verify.png`. Recommendation: disable with reason until input valid.

**F-008 · sev 3 · H2 · CREATE/IMAGE** — The Pen lifts slider shows the operator a literal unevaluated code expression as its value: `value >= 1024 ? 'off' : value`; the 'off' state is invisible and the only readout is broken (merged from 4 dimensions: H2, IXD-FEED, DS-FDBK-1, ST-IDLE). Evidence: `screens/create_image.png`. Recommendation: fix the label binding; add a render test failing on `?`/`>=` in slider labels.

**F-009 · sev 3 · DS-TYPE-1 · all screens** — The design system's typographic identity is silently absent: FONT_BODY/DISPLAY/LOGO tokens (EB Garamond, Cinzel) are declared and exported but no CSS rule or @font-face consumes them; everything renders default Quasar sans. Evidence: `screens/print.png`; 0 `var(--font-*)` references in PAGE_STYLE. Recommendation: wire or delete — an explicit neutral-theme decision.

### Severity 2

**F-010 · sev 2 · DS-A11Y-1 · top-bar state chip** — 'OPERATOR PAUSED' is 12px bold GOLD_DIM on cream at 4.36:1, failing AA-normal at the size used (merged: VD-TYPE-3). Evidence: `screens/print.png`, token_contrast. Recommendation: darken WARN to ≥4.5:1 (~#7A6228) or set chip text in INK.

**F-011 · sev 2 · H2 · SETUP/MACHINE** — Connection status in protocol jargon ('WEBUI offline', 'TELNET offline', 'INPUTS none', 'MODAL -') on the exact screen the operator-language banner sends people to (merged: NAV-5). Evidence: `screens/setup_machine.png`. Recommendation: one operator-level verdict line; protocol pills as secondary detail.

**F-012 · sev 2 · LAW-FITTS-2 · top bar** — Routine STOP PRINT sits 32px from EMERGENCY STOP in the same corner cluster; corner throws land on the e-stop. Evidence: `screens/print.png`. Recommendation: isolate EMERGENCY STOP; move STOP PRINT context-local.

**F-013 · sev 2 · H9 · offline toast + SETUP/MACHINE** — Raw developer output in the operator error ('FluidNC Telnet offline: :23; HTTP offline ([Errno 61] Connection refused)'), truncated with no expansion on the fix-it screen. Evidence: `screens/setup_machine.png`. Recommendation: plain line + expandable details.

**F-014 · sev 2 · H4 · numeric fields app-wide** — Decimal separators inconsistent within single cards ('0,3' vs '0.5'; helper '0.25' vs field '0,25') on G-code-feeding parameters where a misparsed '0.3' can become 3 mm (merged from 3 dimensions: H4, IXD-CONS, DS-FORM-1). Evidence: `screens/setup_pen.png`. Recommendation: dot-decimal display everywhere, accept both on input.

**F-015 · sev 2 · LAW-FITTS-1 · PRINT** — The '?' legend button, sole entry to the ring/dot legend, is a 17px-wide target — the app's only genuine sub-24px control (merged from 3 dimensions: LAW-FITTS-1, H7, DS-A11Y-1). Evidence: measurements.json {w:17, h:34, min:24}, `screens/print.png`. Recommendation: ≥24px (ideally 32x32 + 'Legend' label).

**F-016 · sev 2 · ST-EMPTY · SETUP/VERIFY** — The SVG dropzone is a bare black bar reading '0.0B / 0.00%' with no instruction, while the identical component on CREATE/IMAGE and CREATE/MOTIF is labeled (merged from 3 dimensions: ST-EMPTY, H4, VD-GES-2). Evidence: `screens/setup_verify.png`. Recommendation: same 'Drop an Inkscape SVG here…' label; hide the counter until uploading.

**F-017 · sev 2 · ST-EMPTY · CREATE/SHEET** — Sheet preview empty state is a bare hyphen ('-') where sibling tabs show designed guidance. Evidence: `screens/create_sheet.png`. Recommendation: 'Choose an image folder above to fill the sheet preview.'

**F-018 · sev 2 · H6 · CREATE/SHEET** — 'Image folder' is a free-text server-side path field with no picker, validation, or example. Evidence: `screens/create_sheet.png`. Recommendation: folder picker/recents + found-N-images validation on blur.

**F-019 · sev 2 · H1 · CREATE/TEXT** — Text preview renders as a small clipped box pinned to the canvas corner (glyph stems cut off) instead of on the sheet at origin/scale; the operator cannot verify what will plot (merged: ST-SUCCESS). Evidence: `screens/flow_text_preview.png`; ~227x98px box in a ~686x670px canvas. Recommendation: fit-and-center at actual origin/scale like other sources.

**F-020 · sev 2 · H2 · SETUP/VERIFY success toast** — G-code success notification is a raw `/var/folders/…` temp path with no next step (merged: ST-SUCCESS). Evidence: `screens/flow_verify_gcode.png`. Recommendation: '…written to spool — press START TEST PRINT'; paths to logs.

**F-021 · sev 2 · H2 · CREATE/TEXT** — Font selector shows the internal ID `zzBVFNTL` with no human name or glyph preview. Evidence: `screens/create_text.png`. Recommendation: readable names, render options in their own face.

**F-022 · sev 2 · VD-COL-2 · left rail, all views** — One class (.oracle-helper, 12px RUST) carries both neutral guidance and live blocking state ('Blocked while G-code streams.', 'Not ready', blockers) — cautions indistinguishable from captions; WARN/DANGER tokens unused here. Evidence: `screens/print.png`. Recommendation: split the class; state text in WARN/DANGER with icon.

**F-023 · sev 2 · VD-TYPE-1 · SETUP/PEN, SETUP/VERIFY, CREATE/MOTIF** — Multi-line procedure prose (Z-tune, pen calibration, motif import) set at 12px; nothing in the app exceeds 14px. Evidence: measurements.json font census, `screens/setup_verify.png`. Recommendation: 14–16px for procedure text.

**F-024 · sev 2 · VD-TYPE-2 · SETUP/VERIFY, PEN, ADVANCED** — Helper paragraphs run ~1007px / 150–180 chars per line (2x the 85-char ceiling) on exactly the calibration-procedure text. Evidence: `screens/setup_verify.png`. Recommendation: cap prose at ~65ch.

**F-025 · sev 2 · DS-COL-1 · CREATE/IMAGE, SKETCH, SETUP/ADVANCED, PEN** — Two rusts adjacent: token RUST #8B4513 vs legacy `text-[#8f4f2b]` (17 uses + preview.py:561 fill). Evidence: `screens/create_image.png`. Recommendation: sweep to helper_text(); ratchet to zero in test_gui_design_system.py.

**F-026 · sev 2 · DS-TYPE-1 · SETUP/ADVANCED (pattern app-wide)** — Two section-title treatments on one screen: section_title() 13px vs 15 raw `text-sm font-bold` sites; 18 raw ui.card() sites bypass the card() helper. Evidence: `screens/setup_advanced.png`, dump.json. Recommendation: convert to card(title=…, helper=…).

**F-027 · sev 2 · DS-TYPE-1 · SETUP/ADVANCED** — One semantic role (helper line) rendered three ways simultaneously (12px token rust / 12px legacy rust / 10px bold uppercase legacy rust). Evidence: `screens/setup_advanced.png`. Recommendation: single helper_text() + one micro_label() if genuinely distinct.

**F-028 · sev 2 · DS-NAV-1 · top bar** — .workspace-tabs styled twice with conflicting heights (34px vs 42px); the 42px rule wins, so tabs overflow the 40px bar by 2px top and bottom (y=-1, h=42 in every dump). Evidence: `screens/print.png`, service.py:49-50 vs 115-116. Recommendation: one rule, one number.

### Severity 1

**F-029 · sev 1 · FLOW-2 · CREATE tabs** — Every parameter tweak requires a manual REFRESH PREVIEW press; previews never auto-update, one detour step per iteration in the highest-frequency loop, inconsistent with SETUP/ADVANCED's live filters. Evidence: `screens/flow_text_preview.png`, flow step data. Recommendation: debounced auto-refresh or a stale-preview marker.

**F-030 · sev 1 · LAW-MILLER-1 · CREATE/MOTIF** — ~13 controls in one flat group; densest view (41 interactive elements). Evidence: measurements.json. Recommendation: chunk into Crop / Trace / Save.

**F-031 · sev 1 · IXD-VIS · top-bar chip** — Status chip uses the same bordered-pill treatment as real buttons; status reads as tappable. Evidence: `screens/setup_machine.png`. Recommendation: non-interactive badge styling.

**F-032 · sev 1 · IXD-TOL · top bar** — 'Require Firebase' is an unconfirmed one-click global mode toggle in persistent chrome. Evidence: `screens/print.png`. Recommendation: move to SETUP or confirm on disable.

**F-033 · sev 1 · H2 · PRINT queue card** — Dev shorthand: 'FAIL/SKIP 0 / 177' (unexplained denominator), 'Queue counts loaded', log-styled blockers (merged: ST-IDLE). Evidence: `screens/print.png`. Recommendation: split tiles, label denominators, sentence-case blockers.

**F-034 · sev 1 · H2 · left rail + SETUP/SHEET** — Units missing on Feed (mm/min) and Field W/H/Cell/Gap/Margin while siblings carry them. Evidence: `screens/setup_sheet.png`. Recommendation: unit-suffix every numeric field.

**F-035 · sev 1 · VD-COL-1 · SETUP/PEN** — Accent RUST used for ~half of all running text; the accent stops signaling. Evidence: `screens/setup_pen.png`. Recommendation: helper prose in INK_MID/INK_MUTED.

**F-036 · sev 1 · VD-TYPE-1 · PRINT queue tiles + legend** — 9px letterspaced uppercase captions (.mini-metric .label) and 10px legend chips; FAIL/SKIP is read under time pressure. Evidence: `screens/flow_legend.png`, service.py:142,145. Recommendation: 11–12px caption floor.

**F-037 · sev 1 · VD-TYPE-3 · token level** — RUST_LIGHT (3.23:1 on cream, AA-fail) exported on every page with zero consumers — a contrast footgun for the first hover state that reaches for it. Evidence: token_contrast. Recommendation: darken or mark decorative-only.

**F-038 · sev 1 · VD-GES-1 · SETUP/ADVANCED** — Filters/markers rows have ~350px label→checkbox gaps with no row rules across five identical rows. Evidence: `screens/setup_advanced.png`. Recommendation: tighten columns or add row separators/hover.

**F-039 · sev 1 · VD-HIER-2 · left rail (all views), CREATE/MOTIF, SETUP/PEN** — Three recurring 1–2px left-edge near-misses (79/80/82/83px) on every view plus 2–3px misses on MOTIF/PEN (merged from 3 dimensions: VD-HIER-2, H8, IXD-CONS). Evidence: measurements.json alignment_near_misses. Recommendation: one shared padding token removes all three offsets.

**F-040 · sev 1 · DS-SPACE-1 · PAGE_STYLE** — The stylesheet bypasses its own tokens: off-scale paddings/radii (12px, 14px, 5px 7px…) and four one-off rgba surfaces where one PAPER token exists (merged: DS-COL-1 surfaces). Evidence: service.py PAGE_STYLE vs tokens.py scale. Recommendation: sweep onto tokens; extend the ratchet to px/rgba literals.

**F-041 · sev 1 · DS-MOTION-1 · all screens** — Five duration and three easing tokens declared, zero transition rules consume them. Evidence: service.py:15-197 grep. Recommendation: a shared .oracle-btn transition rule or delete the tokens.

## Recommendations

A **component-consolidation + neutral-theme phase (B/C) is already planned** on this branch. Split the backlog accordingly:

**1. Do not wait for phase B/C — safety and correctness fixes (ship first):**
- **F-001** route the six stop/recovery buttons through the intent system *now* (the ui.colors() mapping is a 3-line change and closes the only sev-4) — phase B/C will also cover this, but it should not wait.
- **F-003, F-012** stop-family placement (separation, confirm/press-and-hold) — layout, not theming.
- **F-002** stop-family naming/scoping; **F-004/F-005** truthful state chip + blocker ranking; **F-006** toast → reserved banner; **F-007** disable prerequisite-gated primaries; **F-008** pen-lifts label binding (+ render test); **F-014** dot-decimal formatting.

**2. Resolved by the planned phase B/C (component consolidation + neutral theme) — verify, don't duplicate work:**
F-001 (button-system routing), F-009 (font tokens: wire-or-delete is a theme decision), F-010 (WARN token contrast), F-022 (helper vs state classes), F-025 (legacy rust sweep), F-026/F-027 (card/title/helper components), F-028 (tab-height rule collapse), F-031 (chip styling), F-035 (accent discipline), F-036 (caption floor), F-037 (RUST_LIGHT), F-039 (shared padding token), F-040 (PAGE_STYLE token sweep + ratchet), F-041 (motion tokens).

**3. Need separate fixes phase B/C will NOT cover — copy, labels, empty states, layout:**
- **Copy/labels:** F-011 (jargon pills), F-013 (errno leak), F-020 (temp path), F-021 (font IDs), F-033 (queue shorthand), F-034 (units).
- **Empty states:** F-016 (SVG dropzone), F-017 ('-' preview), F-018 (folder picker).
- **Layout/interaction:** F-015 ('?' target), F-019 (text preview placement), F-023/F-024 (procedure text size/measure), F-029 (auto-refresh preview — highest-leverage engagement fix), F-030 (MOTIF chunking), F-032 (Firebase toggle placement), F-038 (row grouping).

**Instrumentation:** already implemented (`src/neje_oracle/shared/telemetry.py` → `logs/operator_events.jsonl`; `scripts/operator_report.py`). Next audit should ingest real operator-session numbers for HEART H/E/T instead of proxies.

## Trend vs previous run — baseline reset

The 2026-08-05 audit (39 findings, 5.57/screen, verdict NOT READY) targeted a 7-tab IA (Connection/Calibration/Tests/Work/Exhibition/Generative) that no longer exists; the app collapsed to 3 screens (PRINT/CREATE/SETUP). Per-finding (criterion, screen) matching is therefore meaningless — treat this run as the **new baseline**. What the comparison does show:

**Structurally resolved by the IA collapse** (the screens or components hosting them are gone):
- Bare-text buttons masquerading as labels (old F-006/F-007/F-023/F-024) — all actions now render through a button system, except the stops (see recurring classes).
- The off-system generative sketch page (old F-005/F-008/F-028/F-037) — absorbed into CREATE.
- Inconsistent tab-to-tab layout gutters and card widths (old F-019/F-029).
- The 6-field duplicated status header (old F-032), thermal-printer button pile (old F-017/F-018), 'Checking FluidNC' blue toast (old F-020), exhibition progress-bar contrast (old F-021), truncated printer helper (old F-014).

**Recurring defect classes** (same root cause, new coordinates — these are the culture-level issues the redesign must actually kill):
- **Button-system chaos:** old F-003/F-026/F-027/F-033/F-035 (inconsistent fills, gold meaning both 'next' and 'stop', E-STOP on raw Quasar props) → now concentrated in **F-001/F-002** (raw stop buttons, two danger reds, identical START/STOP styling). The e-stop bypassing the styled button helper was flagged verbatim last run (old F-027) and recurs.
- **Jargon & raw developer output:** old F-001 (sev-4 raw telnet error)/F-002/F-011/F-012 → now **F-008/F-011/F-013/F-020/F-021/F-033**. The error copy improved (plain-language first line) but errno/port/temp-path leaks persist.
- **Occluding toasts:** old F-025/F-031 (toast truncates content, error state vanishes per tab) → now **F-006** (same floating-toast placement, new IA).
- **State-naming ambiguity:** old F-004 ('OPERATOR PAUSED · STOPPED' dot notation) → now **F-004/F-005** (OPERATOR PAUSED vs offline, three names for paused).
- **Off-scale spacing / caption-size sprawl:** old F-038/F-039 → now **F-040/F-036**, near-identical evidence in PAGE_STYLE.

**Metrics deltas:** defect density 5.57 → 3.42/view (−39%); sev-4 and sev-3 counts flat (1 and 8); task success 100% → 100% on a doubled flow suite; severity-weighted total 80 → 79. Verdict remains NOT READY, for a much narrower reason than last run: one sev-4 root cause (stop-button system bypass) plus a safety-path cluster, instead of app-wide chaos.

## Appendix

### Screen inventory
See `screens.md` for the full route table. 12 views: PRINT (`screens/print.png`), CREATE + 6 sources (`screens/create.png`, `create_sketch.png`, `create_texture.png`, `create_image.png`, `create_text.png`, `create_sheet.png`, `create_motif.png`), SETUP + 5 sections (`screens/setup.png`, `setup_machine.png`, `setup_pen.png`, `setup_sheet.png`, `setup_verify.png`, `setup_advanced.png`). Per-view hierarchy: `screens/dump.json`. Flow captures: `screens/flow_legend.png`, `flow_text_preview.png`, `flow_verify_gcode.png`.

### Flow results
| Flow | Passed | Duration | Steps | Notes |
|---|---|---|---|---|
| navigate-all | yes | 17.1 s | 14 | all 3 tabs + sub-views |
| legend-dialog | yes | 4.1 s | 3 | '?' opens legend |
| text-preview | yes | 7.6 s | 3 | includes 1 manual refresh step (F-029) |
| verify-gcode | yes | 9.6 s | 3 | artifact: `gui_sheet_20260815_230416.gcode` |

### measurements.json summary
- 14 view entries (12 views + 2 aliases); elements 40–78, interactive 23–43 per view (max CREATE/MOTIF 41 → F-030).
- Small targets: only one genuine violation — PRINT '?' 17x34px (F-015); all other sub-24px entries are 1x1 hidden native inputs under Quasar wrappers.
- Alignment: 3 recurring near-miss offsets (79/80, 80/82, 82/83) on every view; extras on CREATE/MOTIF and SETUP/PEN (F-039).
- Font census: 12/13/14px only, no ≥16px text anywhere (F-023); crowded_rows and text_below_10px empty in the dump (the 9/10px captions come from stylesheet inspection, F-036).
- token_contrast (15 pairs): failures — GOLD on CREAM 2.08, GOLD_DIM on CREAM 4.36 (AA-normal), RUST_LIGHT on CREAM 3.23 (AA-normal); all INK/RUST/OK/DANGER pairs pass, CREAM on DANGER 7.54 (the ready-made fix for F-001).
