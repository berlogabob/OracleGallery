"""Contract + scribble-specific coverage for the one-line chaotic scribble mode."""

from __future__ import annotations

import math

import numpy as np
from mode_contract import bucket_ink, check_mode_contract, dense_line_art, photo_like

from neje_oracle.blocks.imaging.art.scribble import quality_params, scribble
from neje_oracle.blocks.imaging.modes import ToneGrid, load_tone


def _png_bytes(image) -> bytes:
    import io

    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def test_scribble_contract() -> None:
    report = check_mode_contract(scribble, quality_params, monotonic=True)
    print(report)


def test_scribble_is_almost_never_lifted() -> None:
    """The whole point of this mode is near-zero pen lifts: assert a small, explicit bound.

    dense_line_art is the busy 150 mm render the contract itself uses to reach segment caps
    -- the closest thing to a worst case this mode will see -- and it still comes back as
    exactly one polyline, because scribble has no lift condition at all beyond "nothing
    cleared min_darkness anywhere" (see scribble()'s own docstring).
    """
    tone = load_tone(_png_bytes(dense_line_art()), width_mm=150.0, height_mm=150.0, cell_mm=0.7)
    strokes = scribble(tone, **quality_params(1.6))
    print(f"dense 150mm render: {len(strokes)} stroke(s), {sum(len(s) for s in strokes)} points")
    assert len(strokes) <= 3, f"expected a small, bounded stroke count, got {len(strokes)}"


def test_scribble_stays_in_frame_and_favours_the_dark_half() -> None:
    """Points never leave the sheet, and the darker half of a two-tone image carries more ink.

    Left half dark (0.9), right half lighter but still gated (0.2, well above min_darkness
    0.05) -- both draw, so this isolates the "loops tighter where it's dark" bias from the
    plain on/off gating the contract's own gradient check already covers.
    """
    width_mm, height_mm, cell_mm = 60.0, 40.0, 1.0
    cols, rows = round(width_mm / cell_mm), round(height_mm / cell_mm)
    darkness = np.full((rows, cols), 0.2)
    darkness[:, : cols // 2] = 0.9
    tone = ToneGrid(darkness, cell_mm, width_mm, height_mm)

    strokes = scribble(tone, step_mm=1.0, seed=3)
    assert len(strokes) == 1
    path = strokes[0]

    for x, y in path:
        assert -1e-6 <= x <= width_mm + 1e-6, f"x {x} outside [0, {width_mm}]"
        assert -1e-6 <= y <= height_mm + 1e-6, f"y {y} outside [0, {height_mm}]"

    buckets = bucket_ink(strokes, width_mm, buckets=2)
    dark_ink, light_ink = buckets
    print(f"dark-half ink: {dark_ink:.1f} mm, light-half ink: {light_ink:.1f} mm")
    assert dark_ink > light_ink, ("dark half must carry more ink than the light half", buckets)


def test_scribble_deterministic_on_a_photo() -> None:
    tone = load_tone(_png_bytes(photo_like()), width_mm=80.0, height_mm=48.0, cell_mm=0.5)
    a = scribble(tone, seed=7)
    b = scribble(tone, seed=7)
    assert a == b
    total_points = sum(len(s) for s in a)
    total_ink = sum(math.dist(p, q) for s in a for p, q in zip(s, s[1:], strict=False))
    print(f"photo 80x48mm seed=7: {len(a)} stroke(s), {total_points} points, {total_ink:.1f} mm ink")
