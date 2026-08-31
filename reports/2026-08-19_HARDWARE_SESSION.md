# Hardware session 2026-08-19 — findings and resume point

Physical-testing session: two software bugs found and fixed on hardware, the Z-servo
electrical/mechanical saga diagnosed to root cause, session paused mid-repair.

## ✅ RESUME POINT — closed 2026-08-31

The horn was re-seated and the range saved. **The range is deliberately narrow.**

- Working pulses: **min 1820 / max 2060 µs** (Z-25 = pen down, Z0 = pen up), measured with
  `scripts/z_servo_tune.py`, written into `echodraw/hardware/configs/config.yaml`, uploaded
  by WebDAV (HTTP 201) and verified across a reboot. Direction is correct as marked — no
  min/max swap needed. `$H=Z` homes clean, no fallback config, no panic in `$SS`.
- These are the **working pen-up/pen-down positions, not the mechanical ends**. The gearbox
  cracks audibly near its stops, so the operator stopped short of them on purpose. ~240 µs of
  the servo's arc, so the full Z-25..Z0 command span is only a couple of mm of real pen
  travel: the GUI's Z numbers are lift positions now, not millimetres.
- **Consequence for pen-fix**: there is no travel left below pen-down, so the `GO TO FIX`
  position cannot sit under it. `z_fix_mm` is parked at the bottom (= pen-down) until the
  holder is rebuilt.
- **Deferred, owner: operator** — redesign the pen-holder assembly and gearbox. That is what
  buys back the full 15°..90° arm sweep, real millimetre travel, and a usable pen-fix clamp.
- Board IP still changes on every hotspot drop; `.env` is repinned to `10.131.66.74` and the
  tuner auto-discovers.

## Fixes shipped and field-verified (commits)

- `dc9c212` — **error:152 / "Default (Test Drive)" fallback**: FluidNC intentionally
  skips config.yaml for exactly one boot after a panic (upstream #936). Recovery is a
  software `$Bye` restart — no power cycle. Auto-recovery wired into the system check,
  `RESTART BOARD` button added. **Field-proven twice**: operator recovered a live crash
  in ~20 s at 14:20; agent-side recovery worked at 16:0x. Also: Z floor −30→−25, pen
  moves clamped to travel, pen profiles fixed (gel/ballpoint/textile commanded past
  travel), homing no longer records a brownout-interrupted `$H` as success.
- `75869e7` — **STOP PRINT was uselessly graceful**: it only took effect at row/cell
  boundaries; a dense row runs minutes (operator pressed it twice live, machine kept
  drawing, E-STOP needed). The stream now checks a stop flag between G-code lines,
  drains the RX buffer, waits Idle, pen-up, pauses — seconds. Verified by test suite;
  the live retry at 16:22 ended in a clean operator-paused state.
- `c45c5ec` — **Z-servo live range tuner** (`scripts/z_servo_tune.py`) + recalibrated
  pulse range in `echodraw/hardware/configs/config.yaml`.
- `c32001f` — **pen-fix, the third saved Z position**: `z_fix_mm` through GuiSettings, the
  runtime config, a CALIBRATE input, `SET AS PEN-FIX` and `GO TO FIX`. Built for a clamp
  position below pen-down; the narrow safe range means it has nowhere to go yet.
- `954db9b` — **tuner drives the pulse on single keypresses**: the old Z-based nudge was
  silently refused at Z0 (already at the soft limit) — exactly where the horn needs seating.
  `T`/`B` mark the ends, and a top mark below a bottom mark is the reversed-servo swap, so
  direction no longer costs a second re-seat.

## STOP PRINT confirmed on hardware (2026-08-31)

Four live stops on a real draw. The machine stops in **well under a second** every time:
run 2 acked two more G-code lines after the click (113 -> 115 of 874) and went quiet
0.53 s later. Stops land mid-cell, not at a row boundary, and the board ends Idle with
the pen up and its position reference intact -- no soft reset, no re-home. `75869e7` does
what it claims.

**But the GUI status flip lags, and the lag scales with rows completed:**

| rows done at stop | click -> OPERATOR_PAUSED |
|---|---|
| 0 | ~3 s |
| 1 | 38 s |
| 4 | still `printing` 4 s after the counter froze |

The G-code counter freezes immediately in all cases, so this is reporting lag, not motion.
The `PrintStopRequested` handler logs nothing between the pen lift and `_set_state`, and it
calls `_replace_manifest_row`, which rewrites the whole manifest -- longer with every row.

This matters more than it looks: it is exactly the trap from 2026-08-19, where the operator
pressed STOP twice and reached for E-STOP because the machine looked like it was ignoring
them. The pen was off the paper the whole time. Fix is to flip the state before the
bookkeeping, and to log the pen lift so the next stop is measurable.

## The "HTTP flicker" was probably the probe rate (2026-08-31)

Ten pen-up/pen-down cycles on the new range read `http_online=False` every single time —
then stayed False at Idle, then recovered on their own once the polling stopped. The cause
was the test loop, not the board: `FluidNCTransport.probe()` opens a fresh telnet socket
*and* does an HTTP GET, and calling it ~3x/second exhausts the ESP32's socket pool. At a
1.5 s cadence the same ten cycles are 10/10 clean, HTTP up throughout, no panic in `$SS`.

This is a candidate explanation for finding #1's "HTTP flickers right after Z moves", which
shaped the whole Z-servo diagnosis. It does not explain the *panics* — those showed real
`[MSG:ERR: Showing startup log from previous panic]` in `$SS` and remain unexplained. But
flicker and panic were being read as one symptom, and at least the flicker half looks
self-inflicted. The print hot path never had this problem: `_wait_for_idle` reuses one
telnet connection and sends `?`, never touching HTTP.

## The Z-servo diagnosis trail (what we now know)

1. **Crashes correlate with Z-servo commands, not load**: board crashed during gentle
   Z jogs at 13:15 and 14:19, HTTP flickers right after Z moves, panic ~1.5 s after a
   Z move on 08-10. `$SS` after a crash shows `[MSG:ERR: Showing startup log from
   previous panic]` — confirmed panics, on FluidNC **v4.0.3**.
2. **Board crashed even with the servo electrically dead** (12-cycle test with
   miswired separate supply → zero servo current, same flicker + crash at cycle 11).
   So the servo's *power draw* is not the whole story — but the wiring at the time was
   unverified, so the electrical exoneration is provisional, not final.
3. **Servo moved to separate 5V**: cut USB-C cable (2×red = 5V, silver strands = GND,
   green/white = data, unused) + common ground with the board. Note: cut C-to-C into a
   C charger can give 0V (CC pin); a USB-A charger is the reliable source.
4. **Servo pulse range was far off after remount**: tuned live from 900–2100 to
   **500–1750 µs** (top was grinding at 2100 — chronic stall on every boot and every
   `$H=Z`). Persisted to the board via WebDAV: `curl -T file http://<ip>/flash/TinyBee-06.yaml`
   (HTTP 201, verified across reboot).
5. **Direction flipped mid-session → over-center linkage**: after the reboot-grind the
   arm crossed its top dead center; same pulses now move the pen the opposite way with
   shifted endpoints. Confirmed the software mapping is sane via the tiny-pulse-window
   test (1100–1150 µs → almost no movement, so runtime `$` changes DO apply live).
   Hence the horn re-seat (see resume point). FluidNC direction inversion, if needed
   after re-seat: swap min/max_pulse_us (documented upstream).

## Hardware to-do (owner: operator)

- Redesign the pen-holder assembly / gearbox — it cracks near the mechanical stops, which is
  what forced the narrow pulse range above.
- The spring on the pen mechanism steals lift torque — reconsider or weaken if lift
  stays marginal after retune.
- If crashes persist after the servo is mechanically sane and separately powered,
  suspect FluidNC v4.0.3's rc_servo/LEDC driver — try a firmware update, and grab
  `$SS` right after a crash (raw socket, not transport — `[MSG:ERR:` truncates it).

## Still open from the original physical-test plan

1. Six smoke plots, one per CREATE source (closes parked defect B9) + tab-switch
   mid-print check (finding #13 fix, never confirmed on hardware).
2. Re-capture `z_down_mm` / `z_up_mm` / `z_fix_mm` in the GUI after the servo work (old
   −7/−2 are stale twice over now; with the narrow range they want −25/0).
4. Firebase end-to-end + stale-job requeue live check (finding #18 fix).
5. Pen campaign: 15×3 matrix, sheets already in `runtime/physical_tests/`.

## Operational notes

- After restarting `neje-gui`, the old browser tab is a dead session — clicks silently
  do nothing. **Close the tab and open a fresh one**; a reload is not always enough.
- `.env` now pins `NEJE_PLOTTER_DRY_RUN=false` and the FluidNC host; the host must be
  re-pinned after every hotspot IP change (or rely on CONNECT/SCAN LAN).
