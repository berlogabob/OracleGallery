"""Interactive Z-servo tuner: drive the servo by hand, mark the two endpoints, save.

Run in its own terminal:  uv run python scripts/z_servo_tune.py

Keys are single presses -- no Enter.

  up / w     nudge the servo one step    down / s   nudge it the other way
  + / -      step size up / down the ladder 1 2 5 10 20 50 (starts at 10us)
  T          mark HERE as the TOP        B          mark HERE as the BOTTOM
  t / b / m  go to the marked top / bottom / the middle
  p          position, pulses, marks     h          home Z ($H=Z)
  z          type an absolute Z          l          type the measured arm length
  q          write the marks back and print the yaml values

Nudging drives the pulse, not Z: the servo parks at Z0 and the top pulse is moved
live, so no soft limit is in the way while the horn is loose. Whichever way "up"
turns out to be, just mark the ends with T and B -- if the top mark lands below
the bottom mark that IS the min/max swap FluidNC documents for a reversed servo,
and q prints the two values already in the order the yaml wants them.

Geometry: the arm pushes the holder up. Bottom is the arm at 90 deg to the servo
body (shelf resting on it, hard floor); top is Z home and must keep ~15 deg of
margin from the dead position where the linkage can lock. Pen height is
L*cos(theta), so the usable stroke is L*(cos15 - cos90) ~= 0.966*L. Set the
measured arm length with `l` and `p` reports the travel to check the ends against.

Nothing here is saved: pulse changes are RAM-only until the numbers q prints are
copied into TinyBee-06.yaml and uploaded to the board.
"""

from __future__ import annotations

import sys
import termios
import tty
from math import cos, radians

from neje_oracle.blocks.fluidnc.transport import FluidNCTransport, discover_fluidnc, settings_for_fluidnc_host
from neje_oracle.shared.config import PlotterSettings

MIN_KEY = "$/axes/Z/motor0/rc_servo/min_pulse_us"
MAX_KEY = "$/axes/Z/motor0/rc_servo/max_pulse_us"

# Leash for hand-nudging. Wide enough to find any sane horn seating, narrow enough
# that a stuck key cannot walk the servo into a stall against its internal stops.
PULSE_FLOOR_US = 400
PULSE_CEILING_US = 2600

# The two mechanical endpoints, as angles from the servo's dead position.
TOP_THETA_DEG = 15.0  # Z0: never 0 deg, or the linkage can cross over and lock.
BOTTOM_THETA_DEG = 90.0  # Z-25: arm square to the body, shelf resting on it.
Z_TOP_MM = 0.0
Z_BOTTOM_MM = -25.0

ARROWS = {"[A": "up", "[B": "down", "[C": "right", "[D": "left"}

# A ladder, not doubling: an SG90's dead band is 5-10us, so 10 and 20 are the sizes that
# actually tune anything -- and doubling from 10 can never return to 10 (10 -> 5 -> 2 ->
# 1 -> 2 -> 4 -> 8 -> 16), which stranded a live tuning session on 2026-08-31.
STEP_LADDER = (1, 2, 5, 10, 20, 50)
DEAD_BAND_US = 10


def arm_height_mm(l_mm: float, theta_deg: float) -> float:
    """Pen height above the bottom stop for an arm of length l_mm at theta from dead."""
    return l_mm * cos(radians(theta_deg))


def theta_for_z(z_mm: float) -> float:
    """Angle at a commanded Z. FluidNC interpolates pulse (hence angle) linearly in Z."""
    span = (z_mm - Z_TOP_MM) / (Z_BOTTOM_MM - Z_TOP_MM)
    return TOP_THETA_DEG + span * (BOTTOM_THETA_DEG - TOP_THETA_DEG)


def pulse_for_z(z_mm: float, top_pulse: int, bottom_pulse: int) -> int:
    """The pulse FluidNC holds at a commanded Z, given the two endpoint pulses."""
    span = (z_mm - Z_TOP_MM) / (Z_BOTTOM_MM - Z_TOP_MM)
    return round(top_pulse + span * (bottom_pulse - top_pulse))


def geometry_report(l_mm: float, z_mm: float) -> str:
    # ponytail: linear pulse<->Z, trig only at design time; revisit if gearbox rework needs real mm linearity
    if l_mm <= 0:
        return "arm L unset -- measure shaft->holder contact, press l and type it"
    travel = arm_height_mm(l_mm, TOP_THETA_DEG) - arm_height_mm(l_mm, BOTTOM_THETA_DEG)
    theta = theta_for_z(z_mm)
    return (
        f"L={l_mm:.1f}mm  theta({z_mm:.2f})={theta:.1f}deg  "
        f"height={arm_height_mm(l_mm, theta):.2f}mm  travel(top->bottom)={travel:.2f}mm"
    )


def read_key() -> str:
    """One keypress, no Enter. Arrow keys come back as 'up' / 'down' / 'left' / 'right'.

    cbreak, not raw, so Ctrl-C still raises KeyboardInterrupt -- with a servo on the
    other end of this loop, the panic key has to keep working.
    """
    fd = sys.stdin.fileno()
    saved = termios.tcgetattr(fd)
    try:
        tty.setcbreak(fd)
        char = sys.stdin.read(1)
        if char == "\x1b":  # an escape sequence; a bare Esc would block here, so don't press it
            return ARROWS.get(sys.stdin.read(2), "esc")
        return char
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, saved)


def prompt(label: str) -> str:
    """Line input for the two commands that need a number. Terminal is already cooked."""
    try:
        return input(label).strip()
    except (EOFError, KeyboardInterrupt):
        return ""


def main() -> None:
    # The hotspot re-deals IPs after every drop: try the configured host, then scan.
    settings = PlotterSettings()
    t = FluidNCTransport(settings)
    probe = t.probe(timeout_seconds=3)
    if not probe.telnet_online:
        print(f"{settings.fluidnc_telnet_host} not answering; scanning the subnet...")
        probe = discover_fluidnc(settings)
        if not probe.telnet_online:
            print("No FluidNC found:", probe.message)
            return
        t = FluidNCTransport(settings_for_fluidnc_host(settings, probe.telnet_host))
        print(f"Found the board at {probe.telnet_host} -- update NEJE_PLOTTER_FLUIDNC_TELNET_HOST in .env")
    print(probe.message)
    if probe.controller and probe.controller.is_alarm:
        print("unlocking alarm:", t.unlock_alarm().message)

    def read_pulse(key: str) -> int:
        result = t.send_command(key, wait_for_ok=True)
        for line in result.response_lines:
            if "=" in line:
                return int(float(line.split("=", 1)[1].strip()))
        return 0

    def set_pulse(key: str, value: int) -> None:
        result = t.send_command(f"{key}={value}", wait_for_ok=True)
        if not result.ok:
            print(f"{key.split('/')[-1]}={value} rejected: {result.message}")

    def goto(z: float) -> None:
        result = t.send_commands(["G21", "G90", "G54", f"G1 Z{z:.2f} F600"])
        if not result.ok:
            print(f"Z{z:.2f} -> {result.message}")

    def apply_marks() -> None:
        """Push the marked endpoints back into the live config, in yaml order."""
        set_pulse(MIN_KEY, bottom_pulse)
        set_pulse(MAX_KEY, top_pulse)

    def hold(pulse: int) -> None:
        """Park the servo at an arbitrary pulse: make it the Z0 end and command Z0."""
        set_pulse(MAX_KEY, pulse)
        goto(Z_TOP_MM)

    def status() -> float:
        p = t.probe(timeout_seconds=2)
        z = p.controller.machine_position[2] if p.controller and p.controller.machine_position else float("nan")
        state = p.controller.state.value if p.controller else "?"
        print(
            f"Z={z:.2f}  live={live_pulse}us  step={step_us}us  "
            f"marks: top={top_pulse} bottom={bottom_pulse}  state={state}"
        )
        return z

    top_pulse = read_pulse(MAX_KEY)
    bottom_pulse = read_pulse(MIN_KEY)
    live_pulse = top_pulse
    step_us = 10  # must stay a STEP_LADDER value
    arm_mm = 0.0
    current_z = Z_TOP_MM
    print(f"board pulses: min={bottom_pulse} max={top_pulse}")
    print("keys: up/down nudge, T/B mark here, t/b/m go, p status, l arm length, q quit")

    while True:
        try:
            key = read_key()
        except KeyboardInterrupt:
            key = "q"
        if key in ("q", "esc"):
            apply_marks()
            print("\nFinal values for TinyBee-06.yaml (axes -> z -> motor0 -> rc_servo):")
            print(f"  min_pulse_us: {bottom_pulse}")
            print(f"  max_pulse_us: {top_pulse}")
            if top_pulse < bottom_pulse:
                print("  (top below bottom: that is the reversed-servo swap, the order above is correct)")
            print(geometry_report(arm_mm, current_z))
            print("NOTE: live values are RAM-only; they reset on reboot until saved to the yaml.")
            return
        if key in ("up", "w", "down", "s"):
            delta = step_us if key in ("up", "w") else -step_us
            nudged = max(PULSE_FLOOR_US, min(PULSE_CEILING_US, live_pulse + delta))
            if nudged == live_pulse:
                print(f"pulse leash: staying inside {PULSE_FLOOR_US}..{PULSE_CEILING_US}us")
                continue
            live_pulse = nudged
            current_z = Z_TOP_MM
            hold(live_pulse)
            print(f"pulse {live_pulse}us")
        elif key in ("+", "=", "-", "_"):
            rung = STEP_LADDER.index(step_us) + (1 if key in ("+", "=") else -1)
            step_us = STEP_LADDER[max(0, min(len(STEP_LADDER) - 1, rung))]
            hint = "  (below the SG90 dead band -- may do nothing)" if step_us < DEAD_BAND_US else ""
            print(f"step {step_us}us{hint}")
        elif key == "T":
            top_pulse = live_pulse
            print(f"TOP marked at {top_pulse}us")
        elif key == "B":
            bottom_pulse = live_pulse
            print(f"BOTTOM marked at {bottom_pulse}us")
        elif key in ("t", "b", "m"):
            apply_marks()
            current_z = {"t": Z_TOP_MM, "b": Z_BOTTOM_MM, "m": (Z_TOP_MM + Z_BOTTOM_MM) / 2}[key]
            # Track where the servo actually ended up, so the next nudge continues from
            # here instead of snapping back to the last hand-driven pulse.
            live_pulse = pulse_for_z(current_z, top_pulse, bottom_pulse)
            goto(current_z)
            print(f"Z{current_z:.2f}")
        elif key == "z":
            raw = prompt("absolute Z mm> ")
            try:
                current_z = float(raw)
            except ValueError:
                print("not a number")
            else:
                apply_marks()
                live_pulse = pulse_for_z(current_z, top_pulse, bottom_pulse)
                goto(current_z)
        elif key == "l":
            raw = prompt("arm length mm (shaft -> holder contact)> ")
            try:
                arm_mm = float(raw)
            except ValueError:
                print("not a number")
            else:
                print(geometry_report(arm_mm, current_z))
        elif key == "p":
            current_z = status()
            print(geometry_report(arm_mm, current_z))
        elif key == "h":
            apply_marks()
            result = t.home("Z")
            print("home Z ->", "ok" if result.ok else result.message)
        else:
            print(__doc__.split("Keys are single presses -- no Enter.", 1)[1].split("Nudging", 1)[0])


def selftest() -> None:
    """uv run python scripts/z_servo_tune.py --selftest -- no board needed."""
    assert abs(arm_height_mm(40.0, BOTTOM_THETA_DEG)) < 1e-9
    assert abs(arm_height_mm(40.0, TOP_THETA_DEG) - 38.637) < 0.001
    assert theta_for_z(Z_TOP_MM) == TOP_THETA_DEG
    assert theta_for_z(Z_BOTTOM_MM) == BOTTOM_THETA_DEG
    assert pulse_for_z(Z_TOP_MM, 1750, 500) == 1750
    assert pulse_for_z(Z_BOTTOM_MM, 1750, 500) == 500
    assert pulse_for_z(-12.5, 1750, 500) == 1125
    # A reversed servo marks top below bottom; the interpolation has to follow it.
    assert pulse_for_z(Z_BOTTOM_MM, 500, 1750) == 1750
    # Every rung must be reachable from every other, in both directions.
    assert 10 in STEP_LADDER and tuple(sorted(STEP_LADDER)) == STEP_LADDER
    for start in STEP_LADDER:
        seen, step = {start}, start
        for _ in range(len(STEP_LADDER)):
            step = STEP_LADDER[min(len(STEP_LADDER) - 1, STEP_LADDER.index(step) + 1)]
            seen.add(step)
        for _ in range(2 * len(STEP_LADDER)):
            step = STEP_LADDER[max(0, STEP_LADDER.index(step) - 1)]
            seen.add(step)
        assert seen == set(STEP_LADDER), (start, seen)
    print("selftest ok")


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        selftest()
    else:
        main()
