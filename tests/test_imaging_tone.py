"""Tone modes must respect form, spacing, and colour while minimising unnecessary strokes.

Flow, crosshatch, and dither each answer "how to render tone?" but differ in mechanism.
Flow follows isolines of brightness like shading on a sphere — it reads as form, not a flat
render. Crosshatch works on a fixed grid; stitching is the way to avoid 100k pen lifts.
Dither halftones; chaining cuts the stroke count dramatically by bridging nearby dots.

All must leave white paper white (no ink) and preserve geometric properties like minimum
spacing and stroke layout under reasonable parameter variation.
"""

from __future__ import annotations

import io
import math

import numpy as np
import pytest
from PIL import Image

from neje_oracle.blocks.imaging.modes import (
    MODES,
    ToneGrid,
    crosshatch,
    dither,
    flow,
    halftone,
    hatch,
    load_tone,
    travel_length_mm,
)

WIDTH_MM = 80.0
HEIGHT_MM = 80.0
TONE_CELL_MM = 0.2  # 400 cells across 80 mm, targeting ~300 px for speed


def _to_png(image: Image.Image) -> bytes:
    """Encode PIL image as PNG bytes."""
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _shaded_sphere(size: int = 300) -> bytes:
    """A lit sphere over a graded backdrop, with a soft cast shadow.

    Tone varies continuously across the whole frame on purpose. An earlier version put a
    small sphere on a uniform grey field, which made 80% of the cells share one darkness
    value -- every quantile collapsed onto it and any density measurement compared the
    background against itself.
    """
    grid_y, grid_x = np.mgrid[0:size, 0:size].astype(np.float64)
    image = 0.25 + 0.5 * (grid_y / size)
    centre_x, centre_y, radius = size * 0.5, size * 0.46, size * 0.30
    inside = np.hypot(grid_x - centre_x, grid_y - centre_y) < radius

    height = np.sqrt(np.clip(radius**2 - (grid_x - centre_x) ** 2 - (grid_y - centre_y) ** 2, 0, None)) / radius
    lambert = np.clip(0.55 * -(grid_x - centre_x) / radius + 0.62 * -(grid_y - centre_y) / radius + 0.56 * height, 0, 1)
    image[inside] = 0.06 + 0.94 * lambert[inside] ** 1.4
    shadow = np.exp(
        -(
            ((grid_x - centre_x * 1.06) / (radius * 1.15)) ** 2
            + ((grid_y - centre_y - radius * 0.98) / (radius * 0.22)) ** 2
        )
    )
    image = np.clip(image - 0.45 * shadow, 0, 1)
    return _to_png(Image.fromarray((image * 255).astype(np.uint8), mode="L"))


def _flat_field(size: int = 300, grey: int = 128) -> bytes:
    """A uniform mid-grey image with no gradient anywhere."""
    image = Image.new("L", (size, size), grey)
    return _to_png(image)


def _vertical_gradient(size: int = 300) -> bytes:
    """A top-to-bottom gradient from white (top) to dark (bottom)."""
    image = Image.new("L", (size, size))
    pixels = image.load()
    for y in range(size):
        grey = int(255 * (1.0 - y / size))
        for x in range(size):
            pixels[x, y] = grey
    return _to_png(image)


def _white_image(size: int = 300) -> bytes:
    """A pure white image (255 everywhere)."""
    image = Image.new("L", (size, size), 255)
    return _to_png(image)


def _load_tone_from_png(data: bytes) -> ToneGrid:
    """Helper to load a tone grid from PNG bytes with fixed dimensions."""
    return load_tone(data, width_mm=WIDTH_MM, height_mm=HEIGHT_MM, cell_mm=TONE_CELL_MM)


def _direction_angle(polyline: list[tuple[float, float]]) -> float:
    """Compute the overall direction angle (in radians) of a polyline.

    Uses the vector from the first to last point to represent the polyline's general direction.
    Returns angle in range [0, pi) for simplicity.
    """
    if len(polyline) < 2:
        return 0.0
    x0, y0 = polyline[0]
    x1, y1 = polyline[-1]
    angle = math.atan2(y1 - y0, x1 - x0)
    # Normalize to [0, pi) so parallel lines have the same angle modulo pi
    return angle % math.pi


def _direction_spread(polylines: list[list[tuple[float, float]]]) -> float:
    """Compute the spread (standard deviation) of direction angles across polylines.

    Used to check that polylines are roughly parallel.
    """
    if len(polylines) < 2:
        return 0.0
    angles = [_direction_angle(p) for p in polylines if len(p) > 1]
    if len(angles) < 2:
        return 0.0
    # Convert angles to unit vectors, average, and compute spread
    cos_angles = [math.cos(a) for a in angles]
    sin_angles = [math.sin(a) for a in angles]
    mean_cos = sum(cos_angles) / len(cos_angles)
    mean_sin = sum(sin_angles) / len(sin_angles)
    mean_magnitude = math.sqrt(mean_cos**2 + mean_sin**2)
    # Spread is 1 - mean_magnitude (0 = all parallel, 1 = random)
    return 1.0 - mean_magnitude


def test_flow_leaves_highlights_as_paper() -> None:
    """Ink must follow darkness: the lit side stays paper, the terminator fills in.

    This is the defining property of flow — it should read as a lit form rather than an
    even field. The regions are taken from the tone grid itself rather than from guessed
    circles, so the test cannot drift out of step with the fixture: an earlier version
    hardcoded two circles that no longer matched the sphere and measured mostly background.
    """
    data = _shaded_sphere()
    tone = _load_tone_from_png(data)
    polylines = flow(tone)
    assert polylines, "flow produced nothing on a shaded sphere"

    darkness = tone.darkness
    light_cut = float(np.quantile(darkness, 0.25))
    dark_cut = float(np.quantile(darkness, 0.75))

    lightest = darkness <= light_cut
    darkest = darkness >= dark_cut
    light_ink = dark_ink = 0
    for line in polylines:
        for x, y in line:
            row = min(max(int(y / tone.cell_mm), 0), darkness.shape[0] - 1)
            column = min(max(int(x / tone.cell_mm), 0), darkness.shape[1] - 1)
            if lightest[row, column]:
                light_ink += 1
            elif darkest[row, column]:
                dark_ink += 1

    # Per unit area, so the comparison is a density and not an artefact of region size.
    light_density = light_ink / max(int(lightest.sum()), 1)
    dark_density = dark_ink / max(int(darkest.sum()), 1)
    # Measured 1.99x at the defaults and 2.46x at the shipped `max` preset. It is not the
    # 5x the spacing range alone implies: points sit step_mm apart along every line whatever
    # its spacing, and the white point still admits light mid-tones at the widest spacing.
    # The bar is set below the measured floor so the test fails on an inversion or a
    # collapse, not on ordinary retuning of the spacing tables.
    assert dark_density > light_density * 1.6, (
        f"ink does not follow darkness: {dark_density:.4f} per dark cell vs {light_density:.4f} per light cell"
    )


def test_flow_respects_its_spacing() -> None:
    """Flow must not place points closer than its min_spacing_mm * safety_factor.

    This guards against a collapsed occupancy check scribbling over itself, creating
    visible artifacts. We sample every 3rd point for speed; the test is on real content.
    """
    data = _shaded_sphere()
    tone = _load_tone_from_png(data)
    polylines = flow(tone, min_spacing_mm=0.6)

    if len(polylines) < 2:
        pytest.skip("fewer than 2 polylines; spacing check is vacuous")

    # Sample points from different polylines (every 3rd point for speed)
    sampled_points = []
    for line_idx, line in enumerate(polylines):
        sampled_points.extend([(x, y, line_idx) for i, (x, y) in enumerate(line) if i % 3 == 0])

    if len(sampled_points) < 10:
        pytest.skip("too few sampled points to check spacing")

    # Check nearest-neighbor distances between points from different polylines
    min_allowed = 0.6 * 0.5  # min_spacing_mm * safety_factor
    violations = 0
    for i, (x1, y1, lid1) in enumerate(sampled_points):
        for x2, y2, lid2 in sampled_points[i + 1 :]:
            if lid1 != lid2:  # only check across different polylines
                dist = math.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2)
                if dist < min_allowed:
                    violations += 1

    violation_rate = violations / max(len(sampled_points), 1)
    assert violation_rate < 0.05, f"{violation_rate:.1%} of point pairs violate spacing ({min_allowed} mm)"


def test_flow_handles_a_flat_field() -> None:
    """Flow on a uniform field (no gradient) should return non-empty result with parallel lines.

    This guards the fallback direction when the computed gradient is zero everywhere.
    """
    data = _flat_field()
    tone = _load_tone_from_png(data)
    polylines = flow(tone)

    assert len(polylines) > 0, "flow returned empty list on flat field"
    assert sum(len(line) for line in polylines) > 10, "flat field should produce many points"

    # Check that lines are roughly parallel (direction spread should be small)
    spread = _direction_spread(polylines)
    assert spread < 0.3, f"lines not parallel enough on flat field (spread={spread:.2f}; <0.3 expected)"


def test_dot_chaining_cuts_pen_lifts() -> None:
    """Chaining dots via chain_gap_mm should reduce polyline count dramatically.

    Measured on real content: vertical gradient through dither went from 12330 (chain_gap=0)
    to 1889 strokes (chain_gap~1.6) — a 6.5x reduction. We assert at least 4x here to
    be conservative and allow for parameter variation.
    """
    data = _vertical_gradient()
    tone = _load_tone_from_png(data)

    unchained = dither(tone, chain_gap_mm=0.0)
    chained = dither(tone, chain_gap_mm=1.6)

    unchained_count = len(unchained)
    chained_count = len(chained)

    assert unchained_count > 10, "unchained dither should produce many strokes"
    assert chained_count < unchained_count / 4.0, (
        f"chaining did not cut enough strokes: {unchained_count} -> {chained_count} (needed {unchained_count / 4:.0f})"
    )


def test_dot_chaining_keeps_each_chain_on_one_row() -> None:
    """A chain must join dots along a row, not zigzag between two.

    Stroke-count assertions cannot see this: the original bug recovered the row index as
    round(centre_y / step_y), which is round(row + 0.5), and banker's rounding sent rows 1
    and 2 both to 2. Adjacent rows merged, so most chains zigzagged between two rows and
    the serpentine direction alternated over merged buckets instead of real rows. The
    number of polylines barely moved, which is why only a geometric check catches it.
    """
    tone = _load_tone_from_png(_vertical_gradient())
    chained = dither(tone, chain_gap_mm=1.6)
    multi_point = [line for line in chained if len(line) >= 2]
    assert multi_point, "no chains were produced, so this assertion would be vacuous"

    row_height = tone.height_mm / tone.darkness.shape[0]
    spreads = [max(y for _, y in line) - min(y for _, y in line) for line in multi_point]
    straying = sum(1 for spread in spreads if spread > row_height * 0.5)
    assert straying == 0, f"{straying} of {len(multi_point)} chains span more than one row"


def test_dot_chaining_defaults_to_unchanged_behaviour() -> None:
    """Calling dither with default chain_gap_mm should match chain_gap_mm=0.0 exactly.

    Existing callers must not shift. This guards against accidental regression if the default
    ever changes.
    """
    data = _vertical_gradient()
    tone = _load_tone_from_png(data)

    default = dither(tone)
    explicit_zero = dither(tone, chain_gap_mm=0.0)

    assert default == explicit_zero, "dither default does not match chain_gap_mm=0.0"


def test_crosshatch_stitching_reduces_strokes_without_losing_ink() -> None:
    """Stitching short line segments into longer chains should reduce polyline count.

    Total drawing distance (penned + travel) must not grow more than 15% despite bridging gaps.
    Too much growth means the stitcher is inventing ink rather than just joining close segments.
    """
    data = _shaded_sphere()
    tone = _load_tone_from_png(data)

    unstitched = crosshatch(tone, stitch_mm=0.0)
    stitched = crosshatch(tone, stitch_mm=1.2)

    unstitched_count = len(unstitched)
    stitched_count = len(stitched)

    assert unstitched_count > 10, "unstitched crosshatch should produce many lines"
    assert stitched_count < unstitched_count * 0.9, (
        f"stitching did not reduce polylines enough: {unstitched_count} -> {stitched_count}"
    )

    # Measure total travel distance; stitching may bridge gaps but should not invent much ink
    unstitched_draw, unstitched_travel = travel_length_mm(unstitched)
    stitched_draw, stitched_travel = travel_length_mm(stitched)

    unstitched_total = unstitched_draw + unstitched_travel
    stitched_total = stitched_draw + stitched_travel

    growth = (stitched_total - unstitched_total) / max(unstitched_total, 1e-9)
    assert growth <= 0.15, f"stitching grew total distance by {growth:.1%} (max 15%)"


def test_tone_modes_leave_white_paper_white() -> None:
    """Pure white input should produce no ink output across all tone modes.

    This is a baseline: the modes should never invent strokes on paper.
    """
    data = _white_image()
    tone = _load_tone_from_png(data)

    # Driven off the registry rather than a hand-written list: this test is the reason a new
    # mode cannot quietly start inking blank paper, and a list would have to be remembered.
    # spiral is the case that makes it matter — an Archimedean spiral wants to run edge to
    # edge, and only the darkness gate stops it laying its baseline across empty paper.
    for name, mode in MODES.items():
        assert mode(tone) == [], f"{name} produced ink on white paper"


def test_halftone_leaves_near_white_paper_blank_at_a_coarse_pitch() -> None:
    """Pure white is not the case that failed. Nearly-white is.

    halftone's only tone gate used to be min_ink_mm, a size floor. Expressed in darkness that
    is (min_ink_mm / (cell_mm/2))**2, which weakens as the dot pitch grows: at the shipped
    3 mm pitch it is 1% darkness, so every faintly-grey cell earned a dot and the printed
    sheet came out as a full lattice with the subject only slightly denser inside it.
    """
    faint = np.full((64, 64), 0.04)
    faint[40:, :] = 0.9  # a genuinely dark band that must survive the gate
    tone = ToneGrid(faint, cell_mm=3.0, width_mm=60.0, height_mm=60.0)

    ungated = halftone(tone, pen_width_mm=0.5)
    gated = halftone(tone, pen_width_mm=0.5, min_darkness=0.18)

    assert len(gated) < len(ungated) * 0.6, (
        f"the white point barely filtered anything: {len(ungated)} -> {len(gated)} dots"
    )
    assert gated, "the white point ate the dark band too"
    # Every surviving dot must sit in the dark band, not on the faint background.
    assert all(min(y for _, y in dot) >= 30.0 for dot in gated), "a dot landed on near-white paper"


def test_hatch_smoothing_buys_longer_strokes_for_the_same_ink() -> None:
    """Tone that jitters cell to cell shatters every scanline into crumbs.

    A run breaks wherever a sample dips under that line's threshold, so a resampled photo
    produces confetti: measured on a real drawing, 63 strokes of median 2.1 mm carrying the
    same 158 mm of ink that 23 strokes of median 4.2 mm carry once the field is smoothed.
    Strokes are pen lifts, so this is the rare change that is faster AND more legible.
    """
    rng = np.random.default_rng(11)
    gradient = np.linspace(0.9, 0.25, 64)[None, :].repeat(64, axis=0)
    speckled = np.clip(gradient + rng.normal(0, 0.12, (64, 64)), 0, 1)
    tone = ToneGrid(speckled, cell_mm=1.0, width_mm=64.0, height_mm=64.0)

    def measure(polylines: list[list[tuple[float, float]]]) -> tuple[int, float, float]:
        lengths = [
            sum(math.dist(a, b) for a, b in zip(line, line[1:], strict=False)) for line in polylines
        ]
        return len(polylines), sum(lengths), sorted(lengths)[len(lengths) // 2]

    raw_count, raw_ink, raw_median = measure(hatch(tone, line_spacing_mm=1.6, blur_px=0.0))
    smooth_count, smooth_ink, smooth_median = measure(hatch(tone, line_spacing_mm=1.6, blur_px=2.0))

    assert smooth_count < raw_count * 0.7, f"smoothing did not consolidate strokes: {raw_count} -> {smooth_count}"
    assert smooth_median > raw_median * 1.5, f"strokes did not get longer: {raw_median:.2f} -> {smooth_median:.2f}"
    # The ink is the tone. Consolidating strokes must not quietly lighten the image.
    assert smooth_ink >= raw_ink * 0.75, f"smoothing lost {100 * (1 - smooth_ink / raw_ink):.0f}% of the ink"
