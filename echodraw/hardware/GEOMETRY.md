# Machine Geometry

This file is the single source of truth for EchoDraw machine dimensions.

## Dimension claims

| Value | Source | What it governs |
| --- | --- | --- |
| 255 × 420 mm | `echodraw/docs/explanatory-note.md` | Physical NEJE hardware working area |
| 255 × 420 mm | `echodraw/hardware/README.md` | Physical canvas/working area summary |
| 255 × 420 mm | `echodraw/hardware/configs/config.yaml` (`meta`) | FluidNC configured working area summary |
| X: 255 mm; Y: 420 mm | `echodraw/hardware/configs/config.yaml` (`max_travel_mm`) | FluidNC X/Y soft travel limits |
| Y: 420 mm | `echodraw/hardware/configs/config.yaml` (`homing.mpos_mm`) | FluidNC Y-axis machine position at positive-direction home |
| 250 × 440 mm | `src/neje_oracle/shared/config.py` (`PlotterSettings`) | Software default sheet layout |

## Authoritative values

Per the FluidNC configuration, hardware travel is:

- X: 255 mm
- Y: 420 mm

## OPEN DISCREPANCY

`PlotterSettings` defaults to a 250 × 440 mm sheet. Its 440 mm height exceeds
the configured 420 mm Y travel by 20 mm. This may reflect a modified machine or
a re-homed axis, but it must be verified on the physical machine before changing
either the software sheet default or the FluidNC travel configuration.
