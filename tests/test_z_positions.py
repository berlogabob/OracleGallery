"""The pulse <-> Z mapping, and what makes a set of five positions usable.

The Z axis is a servo whose millimetres are fiction (25 units span a measured 6.8 mm), so
the positions are stored as the pulses the servo really takes and the millimetres are
derived. Everything downstream still speaks millimetres, which is why the conversion is
worth pinning.
"""

from __future__ import annotations

import pytest

from neje_oracle.shared.z_positions import ZPositions, ZPulseRange, pulse_for_z, z_for_pulse

BOARD = ZPulseRange()  # 2100 at Z0, 2400 at Z-25, as the board yaml has it


def test_the_boards_own_endpoints():
    assert pulse_for_z(0.0, BOARD) == 2100
    assert pulse_for_z(-25.0, BOARD) == 2400
    assert z_for_pulse(2100, BOARD) == 0.0
    assert z_for_pulse(2400, BOARD) == -25.0


def test_twelve_microseconds_per_z_unit():
    """300 us over 25 units. It is what makes a 5 us tuning step meaningful: less than
    half a Z unit, well inside what a hand nudge should move."""
    assert pulse_for_z(-1.0, BOARD) - pulse_for_z(0.0, BOARD) == 12
    assert z_for_pulse(2388, BOARD) == -24.0


def test_the_range_is_inverted_on_purpose():
    """Pulse rises as the pen goes down -- min_pulse_us > max_pulse_us in the yaml is the
    reversed-servo mapping, not a typo. A conversion that assumed otherwise would drive
    the pen up when asked for down."""
    assert pulse_for_z(-10.0, BOARD) > pulse_for_z(-1.0, BOARD)


def test_round_trip_through_both_directions():
    for pulse in range(2100, 2401, 7):
        assert pulse_for_z(z_for_pulse(pulse, BOARD), BOARD) == pulse


def test_a_retuned_servo_moves_every_position_with_it():
    """The endpoints are stored, not assumed: after a horn remount the same microsecond
    value means a different Z, and every derived millimetre has to follow."""
    retuned = ZPulseRange(top_us=1900, bottom_us=2300)

    assert z_for_pulse(2100, retuned) != z_for_pulse(2100, BOARD)
    assert z_for_pulse(retuned.top_us, retuned) == 0.0
    assert z_for_pulse(retuned.bottom_us, retuned) == -25.0


def test_a_degenerate_range_does_not_divide_by_zero():
    """A half-finished tuning session can leave both endpoints equal in the settings file."""
    flat = ZPulseRange(top_us=2100, bottom_us=2100)

    assert z_for_pulse(2100, flat) == 0.0
    assert pulse_for_z(-25.0, flat) == 2100


def test_the_shipped_five_are_in_order():
    assert ZPositions().problems() == []


@pytest.mark.parametrize(
    ("positions", "complaint"),
    [
        (ZPositions(top_mech_us=2150), "top soft is above top mechanical"),
        (ZPositions(load_us=2100), "pen load must sit below top soft"),
        (ZPositions(load_us=2399, bottom_soft_us=2399), "drawing must sit below pen load"),
        (ZPositions(bottom_soft_us=2450), "drawing is past bottom mechanical"),
    ],
)
def test_an_inverted_pair_is_refused_with_its_own_complaint(positions: ZPositions, complaint: str) -> None:
    """Refused, not clamped: clamping would quietly move a position just measured off the
    machine, and an inversion here drives the pen through the paper or the end stop."""
    problems = positions.problems()

    assert any(complaint in problem for problem in problems), problems


def test_millimetres_are_unknown_until_somebody_measures_them() -> None:
    """The shipped state is "nobody has measured this servo", and it says so rather than
    deriving a figure from someone else's machine."""
    from neje_oracle.shared.z_positions import (
        DEFAULT_REAL_SPAN_MM,
        DEFAULT_REAL_SPAN_US,
        is_measured,
        pulse_for_real_mm,
        real_mm_between,
    )

    assert not is_measured(DEFAULT_REAL_SPAN_MM, DEFAULT_REAL_SPAN_US)
    assert real_mm_between(2100, 2400, DEFAULT_REAL_SPAN_MM, DEFAULT_REAL_SPAN_US) is None
    # And a material thickness moves nothing: without a scale the correction would be a
    # guess, and the pen is what pays for it.
    assert pulse_for_real_mm(2.0, DEFAULT_REAL_SPAN_MM, DEFAULT_REAL_SPAN_US) == 0

    assert real_mm_between(2100, 2400, 6.8, 300) == pytest.approx(6.8)
    assert pulse_for_real_mm(2.0, 6.8, 300) == 88


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
