"""Speckle and ink-coverage regressions, all of them found on paper rather than in CI.

Printing a clean AI-generated line drawing produced the artwork plus dozens of stray
millimetre-long dashes lying beside it, and a halftone ramp whose darkest region came out
lighter than its mid-tones. Neither is visible to a test that counts vertices, which is what
every filter in modes.py did before: `len(polyline) >= 2` cannot tell a 0.15 mm speck from a
150 mm stroke.
"""

from __future__ import annotations

import io
import math

import numpy as np
from PIL import Image, ImageDraw

from neje_oracle.blocks.imaging.modes import halftone, image_to_polylines, load_tone

PEN_MM = 0.5
FRAME_MM = 100.0


def _png(image: Image.Image) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _antialiased_line_art() -> bytes:
    """Line art carrying the grey edges and background grain a real source has.

    Drawn oversized and resampled down, so every stroke edge ends up part-grey and the
    resampler rings around it — the input that made the mask boundary ragged and fed
    Zhang-Suen spurs. The faint background grain matters just as much and is not decoration:
    load_tone runs autocontrast unconditionally, which lifts render/JPEG noise on white paper
    into real darkness, and contour then draws a closed loop around each lifted cell once per
    band. A pure-white background hides that half of the bug entirely.
    """
    big = Image.new("L", (2048, 2048), 255)
    draw = ImageDraw.Draw(big)
    for index in range(6):
        offset = 200 + index * 260
        draw.line((offset, 200, offset, 1848), fill=0, width=9)
        draw.line((200, offset, 1848, offset), fill=0, width=9)
    draw.ellipse((700, 700, 1400, 1400), outline=0, width=11)
    small = big.resize((512, 512), Image.Resampling.LANCZOS)
    grain = np.random.default_rng(7).integers(0, 26, size=(512, 512), dtype=np.int16)
    return _png(Image.fromarray(np.clip(np.asarray(small, dtype=np.int16) - grain, 0, 255).astype(np.uint8)))


def _convert(mode: str, *, min_stroke_mm: float, **params: object) -> list[list[tuple[float, float]]]:
    return image_to_polylines(
        _antialiased_line_art(),
        mode=mode,
        width_mm=FRAME_MM,
        height_mm=FRAME_MM,
        cell_mm=0.25,
        max_segments=2_000_000,
        min_stroke_mm=min_stroke_mm,
        **params,
    )


def _extent_mm(polyline: list[tuple[float, float]]) -> float:
    xs = [x for x, _ in polyline]
    ys = [y for _, y in polyline]
    return math.hypot(max(xs) - min(xs), max(ys) - min(ys))


def test_trace_leaves_no_stroke_the_pen_would_print_as_a_speck() -> None:
    filtered = _convert("trace", min_stroke_mm=PEN_MM * 2, pen_width_mm=PEN_MM)
    assert filtered, "the filter removed the drawing, not just the noise"
    smallest = min(_extent_mm(polyline) for polyline in filtered)
    assert smallest >= PEN_MM * 2, f"a {smallest:.2f} mm stroke survived; the pen draws that as a dot"


def test_contour_leaves_no_stroke_the_pen_would_print_as_a_speck() -> None:
    filtered = _convert("contour", min_stroke_mm=PEN_MM * 2)
    assert filtered
    smallest = min(_extent_mm(polyline) for polyline in filtered)
    assert smallest >= PEN_MM * 2, f"a {smallest:.2f} mm loop survived; contour bands one noisy cell into a dot"


def test_the_filter_removes_specks_rather_than_the_drawing() -> None:
    """Most of what it deletes must be strokes, and almost none of the ink."""
    for mode, params in (("trace", {"pen_width_mm": PEN_MM}), ("contour", {})):
        raw = _convert(mode, min_stroke_mm=0.0, **params)
        filtered = _convert(mode, min_stroke_mm=PEN_MM * 2, **params)
        assert len(filtered) < len(raw), f"{mode}: nothing was filtered, so the fixture has no speckle"

        def drawn(polylines: list[list[tuple[float, float]]]) -> float:
            return sum(math.dist(a, b) for polyline in polylines for a, b in zip(polyline, polyline[1:], strict=False))

        # Strokes are pen lifts and pen lifts dominate plot time, so the trade this filter
        # makes is only worth it if the ink stays and the lifts go.
        assert drawn(filtered) >= drawn(raw) * 0.9, f"{mode}: the filter ate real ink, not speckle"


def test_weight_passes_do_not_shed_fragments_beside_the_stroke() -> None:
    """The dashes seen on paper lay parallel to the artwork, one pen width off it.

    They came from _weight_passes cutting a run wherever the smoothed half-width dipped and
    emitting any two-point remainder as its own polyline.
    """
    with_weight = _convert("trace", min_stroke_mm=0.0, pen_width_mm=PEN_MM, weight_passes=True)
    without = _convert("trace", min_stroke_mm=0.0, pen_width_mm=PEN_MM, weight_passes=False)
    extra = len(with_weight) - len(without)
    assert extra <= len(without), f"weight passes more than doubled the stroke count ({without} -> {with_weight})"


def test_halftone_dots_are_inked_in_the_middle() -> None:
    """A dot drawn as its outline is a donut once it is wider than the nib.

    On the printed ramp this inverted the tone curve: the darkest region read lighter than the
    mid-tones, because every dot there was a ring around bare paper. Nothing caught it,
    because a ring's circumference still grows with darkness — only its coverage does not.
    """
    tone = load_tone(_png(Image.new("L", (64, 64), 0)), width_mm=60, height_mm=60, cell_mm=4.0)

    hollow = halftone(tone)
    worst_hollow = max(min(math.dist(_centroid(dot), point) for point in dot) for dot in hollow)
    assert worst_hollow > PEN_MM, "fixture is too coarse to show the donut this test guards against"

    filled = halftone(tone, pen_width_mm=PEN_MM)
    assert len(filled) == len(hollow), "filling must not change the dot count, only each dot's interior"
    worst_filled = max(min(math.dist(_centroid(dot), point) for point in dot) for dot in filled)
    assert worst_filled <= PEN_MM, f"a dot centre sat {worst_filled:.2f} mm from any ink; it prints as a ring"


def test_filled_dots_cost_no_extra_pen_lifts() -> None:
    """The fill is one continuous spiral per dot, so it buys coverage without buying lifts."""
    tone = load_tone(_png(Image.new("L", (64, 64), 0)), width_mm=60, height_mm=60, cell_mm=4.0)
    assert len(halftone(tone, pen_width_mm=PEN_MM)) == len(halftone(tone))


def _centroid(polyline: list[tuple[float, float]]) -> tuple[float, float]:
    return (
        sum(x for x, _ in polyline) / len(polyline),
        sum(y for _, y in polyline) / len(polyline),
    )
