# Hardware session 2026-08-31 — Z servo finished, STOP PRINT confirmed, one servo lost

Continuation of `2026-08-19_HARDWARE_SESSION.md`, whose resume point is now closed.

## ⚠ RESUME POINT (read first)

**State of the machine at end of day:**

- The **original servo is installed** and working. Board flash and repo agree:
  `min_pulse_us: 1930 / max_pulse_us: 2060`, `acceleration_mm_per_sec2: 1000`,
  `z_feed_mm_min: 1000`. Verified across a reboot, no panic, real config loaded.
- Board rebooted twice at the end, so **position reference is gone: re-home and
  re-zero before printing.**
- GUI settings: `z_up_mm 0`, `z_down_mm -25`, `z_fix_mm -25`, sheet **A4 210x297**,
  margin **0** (unset — decide this), board IP pinned to `10.131.66.74`.
- **The replacement SG90 is dead.** See "What killed the servo" below.

**First thing tomorrow:** confirm by ear that the bottom is silent at 1930 with the old
servo, then re-home, re-zero, and reload the GUI tab (it holds stale widget values after
any settings change made outside it).

## Shipped and verified on hardware

- `c32001f` **pen-fix**, the third saved Z position, plumbed GuiSettings ->
  PlotterRuntimeConfig -> supervisor -> board. Ran on hardware; emits
  `G1 Z-25.000 F1000.00`. With the current narrow range it lands on pen-down, so it has
  nowhere of its own to sit until the holder is rebuilt.
- `954db9b` **tuner drives the pulse on single keypresses**. The old Z-based nudge was
  silently refused at Z0 — exactly where the horn needs seating. `T`/`B` mark the ends.
- `2bb2beb` / `fa31fcc` **pulse range saved**: 1820, then 1930 after a test print showed
  the nib splaying (pen-down was 110us too deep).
- `c60f3dc` **the "HTTP flicker" was our own poll rate.** `probe()` opens a fresh socket
  plus an HTTP GET per call; 3/second exhausts the ESP32's pool. Likely the other half of
  the observation that steered the 2026-08-19 diagnosis. Does not explain the panics.
- `7a987ab` **STOP PRINT confirmed**, four live stops. Machine stops in **0.53 s**,
  mid-cell, pen up, position reference intact. The GUI status flip lags in proportion to
  rows completed (0 rows ~3 s, 1 row 38 s, 4 rows still "printing" after the counter
  froze) — `_replace_manifest_row` rewrites the whole manifest before `_set_state`.
  Reporting bug, not a safety one, but it is what made the operator press STOP twice and
  reach for E-STOP on 2026-08-19.
- `3f3532f` **tuner step ladder**. `+`/`-` doubled and halved, so leaving 10us meant never
  returning to it — and 10us is the SG90 dead band, the only size that reliably moves.

## What killed the servo

The operator reported the bottom buzzing during a speed test. Buzzing is the servo
stalling against the mechanical floor. In the same session, `z_feed_mm_min` had been
raised 1000 -> 10000 (a 10x faster commanded pen-down) **before the bottom was confirmed
buzz-free**. A stalled SG90 holds near stall current with no protection. The servo was
dead shortly after; the old one had to be reinstalled.

The 2026-08-19 plan already said "listen at the bottom endpoint — done when the servo is
buzz-free and does not push against the hard floor". The instruction existed and was
skipped. Rule going forward: **a buzz stops everything; the endpoint is fixed before any
speed setting is touched.** Also: a servo swap invalidates the pulse range, and running
one servo's endpoints with another servo fitted is its own way to kill the next one.

Note: `acceleration_mm_per_sec2: 5000` was staged locally but **never uploaded**, so the
board's acceleration was 1000 all day. Only the feed change reached the machine.

Also learned: FluidNC `$MD` does **not** re-arm on the next motion command. The board
accepts `G1 Z`, updates position and reports Idle while the servo sits dead. `$ME` is the
required pair — a tuning session after `$MD` drives nothing and reads as broken hardware.

## Open, in the order worth doing

1. Rescale Z to real millimetres. `max_travel_mm: 25` is a lie on an axis with a couple of
   mm of travel. Needs the measured pen-tip travel, then `Z_ABSOLUTE_FLOOR_MM`,
   `assets/tinybee.json`, the `z_down_mm` defaults and the pen profiles must track it.
2. Whether the pen drags on travels — asked three times, never answered, still unknown.
   130us of lift was the worry; the old servo's window is 130us (1930-2060).
3. The STOP PRINT status lag: flip the state before the bookkeeping, and log the pen lift
   so the next stop is measurable.
4. Sheet margin is 0 on A4 — strokes can run to the paper edge or onto the clamp.
5. Six smoke plots, one per CREATE source, plus the tab-switch mid-print check.
6. Firebase end-to-end and the stale-job requeue.
7. The 15x3 pen campaign, sheets already in `runtime/physical_tests/`.
8. Pen-holder / gearbox rebuild (operator). Buys back the full 15..90 deg arm sweep, real
   millimetre travel, and a pen-fix position that isn't pen-down.
