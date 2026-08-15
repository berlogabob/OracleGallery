# Campaign: pens × modes (sheets 10–12)

The RAW-artifacts branch added modes, mode knobs and generators that have never touched
paper, and three new pens that have never been calibrated. This document is the session
protocol and the results ledger: it is tracked, and the matrix below is filled in during
the physical sessions. Regenerate the sheets any time with:

```bash
uv run python scripts/build_campaign_sheets.py --pen <profile>   # or --pen all
```

Sheets land in `runtime/physical_tests/` as `10_modes_<pen>.svg`,
`11_generators_<pen>.svg`, `12_liftbudget_<pen>.svg`. The generator sheet uses a fixed
seed, so its geometry is identical for every pen — differences on paper are the pen.

## Pre-start safety check (every session)

- [ ] Paper on the bed, taped flat
- [ ] Pen fitted and capped-off ink flowing (scribble by hand first)
- [ ] Work zero set (`SET WORK ZERO` on the machine rail)
- [ ] FluidNC connected and **Idle**
- [ ] Z calibrated since the last mechanics change (RUNBOOK §9; `spool/z_range_cal.gcode`
      if the Z range itself is in doubt)

## Per-pen loop

For each pen (fineliner → gel → textile):

1. **Calibrate** — fit the pen; `SETUP` → `PEN` → nearest starter profile →
   `GENERATE PEN CAL G-CODE` → plot it. Read off paper: fastest clean feed, shallowest
   fully-inking Z, shortest blob-free dwell, real `pen_width_mm` from the line pairs.
   Type them in → `SAVE AS PROFILE` under the pen's name → regenerate and plot once more
   to confirm → photo as `runtime/physical_tests/10_pen_cal_<pen>.jpg`.
   *Textile note: the line is pressure-sensitive, so the Z ladder is the decisive block —
   pick the depth by the line width you want, not just "inks fully".*
2. **Regenerate the campaign sheets** with the calibrated profile
   (`--pen <saved name>`), so cell sampling picks up the measured nib width.
3. **Plot sheets 10, 11, 12** via `SETUP` → `VERIFY` → `START SVG PRINT`. Photo each
   next to its SVG preview, into `runtime/physical_tests/`.
4. **Fill the matrix** below.

## Defect vocabulary

One keyword per cell, worst defect wins (§9a inspection-checklist style):

| Keyword | Means |
|---|---|
| `OK` | plots clean at this pen's calibrated settings |
| `skip` | stroke starts dry / segments missing |
| `blob` | ink pooling at stroke starts or direction changes |
| `flood` | lines merge into solid where they should stay separate |
| `tear` | paper damaged (pressure/depth too high) |
| `ghosting` | doubled or offset strokes |

## Result matrix

Rows are sheet cells; columns are pens. Fill during sessions.

| Sheet · cell | fineliner | gel | textile |
|---|---|---|---|
| 10 · wave-H | | | |
| 10 · wave-V | | | |
| 10 · wave-1line | | | |
| 10 · flow | | | |
| 10 · flow-dash | | | |
| 10 · trace | | | |
| 10 · hatch | | | |
| 11 · ribbon | | | |
| 11 · bloom (high density — watch for ring-crossing `flood`) | | | |
| 11 · vine | | | |
| 12 · lifts-off | | | |
| 12 · lifts-256 | | | |
| 12 · lifts-64 | | | |
| 12 · lifts-8 | | | |
| 12 · lifts-0 | | | |

Also note per pen, from sheet 12: the lowest budget whose connector lines are acceptable,
and the measured plot-time saving against `lifts-off`.

## Future pens (planned, nothing built)

The sheets are parameterized per pen profile precisely so these are additive:

- **Brush pens** — need a refill return-point (pause, travel to a dip/refill station,
  resume); a profile field plus G-code support, not a new sheet.
- **Wide markers** — just a profile with a large `pen_width_mm`; the sheets already scale
  sampling to the nib.
- **Auto tool-changer** — per-profile parameterization is the substrate; the campaign
  would then run all pens in one session.
