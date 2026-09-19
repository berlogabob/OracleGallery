"""The five named Z positions, held in servo microseconds.

The Z axis is an RC servo, and its "millimetres" are fiction: the board's 25 Z units span a
measured 6.8 mm of real pen travel (reports/2026-09-09_HARDWARE_SESSION.md), about 0.27 mm
per unit. Tuning in those units means tuning in a made-up scale, so the positions live here
in the pulse microseconds the servo actually takes -- the same units scripts/z_servo_tune.py
nudges -- and the millimetres the G-code needs are derived.

FluidNC interpolates pulse linearly across the axis travel, so two endpoint pulses define
everything between them. On this machine the range is inverted on purpose (pulse RISES as
the pen goes down), which is why min_pulse_us > max_pulse_us in the board yaml.

Why five, top to bottom:

    top mechanical      above home; the linkage can cross over and lock past it
    top soft            pen-up travel, and where homing leaves the axis
    pen load            park for getting a pen in and out of the holder
    bottom soft         DRAWING: the servo stops here and the holder's spring presses
    bottom mechanical   arm square to the body; past this something breaks

Only the two soft positions and pen load are ever commanded. The mechanical pair are
reference marks the operator measures once and tunes against -- and the reason the drawing
position exists at all: parking the servo on its bottom stop to draw is a stall, and a
stalled servo holds near stall current with no protection until it dies (2026-08-31).
"""

from __future__ import annotations

from dataclasses import dataclass

# The board's own endpoints (echodraw/hardware/configs/config.yaml, axes/Z/motor0/rc_servo).
# Kept as defaults rather than read at import: the GUI stores its own copy so a re-tuned
# servo moves every derived millimetre with it, and a system check compares both to the board.
DEFAULT_TOP_PULSE_US = 2100  # Z0
DEFAULT_BOTTOM_PULSE_US = 2400  # Z-25
DEFAULT_TRAVEL_MM = 25.0
# The leash scripts/z_servo_tune.py hand-nudges inside. A value outside it is not a servo
# position at all -- it is a typo or a half-written settings file, and it derives a Z target
# metres away from the machine.
PULSE_FLOOR_US = 400
PULSE_CEILING_US = 2600

# What the operator measured with a rule: the real pen travel across the sweep they measured
# it over. 6.8 mm across the full 2100-2400 range was measured on 2026-09-09, which is where
# the default comes from. The machine's own "millimetres" are fiction, so this is the only
# honest way to read a position in a unit a pen and a sheet of paper share.
DEFAULT_REAL_SPAN_MM = 6.8
DEFAULT_REAL_SPAN_US = 300

Z_TOP_MM = 0.0


@dataclass(frozen=True)
class ZPulseRange:
    """The two endpoint pulses and the travel they span, as the controller is configured."""

    top_us: int = DEFAULT_TOP_PULSE_US
    bottom_us: int = DEFAULT_BOTTOM_PULSE_US
    travel_mm: float = DEFAULT_TRAVEL_MM

    @property
    def bottom_mm(self) -> float:
        return Z_TOP_MM - abs(self.travel_mm)


def pulse_for_z(z_mm: float, pulses: ZPulseRange | None = None) -> int:
    """The pulse the controller holds at a commanded Z."""
    pulses = pulses or ZPulseRange()
    span = (z_mm - Z_TOP_MM) / (pulses.bottom_mm - Z_TOP_MM) if pulses.bottom_mm != Z_TOP_MM else 0.0
    return round(pulses.top_us + span * (pulses.bottom_us - pulses.top_us))


def z_for_pulse(pulse_us: float, pulses: ZPulseRange | None = None) -> float:
    """The Z to command for a pulse. The inverse of pulse_for_z, rounded to the micron.

    Rounded because it is written into G-code with three decimals anyway, and an exact
    binary fraction here would print as 23.999999999999996 in a settings file an operator
    reads.
    """
    pulses = pulses or ZPulseRange()
    if pulses.bottom_us == pulses.top_us:  # a degenerate range would divide by zero
        return Z_TOP_MM
    span = (pulse_us - pulses.top_us) / (pulses.bottom_us - pulses.top_us)
    return round(Z_TOP_MM + span * (pulses.bottom_mm - Z_TOP_MM), 3)


@dataclass(frozen=True)
class ZPositions:
    """The five positions in microseconds, top to bottom."""

    top_mech_us: int = DEFAULT_TOP_PULSE_US
    top_soft_us: int = DEFAULT_TOP_PULSE_US
    load_us: int = 2388
    bottom_soft_us: int = DEFAULT_BOTTOM_PULSE_US
    bottom_mech_us: int = DEFAULT_BOTTOM_PULSE_US

    def problems(self) -> list[str]:
        """Why this set is not usable, in the operator's words. Empty means it is.

        Refused rather than clamped: a clamp would quietly move a position the operator
        just measured, and an inverted pair here drives the pen either through the paper
        or through its own end stop.
        """
        found = []
        for name, value in (
            ("top mechanical", self.top_mech_us),
            ("top soft", self.top_soft_us),
            ("pen load", self.load_us),
            ("drawing", self.bottom_soft_us),
            ("bottom mechanical", self.bottom_mech_us),
        ):
            if not PULSE_FLOOR_US <= value <= PULSE_CEILING_US:
                found.append(f"{name} is {value}us, outside the {PULSE_FLOOR_US}-{PULSE_CEILING_US}us the servo takes")
        if found:
            return found
        if self.top_soft_us < self.top_mech_us:
            found.append("top soft is above top mechanical -- the linkage can lock there")
        if self.load_us <= self.top_soft_us:
            found.append("pen load must sit below top soft")
        if self.bottom_soft_us <= self.load_us:
            found.append("drawing must sit below pen load")
        if self.bottom_soft_us > self.bottom_mech_us:
            found.append("drawing is past bottom mechanical -- the servo would stall against its stop")
        return found


def mm_per_us(span_mm: float = DEFAULT_REAL_SPAN_MM, span_us: float = DEFAULT_REAL_SPAN_US) -> float:
    """Real millimetres of pen travel per microsecond of pulse, from one measured sweep.

    Measured rather than derived: the linkage turns a linear pulse ramp into an arc, so the
    only number worth trusting is the one that came off a rule between two known positions.
    """
    if span_us == 0:
        return 0.0
    return abs(span_mm) / abs(span_us)


def real_mm_between(from_us: float, to_us: float, span_mm: float, span_us: float) -> float:
    """How far the pen really moves between two pulses, in millimetres.

    Positive means the pen goes DOWN, matching the way a thickness adds to a stack.
    """
    return (to_us - from_us) * mm_per_us(span_mm, span_us)


def pulse_for_real_mm(distance_mm: float, span_mm: float, span_us: float) -> int:
    """The pulse offset that moves the pen `distance_mm` -- the inverse of real_mm_between.

    This is how a material thickness becomes a Z correction: put a 2 mm mat on the bed and
    the drawing position has to rise by 2 mm of real travel, which is this many microseconds.
    """
    scale = mm_per_us(span_mm, span_us)
    if scale == 0:
        return 0
    return round(distance_mm / scale)


def with_material(positions: ZPositions, material_us: int) -> ZPositions:
    """The positions to actually command with a material of `material_us` on the bed.

    Drawing and pen load rise by the thickness, because both are referenced to the surface
    the pen meets. Pen-up deliberately does NOT move: it is referenced to the machine, and
    lifting it further for every sheet of card would add pen-lift time to every stroke of
    every plot -- and lifts are already about half of this machine's plot time.
    """
    if material_us <= 0:
        return positions
    return ZPositions(
        top_mech_us=positions.top_mech_us,
        top_soft_us=positions.top_soft_us,
        load_us=max(PULSE_FLOOR_US, positions.load_us - material_us),
        bottom_soft_us=max(PULSE_FLOOR_US, positions.bottom_soft_us - material_us),
        bottom_mech_us=positions.bottom_mech_us,
    )
