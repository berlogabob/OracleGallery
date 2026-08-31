"""Interactive Z-servo range tuner: find the real mechanical top/bottom after remounting.

Run in its own terminal:  uv run python scripts/z_servo_tune.py

The servo maps min_pulse_us -> Z-25 (bottom) and max_pulse_us -> Z0 (top).
If the arm grinds at the top, LOWER max_pulse until Z0 sits just inside the
mechanical range. If the bottom is short/deep, adjust min_pulse the same way.
Pulse changes apply live to the board (RAM only) -- nothing is saved until you
copy the final numbers into TinyBee-06.yaml on the board.

Commands (type, then Enter):
  t          go to Z0 (top)            b     go to Z-25 (bottom)
  m          go to Z-12 (middle)       z -7  go to any Z (example)
  w / s      nudge Z up / down 0.5mm   W / S nudge Z up / down 2mm
  [ / ]      max_pulse -25 / +25 us (re-seats the TOP)
  ; / '      min_pulse -25 / +25 us (re-seats the BOTTOM)
  p          show position + pulses    h     home Z ($H=Z)
  l 38.5     set the measured arm length (shaft -> pen-holder contact), in mm
  q          quit and print the final yaml values

Geometry: the arm pushes the holder up. Bottom is the arm at 90 deg to the servo body
(shelf resting on it, hard floor); top is Z home and must keep ~15 deg of margin from
the dead position where the linkage can lock. Pen height is L*cos(theta), so the whole
usable stroke is L*(cos15 - cos90) ~= 0.966*L. Set `l <mm>` after measuring and `p`
reports the expected travel to sanity-check the endpoints against.
"""

from __future__ import annotations

from math import cos, radians

from neje_oracle.blocks.fluidnc.transport import FluidNCTransport, discover_fluidnc, settings_for_fluidnc_host
from neje_oracle.shared.config import PlotterSettings

MIN_KEY = "$/axes/Z/motor0/rc_servo/min_pulse_us"
MAX_KEY = "$/axes/Z/motor0/rc_servo/max_pulse_us"

# The two mechanical endpoints, as angles from the servo's dead position.
TOP_THETA_DEG = 15.0  # Z0: never 0 deg, or the linkage can cross over and lock.
BOTTOM_THETA_DEG = 90.0  # Z-25: arm square to the body, shelf resting on it.
Z_TOP_MM = 0.0
Z_BOTTOM_MM = -25.0


def arm_height_mm(l_mm: float, theta_deg: float) -> float:
    """Pen height above the bottom stop for an arm of length l_mm at theta from dead."""
    return l_mm * cos(radians(theta_deg))


def theta_for_z(z_mm: float) -> float:
    """Angle at a commanded Z. FluidNC interpolates pulse (hence angle) linearly in Z."""
    span = (z_mm - Z_TOP_MM) / (Z_BOTTOM_MM - Z_TOP_MM)
    return TOP_THETA_DEG + span * (BOTTOM_THETA_DEG - TOP_THETA_DEG)


def geometry_report(l_mm: float, z_mm: float) -> str:
    # ponytail: linear pulse<->Z, trig only at design time; revisit if gearbox rework needs real mm linearity
    if l_mm <= 0:
        return "arm L unset -- measure shaft->holder contact and type: l 38.5"
    travel = arm_height_mm(l_mm, TOP_THETA_DEG) - arm_height_mm(l_mm, BOTTOM_THETA_DEG)
    theta = theta_for_z(z_mm)
    return (
        f"L={l_mm:.1f}mm  theta({z_mm:.2f})={theta:.1f}deg  "
        f"height={arm_height_mm(l_mm, theta):.2f}mm  travel(top->bottom)={travel:.2f}mm"
    )


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

    def read_pulse(key: str) -> str:
        result = t.send_command(key, wait_for_ok=True)
        for line in result.response_lines:
            if "=" in line:
                return line.split("=", 1)[1].strip()
        return "?"

    def set_pulse(key: str, value: int) -> None:
        result = t.send_command(f"{key}={value}", wait_for_ok=True)
        print(f"{key.split('/')[-1]} = {value} -> {'ok' if result.ok else result.message}")

    def goto(z: float) -> None:
        result = t.send_commands(["G21", "G90", "G54", f"G1 Z{z:.2f} F600"])
        print(f"Z{z:.2f} -> {'ok' if result.ok else result.message}")

    def status() -> float:
        p = t.probe(timeout_seconds=2)
        z = p.controller.machine_position[2] if p.controller and p.controller.machine_position else float("nan")
        print(f"Z={z:.2f}  min_pulse={read_pulse(MIN_KEY)}  max_pulse={read_pulse(MAX_KEY)}  state={p.controller.state.value if p.controller else '?'}")
        return z

    arm_mm = 0.0
    current_z = status()
    print(geometry_report(arm_mm, current_z))
    while True:
        try:
            cmd = input("tune> ").strip()
        except (EOFError, KeyboardInterrupt):
            cmd = "q"
        if not cmd:
            continue
        if cmd == "q":
            print("\nFinal values for TinyBee-06.yaml (axes -> z -> motor0 -> rc_servo):")
            print(f"  min_pulse_us: {read_pulse(MIN_KEY)}")
            print(f"  max_pulse_us: {read_pulse(MAX_KEY)}")
            print(geometry_report(arm_mm, current_z))
            print("NOTE: live values are RAM-only; they reset on reboot until saved to the yaml.")
            return
        elif cmd == "t":
            current_z = 0.0; goto(current_z)
        elif cmd == "b":
            current_z = -25.0; goto(current_z)
        elif cmd == "m":
            current_z = -12.0; goto(current_z)
        elif cmd.startswith("z"):
            try:
                current_z = float(cmd[1:].strip()); goto(current_z)
            except ValueError:
                print("usage: z -7.5")
        elif cmd in ("w", "s", "W", "S"):
            step = {"w": 0.5, "s": -0.5, "W": 2.0, "S": -2.0}[cmd]
            current_z = max(-25.0, min(0.0, current_z + step)); goto(current_z)
        elif cmd in ("[", "]"):
            value = int(float(read_pulse(MAX_KEY))) + (25 if cmd == "]" else -25)
            set_pulse(MAX_KEY, value); goto(current_z)
        elif cmd in (";", "'"):
            value = int(float(read_pulse(MIN_KEY))) + (25 if cmd == "'" else -25)
            set_pulse(MIN_KEY, value); goto(current_z)
        elif cmd == "p":
            current_z = status()
            print(geometry_report(arm_mm, current_z))
        elif cmd.startswith("l"):
            try:
                arm_mm = float(cmd[1:].strip())
            except ValueError:
                print("usage: l 38.5")
            else:
                print(geometry_report(arm_mm, current_z))
        elif cmd == "h":
            result = t.home("Z")
            print("home Z ->", "ok" if result.ok else result.message)
        else:
            print(__doc__.split("Commands", 1)[1])


if __name__ == "__main__":
    main()
