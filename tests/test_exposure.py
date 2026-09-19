"""Solving a mode's detail for the ink it actually lays.

Every mode's spacing is tuned against a ~150 mm sheet, so at a grid cell's few centimetres
the shipped numbers put geometry bigger than the subject into the picture and the cell reads
as abstraction. The solve replaces a guessed multiplier with a measurement.
"""

from __future__ import annotations

import math

import pytest

from neje_oracle.blocks.imaging.exposure import DEFAULT_TARGET_INK_PER_MM2, expose, ink_mm

AREA = 100.0  # a 10 x 10 mm patch keeps the arithmetic readable


def _lines(total_mm: float) -> list[list[tuple[float, float]]]:
    """One polyline of a known length, so a fake mode can promise exact ink."""
    return [[(0.0, 0.0), (total_mm, 0.0)]] if total_mm > 0 else []


def test_ink_mm_measures_drawn_length() -> None:
    assert ink_mm([[(0.0, 0.0), (3.0, 4.0)]]) == pytest.approx(5.0)
    assert ink_mm([[(0.0, 0.0)]]) == 0.0, "a single point is not a stroke"


def test_a_mode_already_at_the_target_is_left_alone() -> None:
    """No reason to spend renders on a cell that already reads."""
    calls: list[float] = []

    def render(detail: float):
        calls.append(detail)
        return _lines(AREA * DEFAULT_TARGET_INK_PER_MM2)

    result = expose(render, area_mm2=AREA)

    assert result.detail == 1.0
    assert calls == [1.0], "a satisfied mode should be rendered once"
    assert not result.saturated


def test_the_solve_lands_near_the_target() -> None:
    """Ink proportional to detail: the answer is knowable, so check it is found."""

    def render(detail: float):
        return _lines(AREA * 0.1 * detail)  # target 1.0 wants detail 10

    result = expose(render, area_mm2=AREA, detail_bounds=(1.0, 12.0), steps=8)

    assert result.ink_per_mm2 == pytest.approx(DEFAULT_TARGET_INK_PER_MM2, rel=0.35)
    assert 7.0 < result.detail <= 12.0


def test_a_mode_that_cannot_reach_the_target_says_so() -> None:
    """stitch saturates, ripple and sunburst top out near a third of the target: the honest
    answer is the finest setting plus a flag, not a number invented for it."""

    def render(detail: float):
        return _lines(AREA * 0.2)  # flat, whatever the detail

    result = expose(render, area_mm2=AREA, detail_bounds=(1.0, 8.0))

    assert result.saturated
    assert result.ink_per_mm2 == pytest.approx(0.2)


def test_a_refusal_is_read_as_too_fine() -> None:
    """Several modes refuse a spacing their geometry cannot hold -- rings raises once its
    rings fall under the nib. The solve must step back, not propagate."""

    def render(detail: float):
        if detail > 3.0:
            raise ValueError("pitch leaves a ring under the nib")
        return _lines(AREA * 0.2 * detail)

    result = expose(render, area_mm2=AREA, detail_bounds=(1.0, 12.0), steps=6)

    assert result.detail <= 3.0
    assert result.ink_per_mm2 > 0.2, "it should still have improved on the shipped setting"


def test_the_shipped_setting_is_a_floor() -> None:
    """Not every mode is monotonic: rings drops circles the nib cannot resolve and halftone's
    marks fall under the minimum stroke, so a finer setting can draw LESS -- once, nothing."""

    def render(detail: float):
        return _lines(AREA * 0.4) if detail <= 1.0 else _lines(0.0)

    result = expose(render, area_mm2=AREA, detail_bounds=(1.0, 6.0))

    assert result.ink_per_mm2 == pytest.approx(0.4)
    assert result.detail == 1.0


def test_a_mode_that_refuses_everything_raises() -> None:
    def render(detail: float):
        raise ValueError("nope")

    with pytest.raises(ValueError, match="coarsest"):
        expose(render, area_mm2=AREA)


def test_bad_arguments_are_refused() -> None:
    with pytest.raises(ValueError, match="area_mm2"):
        expose(lambda detail: _lines(1.0), area_mm2=0.0)
    with pytest.raises(ValueError, match="detail_bounds"):
        expose(lambda detail: _lines(1.0), area_mm2=AREA, detail_bounds=(4.0, 1.0))


def test_the_solve_costs_a_handful_of_renders() -> None:
    """A whole sheet is re-rendered per solve, so the render count is the cost that matters."""
    calls: list[float] = []

    def render(detail: float):
        calls.append(detail)
        return _lines(AREA * 0.05 * detail)

    expose(render, area_mm2=AREA, detail_bounds=(1.0, 12.0), steps=4)

    assert len(calls) <= 6, calls


def test_geometric_steps_reach_the_top_of_the_range() -> None:
    """detail is a scale factor, so the search walks it geometrically: a linear bisection
    spends its steps near the coarse end, where nothing happens."""
    seen: list[float] = []

    def render(detail: float):
        seen.append(detail)
        return _lines(AREA * 0.2 * detail)  # passes the target inside the range, so it bisects

    expose(render, area_mm2=AREA, detail_bounds=(1.0, 16.0), steps=4)

    assert max(seen) == 16.0
    assert any(math.isclose(value, 4.0, rel_tol=0.01) for value in seen), seen


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
