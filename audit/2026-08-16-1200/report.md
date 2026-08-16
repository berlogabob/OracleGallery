# UX/UI Re-Audit — Oracle Operator GUI (web, headless Chromium 1280x800) — 2026-08-16

## Executive Summary

**Release verdict: READY WITH FIXES.**

The fix phases resolved the release blocker and roughly half the backlog. Of the baseline's 41 findings (verdict NOT READY): **19 fixed, 8 partial, 14 open**, plus **3 new findings** (2 of them regressions introduced by the fixes themselves) — 25 findings remain (0 sev-4, 3 sev-3, 11 sev-2, 11 sev-1). Token contrast failures went 3 → 0, all 4 CDP flows still pass 4/4, and the sev-4 intent-system breach on the safety controls (F-001) is verifiably gone: one danger red (#A0221A) everywhere, E-STOP filled, STOP PRINT outlined, white-on-gold eliminated. The three issues that gate the next run: (1) the relocated offline toast now occludes the machine-state chip and the workspace sub-tab row on every view — the occlusion moved from content to navigation (F-102); (2) the toast's DISMISS action renders accent-blue on danger-red at **1.09:1**, effectively invisible (F-103, new regression); (3) prerequisite-gated primaries still render enabled next to "No SVG/image/picture selected" (F-101).

## Background & Objectives

Re-audit of the NejeDraw Oracle operator GUI (branch `feat/raw-artifacts`) after the B3/B4/B5/B8/C2 design-system fix phases and the Phase E state/copy fixes, against baseline `audit/2026-08-15-1930` (41 findings, NOT READY). Same platform and device: headless Chromium 1280x800 driven via CDP against the sandbox on :8799. Hardware states (connected plotter, alarm, streaming) are not reproducible in the sandbox; findings only verifiable at runtime are marked code-verified where the rendered UI is consistent with the claim.

## Methodology

- Crawl: 12 screens audited (PRINT, CREATE x6 tabs, SETUP x5 tabs), 14 screenshots + 3 flow screenshots, filtered element dump for PRINT/CREATE/SETUP (`screens/dump.json`).
- Flow suite: navigate-all, legend-dialog, text-preview, verify-gcode (`flows-results.json`) — 4/4 PASS.
- Frameworks: Nielsen 10, UX laws (Fitts/Hick/Miller), WCAG 2.x contrast + target size, design-system consistency, 5 system states, ISO 9241-11 / HEART.
- Measurements: `measurements.json` (targets, alignment, font sizes, token contrast). The 26 recorded 1x1 "small targets" are hidden Quasar native inputs — known artifact, excluded.
- Not covered: hardware-dependent states (chip during RUN/ALARM, streaming lockouts), the claimed stop-family scope tooltips (hover not captured), motion timing.

## Metrics

| Metric | Value | Previous | Δ |
|---|---|---|---|
| Task success rate | 4/4 (100%) | 4/4 (100%) | = |
| Avg flow duration | 9.6 s | 9.6 s | = |
| Findings open (total) | 25 | 41 | −16 |
| — sev 4 | 0 | 1 | −1 |
| — sev 3 | 3 | 8 | −5 |
| — sev 2 | 11 | 19 | −8 |
| — sev 1 | 11 | 13 | −2 |
| Defect density (findings/screen) | 2.08 | 3.42 | −39% |
| Token AA contrast failures | 0 | 3 | −3 |
| Rendered contrast failures | 1 (F-103, 1.09:1) | ≥2 | new item |
| Severity-weighted findings (HEART Happiness proxy) | 42 | 79 | −47% |

## Key Findings (open/partial only — full details in findings.json)

### Severity 3
- **F-101 · H5 · SETUP/VERIFY, CREATE/IMAGE, CREATE/MOTIF** (baseline F-007, open) — START SVG PRINT / PRINT IMAGE / SAVE TO BANK render filled and enabled beside "No SVG/image/picture selected". Evidence: `screens/setup_verify.png`.
- **F-102 · H1 · all views** (baseline F-006, partial-**regressed**) — the offline toast moved to the top and now hides the machine-state chip and the SETUP/CREATE sub-tab rows, and half-covers SEND on PRINT; PRINT's bottom status line is still clipped at y=794/800. Evidence: `screens/setup_machine.png`, dump.json (DISMISS 89x32 @857,22 on all views).
- **F-103 · DS-A11Y-1 · all views** (**new regression**) — toast DISMISS is ACCENT #2F5A8F on DANGER #A0221A = **1.09:1**; the only control that clears the persistent overlay is nearly invisible. Evidence: `screens/print.png`, sampled pixels.

### Severity 2
- **F-104** (F-004 partial) — Manual motion still statically captions "Blocked while G-code streams." while offline, jog buttons enabled; chip state unverifiable (occluded by F-102). `screens/print.png`.
- **F-105** (F-002 partial) — STOP SYSTEM now visually distinct (danger fill vs accent START), but four stop-family labels still lack on-screen scope. `screens/print.png`.
- **F-106** (F-012 partial) — STOP PRINT/E-STOP weights differ now, gap still 32px. dump.json.
- **F-107** (F-013 open) — ":23; HTTP offline ([Errno 61]…)" still leaks; still truncated on SETUP/MACHINE. `screens/setup_machine.png`.
- **F-108** (F-014 open) — comma decimals persist against dot readouts ("0,3" vs "0.25 to 3 mm") on 5 screens. `screens/setup_advanced.png`.
- **F-109** (F-018 open) — Image folder free-text path, no picker/validation; stray "-" dangles. `screens/create_sheet.png`.
- **F-110** (F-019 open) — text preview still tiny, top-left pinned, glyphs clipped. `screens/flow_text_preview.png`.
- **F-111** (F-021 open) — font selector still shows "zzBVFNTL". `screens/create_text.png`.
- **F-112** (F-022 open) — blockers/"Not ready" still styled identically to helper captions (.oracle-helper 12px). dump.json.
- **F-113** (F-023 open) — procedure paragraphs still 12px; max font in app 14px. measurements.json.
- **F-114** (**new**) — SET WORK ZERO is filled DANGER red identical to STOP SYSTEM/RESET/ABORT: 4 danger-red surfaces at once on PRINT dilutes the danger signal the F-001 fix established. `screens/print.png`.

### Severity 1
F-115 (F-017 partial: guidance added, "-" remains) · F-116 (F-008 residual: "fine" badge overlaps helper) · F-117 (F-034 residual: "Cell", "SVG X0/Y0" unitless) · F-118 (F-029 manual REFRESH PREVIEW) · F-119 (F-030 MOTIF flat 41-control stack) · F-120 (F-031 chip pill-as-button; currently occluded) · F-121 (F-032 Require Firebase toggle in chrome) · F-122 (F-033 FAIL/SKIP 0/177 tile) · F-123 (F-038 350px label→checkbox gaps) · F-124 (F-039 1–2px alignment near-misses persist) · F-125 (**new**: texture editor toolbar kept legacy cream/rust pills + native selects, `screens/create_texture.png`).

### Verified fixed (19)
F-001 (sev-4 intent system: one danger red, E-STOP filled / STOP PRINT outline), F-003 (RESET/ABORT now 562px from RESUME), F-005 (blockers lead with "plotter offline"; Next action says connect first), F-009 (neutral theme + system font stack — the Garamond/Cinzel question resolved by decision), F-010 (WARN AA; 0 token failures), F-011 (Browser UI / Control channel / Limit switches / Machine mode pills), F-015 (LEGEND 69x34 replaces 17px "?"), F-016 (SVG dropzone labelled), F-020 (spool-relative success toast + "Press START TEST PRINT"), F-024 (65ch helper prose), F-025 (legacy #8f4f2b gone), F-026 (one card/title idiom), F-027 (one helper + micro_label), F-028 (tabs 36px inside 40px bar), F-035 (accent no longer prose), F-036 (no text <10px; legend chips legible), F-037 (RUST_LIGHT deleted), F-040 + F-041 (spacing/motion sweeps — code-verified, consistent with rendering; not directly measurable in static capture).

## Recommendations (prioritized)

1. **F-103** — set notify action color to the on-color of the notification surface (SURFACE on DANGER = 7.22:1, already AA per token_contrast); add a toast-contrast render test. One-line fix, sev-3.
2. **F-102** — reserve a non-overlaying banner strip for the persistent connection warning; never cover the chip or sub-tabs; unclip the PRINT bottom status strip.
3. **F-101** — disable prerequisite-gated primaries with the reason adjacent.
4. **F-114** — demote SET WORK ZERO out of filled danger; reserve that treatment for motion-stopping actions.
5. **F-104 + F-112** — state-driven Manual motion caption + WARN/DANGER styling for live blockers (pairs naturally).
6. **F-108** — dot-decimal display sweep (safety-adjacent on a G-code panel).
7. Batchable design-system debt: F-105/F-106 (stop-family naming/placement), F-113 (procedure text size), F-117 (unit stragglers), F-123/F-124 (alignment), F-125 (texture toolbar).

## Trend vs previous run (2026-08-15-1930)

| Severity | Baseline | Fixed | Partial | Open | New | Remaining |
|---|---|---|---|---|---|---|
| 4 | 1 | 1 | 0 | 0 | 0 | 0 |
| 3 | 8 | 4 | 3¹ | 1 | 1 | 3² |
| 2 | 19 | 11 | 3 | 5 | 1 | 11² |
| 1 | 13 | 3 | 2 | 8 | 1 | 11 |
| **Total** | **41** | **19** | **8** | **14** | **3** | **25** |

¹ F-002, F-004, F-006 (F-008's residual downgraded to sev-1). ² Remaining counts use residual severities: F-002/F-004 residuals re-rated sev-2; F-006's regression and the new F-103 hold sev-3.

- Fixed: 19 of 41 (46%), including the only sev-4.
- Regressed/new: F-102 (toast now occludes nav + chip), F-103 (DISMISS 1.09:1), F-114 (danger-fill dilution), F-125 (texture toolbar legacy island).
- Metrics: findings 41 → 25 open; defect density 3.42 → 2.08/screen; token AA failures 3 → 0; task success 4/4 → 4/4.

## HEART Scorecard

| Dimension | This run | Delta / note |
|---|---|---|
| **H**appiness (severity-weighted findings proxy) | 42 | 79 → 42 (−47%) |
| **E**ngagement (friction in core loops) | unchanged | REFRESH PREVIEW detour remains (F-118); telemetry will now measure real iteration counts |
| **A**doption (first-run guidance) | improved | Next action now leads new operators to CONNECT first; empty states labelled (F-005, F-016 fixed) |
| **R**etention (recovery & state) | improved with caveat | Recovery row de-fanged (F-003 fixed), offline recovery guidance correct — but the state chip is occluded by the toast (F-102) |
| **T**ask success (measured) | 4/4 flows, 9.6 s avg | unchanged, 0 errors |

**Telemetry is now live**: `src/neje_oracle/shared/telemetry.py` records operator sessions and `scripts/operator_report.py` aggregates them — real Task-success and Engagement numbers (session counts, flow durations, error rates from actual operators, including the remote unattended Oracle operator) will accrue and should replace the automation proxies in the next audit's HEART table.

## Appendix

### Screen inventory
PRINT → `screens/print.png` · CREATE/SKETCH → `create_sketch.png` (= `create.png`) · CREATE/TEXTURE → `create_texture.png` · CREATE/IMAGE → `create_image.png` · CREATE/TEXT → `create_text.png` · CREATE/SHEET → `create_sheet.png` · CREATE/MOTIF → `create_motif.png` · SETUP/MACHINE → `setup_machine.png` (= `setup.png`) · SETUP/PEN → `setup_pen.png` · SETUP/SHEET → `setup_sheet.png` · SETUP/VERIFY → `setup_verify.png` · SETUP/ADVANCED → `setup_advanced.png`. Element hierarchy: `screens/dump.json` (PRINT/CREATE/SETUP).

### Flow results
| Flow | Result | Duration | Steps | Artifact |
|---|---|---|---|---|
| navigate-all | PASS | 17.1 s | 14 | — |
| legend-dialog | PASS | 4.1 s | 3 | `flow_legend.png` |
| text-preview | PASS | 7.6 s | 3 | `flow_text_preview.png` |
| verify-gcode | PASS | 9.6 s | 3 | `gui_sheet_20260815_235716.gcode`, `flow_verify_gcode.png` |

### measurements.json summary
Token contrast: 13/13 pairs pass AA (baseline: 3 failures). No text below 10px on any view (baseline: 9px/10px captions). Small-target list contains only 1x1 hidden Quasar native inputs (known artifact); the baseline's one genuine violation (17px "?") is fixed (LEGEND 69x34). Alignment near-misses persist: offsets 1–2px at edges 80/81, 85/86, 238/240 on all views (F-124).

---

## Post-audit fixes (same day, commit follows this report)

The two sev-3 regressions and two residuals this re-audit raised were fixed immediately after it ran, verified by a fresh gate render (`/tmp/gate-f/print.png` reproduced via `measure_gui --gate`):

- **F-103 fixed** — `.q-notification__actions .q-btn` now renders SURFACE on the notification's own fill (7.22:1 on DANGER); the accent never rides a colored toast again.
- **F-102 fixed** — the persistent offline fact moved into a reflow `warning_banner` under the top bar (occludes nothing; layout shrinks to fit); the toast is transient (8s) and only marks the transition. The OFFLINE chip is now verifiable on screen: the sandbox renders `✕ OFFLINE`.
- **F-114 fixed** — SET WORK ZERO is danger-outline; one danger fill per screen plus the e-stop.
- **F-004 residual fixed** — the Manual motion caption is state-driven: "Offline — connect on SETUP first." / "Blocked while G-code streams." / "Jog is live…".

Remaining open after these: 3 sev-2 leads (F-101 prerequisite-disabled buttons, F-104 PRINT bottom strip clipping, F-105 decimal locale) and the filed sev-1/2 backlog in `planning/DISPOSITION_REGISTER.md`.
