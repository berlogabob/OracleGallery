"""How long a G-code file will take on the machine, by replaying FluidNC's planner.

Feed-rate arithmetic (length / feed) promised 20 min for a job that ran 76: at the board's
100 mm/s^2 a 0.44 mm segment never gets near its feed, so the time is set by acceleration
and by how fast each corner may be taken, not by F. This replays what the grbl-family
planner does -- junction-deviation corner speeds, a backward and a forward acceleration
pass, a trapezoid per move -- and matched every kept print_svg within 1% (6k-45k lines).

Streaming cost is left out on purpose: with ok_wait one round trip per line was measured
at ~0 ms of residual, because the planner, not the link, is the bottleneck.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any

_WORD = re.compile(r"([XYZFP])(-?\d*\.?\d+)")


@dataclass(frozen=True)
class MachineLimits:
    """What the controller enforces. Mirrors echodraw/hardware/configs/config.yaml."""

    xy_acceleration_mm_s2: float = 100.0
    xy_max_rate_mm_min: float = 8000.0
    z_acceleration_mm_s2: float = 1000.0
    z_max_rate_mm_min: float = 10000.0
    # FluidNC's default; the board config does not override it.
    junction_deviation_mm: float = 0.01


def limits_for(settings: Any) -> MachineLimits:
    # ponytail: only XY acceleration is a knob; rates and Z are the board's constants. Make
    # them settings the day the board config changes.
    return MachineLimits(xy_acceleration_mm_s2=float(settings.xy_acceleration_mm_s2))


def line_times(gcode: str, limits: MachineLimits = MachineLimits()) -> list[float]:
    """Cumulative seconds at the end of each line: `result[i]` is when line i finishes.

    Indexed like `gcode.splitlines()`, so a streamer that knows how many lines were sent
    can read the remaining time as `result[-1] - result[sent - 1]`.
    """
    lines = gcode.splitlines()
    moves = _parse(lines, limits)
    ends = _move_seconds(moves, limits.junction_deviation_mm)
    cumulative: list[float] = []
    elapsed = 0.0
    move_index = 0
    for index in range(len(lines)):
        while move_index < len(moves) and moves[move_index].line == index:
            elapsed += ends[move_index]
            move_index += 1
        cumulative.append(elapsed)
    return cumulative


def estimate(gcode: str, limits: MachineLimits = MachineLimits()) -> tuple[float, float]:
    """(xy_seconds, pen_seconds). Pen = Z-only moves and G4 dwells, the pen-lift cost."""
    moves = _parse(gcode.splitlines(), limits)
    seconds = _move_seconds(moves, limits.junction_deviation_mm)
    xy = sum(s for move, s in zip(moves, seconds, strict=True) if not move.pen)
    return xy, sum(seconds) - xy


@dataclass(frozen=True)
class _Move:
    line: int
    unit: tuple[float, float, float]
    length: float  # 0 for a dwell, whose duration is carried in `dwell`
    max_speed: float  # mm/s
    acceleration: float  # mm/s^2
    pen: bool
    dwell: float = 0.0


def _parse(lines: list[str], limits: MachineLimits) -> list[_Move]:
    rate = (limits.xy_max_rate_mm_min / 60, limits.xy_max_rate_mm_min / 60, limits.z_max_rate_mm_min / 60)
    accel = (limits.xy_acceleration_mm_s2, limits.xy_acceleration_mm_s2, limits.z_acceleration_mm_s2)
    position = [0.0, 0.0, 0.0]
    feed = limits.xy_max_rate_mm_min / 60  # grbl starts with no F; nothing we emit relies on it
    moves: list[_Move] = []
    for index, raw in enumerate(lines):
        code = raw.split(";", 1)[0].strip().upper()
        if not code:
            continue
        command = code.split()[0]
        words = {key: float(value) for key, value in _WORD.findall(code)}
        if command == "G4":
            moves.append(_Move(index, (0.0, 0.0, 0.0), 0.0, 0.0, 1.0, pen=True, dwell=words.get("P", 0.0)))
            continue
        if command not in ("G0", "G1"):
            continue
        if command == "G1" and "F" in words:
            feed = words["F"] / 60
        target = [words.get(axis, position[i]) for i, axis in enumerate("XYZ")]
        delta = [target[i] - position[i] for i in range(3)]
        position = target
        length = math.sqrt(sum(d * d for d in delta))
        if length == 0:
            continue
        unit = (delta[0] / length, delta[1] / length, delta[2] / length)
        # G0 always runs at the axis max rate; an F on a G0 line changes nothing.
        speed = math.inf if command == "G0" else feed
        acceleration = math.inf
        for i in range(3):
            if abs(unit[i]) > 1e-9:
                speed = min(speed, rate[i] / abs(unit[i]))
                acceleration = min(acceleration, accel[i] / abs(unit[i]))
        pen = delta[0] == 0 and delta[1] == 0
        moves.append(_Move(index, unit, length, speed, acceleration, pen=pen))
    return moves


def _move_seconds(moves: list[_Move], junction_deviation: float) -> list[float]:
    """Seconds per move. Dwells and the moves either side of them start and end at rest."""
    count = len(moves)
    junction = [0.0] * (count + 1)
    for i in range(1, count):
        before, after = moves[i - 1], moves[i]
        if before.length == 0 or after.length == 0:
            continue
        cos_theta = -sum(a * b for a, b in zip(before.unit, after.unit, strict=True))
        if cos_theta > 0.999999:  # full reversal
            speed = 0.0
        elif cos_theta < -0.999999:  # straight on
            speed = min(before.max_speed, after.max_speed)
        else:
            sin_half = math.sqrt(0.5 * (1.0 - cos_theta))
            acceleration = min(before.acceleration, after.acceleration)
            speed = math.sqrt(acceleration * junction_deviation * sin_half / (1.0 - sin_half))
        junction[i] = min(speed, before.max_speed, after.max_speed)
    # Backward then forward: every move must be able to stop in time and to get up to speed.
    for i in range(count - 1, -1, -1):
        move = moves[i]
        junction[i] = min(junction[i], math.sqrt(junction[i + 1] ** 2 + 2 * move.acceleration * move.length))
    for i in range(count):
        move = moves[i]
        junction[i + 1] = min(junction[i + 1], math.sqrt(junction[i] ** 2 + 2 * move.acceleration * move.length))

    seconds: list[float] = []
    for i, move in enumerate(moves):
        if move.length == 0:
            seconds.append(move.dwell)
            continue
        v0, v1, vmax, a = junction[i], junction[i + 1], move.max_speed, move.acceleration
        accelerate = (vmax * vmax - v0 * v0) / (2 * a)
        decelerate = (vmax * vmax - v1 * v1) / (2 * a)
        if accelerate + decelerate <= move.length:
            seconds.append((vmax - v0) / a + (vmax - v1) / a + (move.length - accelerate - decelerate) / vmax)
        else:  # triangle: never reaches vmax
            peak = math.sqrt((2 * a * move.length + v0 * v0 + v1 * v1) / 2)
            seconds.append((peak - v0) / a + (peak - v1) / a)
    return seconds
