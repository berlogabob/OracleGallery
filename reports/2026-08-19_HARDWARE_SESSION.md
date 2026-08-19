# Hardware session 2026-08-19 — findings and resume point

Physical-testing session: two software bugs found and fixed on hardware, the Z-servo
electrical/mechanical saga diagnosed to root cause, session paused mid-repair.

## ⚠ RESUME POINT (read first)

**The servo horn re-seat was interrupted.** State at pause:

- Servo is held at its electrical center: pulse window narrowed to 1495–1505 µs **in RAM
  only** — a reboot restores the yaml values (min 500 / max 1750).
- The pen currently parks **below the needed bottom** — the horn is bolted at the wrong
  angle for the servo's center. Next physical step: unscrew the horn, re-seat it on the
  spline so the pen sits at **mid-height** while the shaft holds center, avoiding
  over-center linkage crossings at either end. Then: restore a working pulse range,
  slow direction check (Z0 = up?), re-tune endpoints with `scripts/z_servo_tune.py`,
  send the numbers for persisting (WebDAV upload + repo config, procedure below).
- Board IP changes on every hotspot drop (phone overheats). Last known: `10.249.30.74`
  (`fluidnc.local` works; `.env` is pinned to the last IP; the tuner auto-discovers).

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

- Finish the horn re-seat + endpoint retune (resume point above).
- The spring on the pen mechanism steals lift torque — reconsider or weaken if lift
  stays marginal after retune.
- If crashes persist after the servo is mechanically sane and separately powered,
  suspect FluidNC v4.0.3's rc_servo/LEDC driver — try a firmware update, and grab
  `$SS` right after a crash (raw socket, not transport — `[MSG:ERR:` truncates it).

## Still open from the original physical-test plan

1. Six smoke plots, one per CREATE source (closes parked defect B9) + tab-switch
   mid-print check (finding #13 fix, never confirmed on hardware).
2. Re-capture `z_down_mm` / `z_up_mm` in the GUI after the servo work (old −7/−2 are
   stale twice over now).
3. One live STOP PRINT mid-draw confirmation of `75869e7`.
4. Firebase end-to-end + stale-job requeue live check (finding #18 fix).
5. Pen campaign: 15×3 matrix, sheets already in `runtime/physical_tests/`.

## Operational notes

- After restarting `neje-gui`, the old browser tab is a dead session — clicks silently
  do nothing. **Close the tab and open a fresh one**; a reload is not always enough.
- `.env` now pins `NEJE_PLOTTER_DRY_RUN=false` and the FluidNC host; the host must be
  re-pinned after every hotspot IP change (or rely on CONNECT/SCAN LAN).
