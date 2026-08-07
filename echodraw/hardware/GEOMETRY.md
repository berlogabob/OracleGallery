# Machine Geometry

This file is the single source of truth for EchoDraw machine dimensions.

All values below were **measured on the physical machine on 2026-08-07** and
cross-checked against the running FluidNC controller (`$CD` dump and `$SS` boot
log). They supersede every earlier claim in the repo.

## Authoritative values

| Axis | Travel | Homing | Limit switch |
| --- | --- | --- | --- |
| X | **255 mm** | negative direction, `mpos_mm: 0` | `gpio.33:pu:low` |
| Y | **440 mm** | negative direction, `mpos_mm: 0` | `gpio.32:pu:low` |
| Z | 25 mm (RC servo pen lift; Z0 = up, Z-25 = down) | positive direction, `mpos_mm: 0` | `gpio.22:pu:low` |

- `steps_per_mm`: X 40, Y 40, Z 100. Verified by commanding 100 mm and measuring.
- `hard_limits: true` on X and Y — the machine **does** have real limit switches.
  They were observed triggering during homing (`Pn:X`, `Pn:Y`, `Pn:XY`).
- `start.must_home: true`. Before homing, motion commands return `ok` while
  nothing moves. This is the single most misleading behaviour when debugging a
  cold machine.
- Pen servo is on `gpio.2`; the laser spindle PWM is on `gpio.15`. These are not
  interchangeable.

## Sources

| Value | Source | Status |
| --- | --- | --- |
| X 255, Y 440, Z 25 | `echodraw/hardware/configs/config.yaml` (`max_travel_mm`) | pulled from the board 2026-08-07 |
| X 255, Y 440 | live controller `$CD` | measured 2026-08-07 |
| 250 × 440 mm | `src/neje_oracle/shared/config.py` (`PlotterSettings`) | software default sheet layout |

## Resolved: the former 420 vs 440 discrepancy

Earlier revisions of this file recorded Y travel as 420 mm and claimed Y homed
in the **positive** direction to `mpos_mm: 420`. Both were wrong.

The machine homes Y **negative to 0** with **440 mm** of travel. The 420 figure
came from a pre-servo draft config that was never flashed. `assets/tinybee.json`
was correct all along.

The software default sheet (250 × 440) therefore fits Y exactly, with **zero
margin**. Note that the usable area is further reduced by wherever work zero is
set: with G54 at machine (5, 5), only 435 mm of Y remains. Sheet height plus the
work-zero offset must stay within travel.
