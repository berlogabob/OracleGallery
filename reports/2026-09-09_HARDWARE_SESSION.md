# Hardware session 2026-09-09 — Miuzei MZ996 fitted, range marked, feed at the cap

Continuation of `2026-08-31_HARDWARE_SESSION.md`. The dead SG90 is replaced by a Miuzei
180 MZ996 (MG996R clone: metal gear, ~10 kg·cm, ~11 µs/°, ~2.5 A stall), on its own
5 V USB-A supply with common ground. The operator remounted it with a different
placement and arm length; the horn stayed as fitted.

## ⚠ RESUME POINT (read first)

- Board flash and repo agree: `min_pulse_us: 2400 / max_pulse_us: 2100`. Verified
  across a `$Bye` reboot; `$H=Z` and a full F10000 cycle ran clean afterwards.
- `runtime/gui_settings.json` and `.env`: `z_feed_mm_min 10000`. Positions unchanged,
  `z_up 0 / z_down -25 / z_fix -25`. The GUI was not running during the session, so
  no stale tab to worry about; the next `neje-gui` start reads the new feed.
- Board rebooted: **re-home and re-zero X/Y before printing.**
- **Not done yet: the paper check.** F10000 is mechanically clean; whether the pen
  lands without a blob is unknown until the pen calibration sheet is plotted.

## What was measured

| Item | Value |
|---|---|
| Top, Z0, pen up | 2100 µs |
| Bottom, Z-25, pen down | 2400 µs |
| Real pen travel top→bottom | 6.8 mm (≈0.27 mm per Z unit) |
| Direction | pulse up = pen down, hence `min > max` in the yaml |
| Bottom at 2400, 3 s hold | silent |
| Speed ladder, 10 cycles per rung | F1000, 2000, 4000, 7000, 10000 all clean |

Cycle wall time per rung, measured with `G4 P0` so the ack waits for the motion:

| Feed | Mean cycle | Motion alone | Note |
|---|---|---|---|
| F1000 | 3.85 s | 3.0 s | the 08-31 setting |
| F2000 | 2.49 s | 1.5 s | |
| F4000 | 1.64 s | 0.75 s | |
| F7000 | 1.45 s | 0.43 s | telnet round trip dominates from here |
| F10000 | 1.39 s | 0.30 s | yaml `max_rate` cap, saved |

The servo itself needs ~0.05 s for the 300 µs arc, so even at the cap the pulse ramp
is what sets the pace and the arm tracks it; no slam was expected and none was heard.

## What was done

1. The "no movement" report at the start was diagnosed as `$MD` from an earlier session
   and/or 10 µs nudges (≈1° on this servo). `$ME` plus a 100 µs wiggle proved the
   servo, supply and signal. The tuner now sends `$ME` on start.
2. Board parked at 1500/1500 for a fresh start, then the operator drove the tuner at
   step 50 and marked `T` = 2100, `B` = 2400 without removing the horn.
3. Three cycles at F600 with a 3 s bottom hold: silent at both ends. Only then the
   ladder.
4. Yaml comment rewritten, uploaded (HTTP 201), rebooted, read back, homed, cycled.
5. `scripts/z_servo_tune.py`: `f` sets the feed for every move, `c` runs N timed
   cycles and holds at the bottom to listen, `$ME` on start, selftest covers the feed
   clamp. Note for the tuner: its `c` timing does not sync with `G4 P0`, so it reads
   the ack time, not the motion time; the table above came from a synced one-off.

## Open, in the order worth doing

1. **Paper check at F10000**: plot the pen calibration sheet (RUNBOOK section 9). A
   blob at every dash start means drop to F4000 or add `pen_down_dwell_ms`. The same
   print answers the 08-31 question whether the pen drags on travels at this lift.
2. Rescale Z to real millimetres: 25 units now equal a measured 6.8 mm, so the number
   exists. `max_travel_mm`, `Z_ABSOLUTE_FLOOR_MM`, `assets/tinybee.json`, the
   `z_down_mm` defaults and the pen profiles must move together.
3. Pen-fix still equals pen-down; with 6.8 mm of travel there is now room for it once
   the calibration plate height is known.
4. STOP PRINT status lag, sheet margin, smoke plots, Firebase, pen campaign: unchanged
   from 08-31.
