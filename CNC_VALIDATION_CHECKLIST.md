# CNC hardware validation checklist — 2026-07-17 bug-fix pass

Context: a repo-wide audit found 15 correctness/safety bugs, all fixed and
covered by unit tests (192/192 passing), but four of the fixes change real
plotter behavior in ways unit tests can't fully confirm. Nothing is
committed yet — do that first. This file lists what to physically verify
next time you're at the machine.

## 0. Before touching the machine

- [ ] Review the diff (`git status` / `git diff`), then commit. Nothing has
      been committed — nice-to-verify-before-committing items below are
      optional, but the diff should land in a commit regardless so it isn't
      sitting as uncommitted working-tree state indefinitely.
- [ ] `uv run pytest -q` one more time on the machine you'll actually run
      the plotter from, in case the dev machine's environment differs.

## 1. Pause / emergency-stop now takes effect mid-sheet (was: waited for the whole sheet to finish)

**What changed:** `blocks/plotter/daemon.py` — the row/cell send loop now
re-checks operator control before every row/cell, not just once at the start
of the sheet.

**Test at the machine:**
- [ ] Start a multi-row/multi-cell TEST print.
- [ ] Press **PAUSE** partway through (after row/cell 1 has started sending,
      before the sheet finishes).
- [ ] Confirm motion stops after the current row/cell finishes — it should
      **not** continue sending further rows/cells. GUI status should show
      "Print paused by operator mid-sheet" / `OPERATOR_PAUSED`.
- [ ] Repeat with **emergency stop** instead of pause. Confirm the same:
      no further motion is sent after the in-flight segment completes.
- [ ] Resume and confirm a fresh print still starts and runs a full sheet
      normally when nothing is paused.

## 2. Stop → restart no longer risks two daemons driving the plotter at once

**What changed:** `app/supervisor.py`'s `stop_plotter()` — if the daemon
thread doesn't exit within 5 seconds of a stop request (e.g. it's mid-move),
it now reports **WARNING** ("still finishing current motion") instead of
falsely claiming STOPPED, and keeps the thread reference so a follow-up
start can't spawn a second daemon on the same hardware.

**Test at the machine:**
- [ ] Start a print with a long single row/cell move (so a stop request
      lands mid-motion rather than between segments).
- [ ] Hit **STOP** immediately.
- [ ] Watch the GUI status — if the daemon doesn't exit within 5s you should
      see a "still finishing" WARNING state rather than an immediate false
      STOPPED.
- [ ] Try **starting a new print immediately** while that WARNING is
      showing — confirm it's blocked ("already running" / doesn't spin up
      a second daemon) rather than silently starting a second motion stream.
- [ ] Once the machine genuinely goes idle, confirm status settles to
      STOPPED and a new print now starts normally.

## 3. Direct-SVG upload now rejects artwork bigger than the sheet, instead of sending it anyway

**What changed:** `blocks/gcode/svg_gcode.py` / `blocks/gui/support.py` —
direct SVG print jobs are now bounds-checked against
`PlotterSettings.sheet_width_mm` / `sheet_height_mm` (default 250×440mm)
before gcode is generated.

**Test at the machine (or at the GUI, no motion needed for the reject case):**
- [ ] Upload/select a deliberately oversized SVG (bigger than your
      configured sheet) via the direct-print path. Confirm you get a clear
      error instead of the plotter attempting out-of-bounds motion.
- [ ] Upload a normal in-bounds SVG the same way and confirm it still
      prints correctly — this fix must not have broken the normal path.
- [ ] If your real `sheet_width_mm`/`sheet_height_mm` config differs from
      the 250×440mm default, double check the bound being enforced matches
      your actual physical sheet/travel area, not just the code default.

## 4. Z-feed rate is now actually applied to pen-down moves (was silently ignored)

**What changed:** `blocks/gcode/svg_gcode.py`'s `_pen_down_command()` — the
Z-servo pen-down move now emits `G1 Z... F<z_feed_mm_min>` instead of a
hardcoded rapid `G0 Z...`. This is the one change that most needs your eyes
on real hardware — a unit test confirms the G-code *text* is correct, but
not that the physical motion is safe/smooth.

**Test at the machine:**
- [ ] Set `z_feed_mm_min` to its current/normal configured value and run a
      TEST print. Watch the pen-down move specifically.
- [ ] Confirm the pen lowers smoothly at a controlled (fed) speed rather
      than the old instantaneous rapid-move snap — should look and sound
      noticeably different (a `G1` feed move vs. the old `G0` rapid).
- [ ] Try a couple of different `z_feed_mm_min` values (slower and faster)
      and confirm the pen-down speed visibly changes accordingly — this
      setting had **zero effect** before this fix, so this is the first
      time it will do anything.
- [ ] Check pen-down accuracy/registration is still fine — a feed-rate move
      instead of a rapid shouldn't change *where* the pen lands, only *how
      fast* it gets there, but worth confirming a few marks look right.
- [ ] Pen-**up** moves were deliberately left as rapid `G0` (unchanged,
      matches the scoped fix) — no need to check those for a difference.

## Everything else (no CNC time needed)

The other fixes (GUI settings-default correctness, uploader scan isolating
bad sessions, status-display correctness, SQLite lock protocol, atomic
manifest writes, ESP32 tool JSON error handling) are desk/software-only —
already covered by the automated test suite, nothing physical to verify.
