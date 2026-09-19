"""Contract + weave-specific coverage for the plain-weave (warp/weft) mode."""

from __future__ import annotations

import math

import numpy as np
from mode_contract import check_mode_contract

from neje_oracle.blocks.imaging.art.weave import quality_params, weave
from neje_oracle.blocks.imaging.modes import ToneGrid


def test_weave_contract() -> None:
    report = check_mode_contract(weave, quality_params, monotonic=True)
    print(report)


def _uniform_tone(darkness: float, *, size_mm: float = 32.0, cell_mm: float = 1.0) -> ToneGrid:
    cells = round(size_mm / cell_mm)
    return ToneGrid(np.full((cells, cells), darkness), cell_mm, size_mm, size_mm)


def _half_and_half_tone(*, dark: float, light: float, size_mm: float = 40.0, cell_mm: float = 1.0) -> ToneGrid:
    """Left half at `dark`, right half at `light`, so the two halves have equal area."""
    cells = round(size_mm / cell_mm)
    darkness = np.full((cells, cells), light)
    darkness[:, : cells // 2] = dark
    return ToneGrid(darkness, cell_mm, size_mm, size_mm)


def _thread_length(polyline: list[tuple[float, float]]) -> float:
    return sum(math.dist(polyline[i], polyline[i + 1]) for i in range(len(polyline) - 1))


def test_at_a_crossing_exactly_one_thread_is_continuous() -> None:
    """Prove the interlacing from the emitted geometry itself, not from an internal flag.

    On solid black every warp thread crosses every weft thread (both families span the full
    sheet), so any (warp x, weft y) pair away from the borders is a real crossing. A thread is
    "continuous" there when one of its own runs strictly straddles the crossing point; exactly
    one of the two threads meeting at a crossing must straddle it, the other must have a gap.
    """
    tone = _uniform_tone(1.0, size_mm=40.0, cell_mm=1.0)
    lines = weave(tone, thread_pitch_mm=3.0, seed=2)

    vertical = {line[0][0] for line in lines if line[0][0] == line[-1][0]}
    horizontal = {line[0][1] for line in lines if line[0][1] == line[-1][1]}
    assert len(vertical) >= 4 and len(horizontal) >= 4, "need several threads per axis to test crossings"

    def straddles(runs: list[list[tuple[float, float]]], fixed_index: int, free_value: float) -> bool:
        margin = 1e-6
        return any(run[0][fixed_index] < free_value - margin < run[-1][fixed_index] for run in runs)

    warp_runs = {x: [line for line in lines if line[0][0] == line[-1][0] == x] for x in vertical}
    weft_runs = {y: [line for line in lines if line[0][1] == line[-1][1] == y] for y in horizontal}

    checked = 0
    for x in sorted(vertical)[1:-1]:
        for y in sorted(horizontal)[1:-1]:
            warp_continuous = straddles(warp_runs[x], 1, y)
            weft_continuous = straddles(weft_runs[y], 0, x)
            assert warp_continuous != weft_continuous, (
                f"crossing ({x}, {y}): warp_continuous={warp_continuous}, weft_continuous={weft_continuous}"
            )
            checked += 1
    assert checked > 0


def test_denser_region_has_more_thread_length_per_area() -> None:
    tone = _half_and_half_tone(dark=0.9, light=0.15, size_mm=40.0, cell_mm=1.0)
    lines = weave(tone, thread_pitch_mm=2.0, seed=0)

    dark_length = sum(_thread_length(line) for line in lines if max(p[0] for p in line) <= 20.0)
    light_length = sum(_thread_length(line) for line in lines if min(p[0] for p in line) >= 20.0)
    # Equal-area halves (20mm x 40mm each), so comparing totals is comparing density directly.
    assert dark_length > light_length, (dark_length, light_length)


def test_dense_150mm_stroke_count() -> None:
    """Not an assertion beyond non-emptiness -- surfaces the pen-lift count for the report."""
    from mode_contract import TONE_CELL_MM, _tone, dense_line_art

    tone = _tone(dense_line_art(), 150.0, 150.0, TONE_CELL_MM[-1])
    lines = weave(tone, **quality_params(1.0))
    strokes = len([line for line in lines if len(line) >= 2])
    print(f"dense 150mm stroke count: {strokes}")
    assert strokes > 0
