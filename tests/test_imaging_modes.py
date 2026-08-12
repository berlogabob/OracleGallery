from __future__ import annotations

import io
import math
import time
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from neje_oracle.blocks.gcode.svg_gcode import generate_absolute_svg_gcode
from neje_oracle.blocks.imaging.modes import (
    MODES,
    hatch,
    image_to_polylines,
    image_to_svg,
    load_tone,
    order_serpentine,
    polylines_to_svg,
    tone_to_polylines,
    travel_length_mm,
    travel_preview_svg,
)


def _png(image: Image.Image) -> bytes:
    output = io.BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


@pytest.mark.parametrize("mode", ["hatch", "contour"])
def test_tone_to_polylines_matches_image_to_polylines(mode):
    """image_to_polylines is now load_tone + tone_to_polylines. Same tone in, same strokes out --
    proves the split is behaviour-preserving rather than merely compiling."""
    gradient = np.tile(np.linspace(0, 255, 60, dtype=np.uint8), (60, 1))
    data = _png(Image.fromarray(gradient, mode="L"))
    tone = load_tone(data, width_mm=60.0, height_mm=60.0, cell_mm=1.0)
    assert tone_to_polylines(tone, mode=mode) == image_to_polylines(
        data, mode=mode, width_mm=60.0, height_mm=60.0, cell_mm=1.0
    )


def test_unknown_mode_is_reported_before_the_image_is_read():
    """The guard must stay in front of load_tone: a typo'd mode with an unreadable payload should
    say which is wrong, not blame the bytes."""
    with pytest.raises(ValueError, match="unknown mode"):
        image_to_polylines(b"not an image", mode="nope", width_mm=10.0, height_mm=10.0)


def _bucket_draw_lengths(polylines: list[list[tuple[float, float]]], width_mm: float) -> list[float]:
    buckets = [0.0] * 8
    bucket_width = width_mm / len(buckets)
    boundaries = [bucket_width * index for index in range(1, len(buckets))]
    for polyline in polylines:
        for start, end in zip(polyline, polyline[1:], strict=False):
            length = math.dist(start, end)
            if length == 0:
                continue
            parameters = [0.0, 1.0]
            if start[0] != end[0]:
                parameters.extend(
                    (boundary - start[0]) / (end[0] - start[0])
                    for boundary in boundaries
                    if 0 < (boundary - start[0]) / (end[0] - start[0]) < 1
                )
            parameters.sort()
            for first, second in zip(parameters, parameters[1:], strict=False):
                midpoint = start[0] + (end[0] - start[0]) * (first + second) / 2
                bucket = min(7, max(0, int(midpoint / bucket_width)))
                buckets[bucket] += length * (second - first)
    return buckets


def test_all_modes_registered() -> None:
    assert set(MODES) == {
        "halftone",
        "hatch",
        "dither",
        "contour",
        "trace",
        "crosshatch",
        "flow",
        "spiral",
        "wave",
        "stipple",
        "squiggle",
    }


def test_solid_white_produces_no_ink() -> None:
    data = _png(Image.new("L", (64, 64), 255))
    for mode in MODES:
        assert image_to_polylines(data, mode=mode, width_mm=64, height_mm=64) == []


def test_monotonic_ink_vs_brightness() -> None:
    """Ink density must fall as the image gets lighter — for the tone modes.

    trace is excluded on purpose, not because it fails: it is not a tone renderer. It
    follows strokes, and a smooth gradient has none, so "ink proportional to darkness" is
    not a property it is supposed to have. tests/test_imaging_trace.py covers it instead.
    """
    gradient = np.tile(np.arange(256, dtype=np.uint8), (64, 1))
    data = _png(Image.fromarray(gradient, mode="L"))
    tone = load_tone(data, width_mm=80, height_mm=20, cell_mm=1)
    for name, mode in MODES.items():
        if name == "trace":
            continue
        if name == "halftone":
            polylines = mode(tone, angle_deg=0.0)
        elif name == "contour":
            polylines = mode(tone, bands=8)
        else:
            polylines = mode(tone)
        buckets = _bucket_draw_lengths(polylines, tone.width_mm)
        assert buckets[0] > buckets[-1], (name, buckets)
        # flow gets a looser bar between adjacent buckets, not a free pass: the overall
        # fall is still asserted above. The scanline modes lay down a fine threshold ladder
        # and quantise smoothly, whereas flow places whole streamlines — at the light end
        # its spacing is ~3 mm, so a 10 mm bucket holds about three lines and one line
        # either way is a third of the bucket. That is placement granularity, not a break
        # in the density-from-darkness mapping.
        tolerance = 1.4 if name == "flow" else 1.15
        assert all(right <= left * tolerance + 0.01 for left, right in zip(buckets, buckets[1:], strict=False)), (
            name,
            buckets,
        )


def test_hatch_coverage_on_solid_black() -> None:
    data = _png(Image.new("L", (64, 64), 0))
    tone = load_tone(data, width_mm=100, height_mm=100, cell_mm=1)
    draw, _ = travel_length_mm(hatch(tone, line_spacing_mm=2.0, angle_deg=0.0))
    assert draw == pytest.approx(5_000, rel=0.05)


def test_gcode_roundtrip_all_modes(tmp_path: Path) -> None:
    y, x = np.indices((64, 64))
    pixels = ((17 * x + 31 * y + x * y) % 256).astype(np.uint8)
    data = _png(Image.fromarray(pixels, mode="L"))
    width_mm = 40.0
    height_mm = 30.0

    for mode in MODES:
        svg_path = tmp_path / f"{mode}.svg"
        svg_path.write_text(
            image_to_svg(
                data,
                mode=mode,
                width_mm=width_mm,
                height_mm=height_mm,
                cell_mm=1.0,
            )
        )
        gcode = generate_absolute_svg_gcode(
            svg_path,
            sample_step_mm=1.0,
            travel_rate=5_000.0,
            draw_rate=1_800.0,
            pen_up_command="M5",
            pen_down_command="M3 S15",
        )
        assert "G21" in gcode and "G90" in gcode
        assert "M3 S15" in gcode and "M5" in gcode
        for line in gcode.splitlines():
            if not line.startswith(("G0 X", "G1 X")):
                continue
            coordinates = {part[0]: float(part[1:]) for part in line.split()[1:]}
            assert -0.01 <= coordinates["X"] <= width_mm + 0.01
            assert -0.01 <= coordinates["Y"] <= height_mm + 0.01


def test_segment_cap_raises() -> None:
    y, x = np.indices((64, 64))
    data = _png(Image.fromarray(((x + y) % 2 * 255).astype(np.uint8), mode="L"))
    with pytest.raises(ValueError, match="max_segments"):
        image_to_polylines(
            data,
            mode="dither",
            width_mm=20,
            height_mm=20,
            cell_mm=0.25,
            max_segments=100,
        )


def test_halftone_at_gui_defaults_survives_a_dense_image() -> None:
    """The shipped defaults must render, not dead-end on the segment cap.

    cell_mm=1.5 used to be the default: 10 000 cells over a 150 mm frame, past the 40k
    cap before a single vertex was placed, so every real photo produced a blank preview.
    """
    noise = np.random.default_rng(0).integers(40, 200, size=(512, 512), dtype=np.uint8)
    data = _png(Image.fromarray(noise, mode="L"))
    polylines = image_to_polylines(data, mode="halftone", width_mm=150.0, height_mm=150.0, cell_mm=3.0)
    assert polylines


def test_travel_preview_is_screen_only_and_never_reaches_the_plotter() -> None:
    """The preview draws pen-up moves in red. If those leak into the print path the pen
    draws every one of them, so the two serializers must stay separate."""
    polylines = [[(0.0, 0.0), (10.0, 0.0)], [(30.0, 30.0), (40.0, 30.0)]]
    printed = polylines_to_svg(polylines, width_mm=50, height_mm=50)
    preview = travel_preview_svg(polylines, width_mm=50, height_mm=50)

    assert "<line" not in printed and "#c4623f" not in printed
    assert 'width="50mm" height="50mm"' in printed
    # One hop from the origin to stroke one, one from stroke one's end to stroke two.
    assert preview.count("<line") == 2
    assert preview.count("<polyline") == printed.count("<polyline")
    # A non-square frame must not be serialized as a square.
    assert 'width="40mm" height="90mm"' in travel_preview_svg(polylines, width_mm=40, height_mm=90)


def test_unknown_mode_raises() -> None:
    data = _png(Image.new("L", (1, 1), 255))
    with pytest.raises(ValueError) as error:
        image_to_polylines(data, mode="scribble", width_mm=10, height_mm=10, cell_mm=1)
    message = str(error.value)
    assert all(name in message for name in MODES)


def test_serpentine_reduces_travel() -> None:
    gradient = np.tile(np.arange(256, dtype=np.uint8), (128, 1))
    tone = load_tone(
        _png(Image.fromarray(gradient, mode="L")),
        width_mm=100,
        height_mm=100,
        cell_mm=1,
    )
    polylines = hatch(tone, line_spacing_mm=2.0, angle_deg=0.0)
    assert travel_length_mm(order_serpentine(polylines))[1] < travel_length_mm(polylines)[1]


def test_conversion_does_not_become_pathologically_slow() -> None:
    """Guard against an accidentally quadratic rewrite, not a benchmark.

    A tight wall-clock bound is the wrong instrument here: this ran in 0.3s on a
    dev laptop and 3.1s on a shared CI runner under `coverage`, whose tracing
    inflates pure-Python loops several-fold. That flakiness teaches people to
    ignore CI, which costs more than the test is worth.

    The budget is therefore generous — it still catches the regression that
    matters (an O(n^2) rewrite is orders of magnitude, not a factor of two) while
    tolerating slow, instrumented, contended hardware.
    """
    gradient = np.tile(np.arange(256, dtype=np.uint8), (1024, 4))
    data = _png(Image.fromarray(gradient, mode="L"))
    budget_seconds = 30.0
    timings = {}
    for mode in MODES:
        started = time.perf_counter()
        image_to_polylines(
            data,
            mode=mode,
            width_mm=200,
            height_mm=200,
            cell_mm=1,
            max_segments=2_000_000,
        )
        timings[mode] = time.perf_counter() - started
        assert timings[mode] < budget_seconds, timings
    print("timings:", ", ".join(f"{mode}={value:.3f}s" for mode, value in timings.items()))


def _uniform(value: int, size: int = 128) -> bytes:
    return _png(Image.new("L", (size, size), value))


def test_halftone_covers_rotated_field() -> None:
    """A rotated lattice must still reach the sheet corners, not leave an octagon."""
    polylines = image_to_polylines(
        _uniform(128),
        mode="halftone",
        width_mm=100.0,
        height_mm=100.0,
        cell_mm=2.0,
        angle_deg=45.0,
        max_segments=200_000,
    )
    points = [point for polyline in polylines for point in polyline]
    assert points
    corners = {"tl": False, "tr": False, "bl": False, "br": False}
    for x, y in points:
        if x < 15 and y < 15:
            corners["tl"] = True
        elif x > 85 and y < 15:
            corners["tr"] = True
        elif x < 15 and y > 85:
            corners["bl"] = True
        elif x > 85 and y > 85:
            corners["br"] = True
    assert all(corners.values()), f"rotated halftone left corners bare: {corners}"


def test_hatch_midtone_is_not_solid() -> None:
    """Tone must come from line density; a fixed threshold makes every photo solid."""

    def draw_mm(value: int) -> float:
        polylines = image_to_polylines(
            _uniform(value),
            mode="hatch",
            width_mm=100.0,
            height_mm=100.0,
            cell_mm=0.5,
            line_spacing_mm=1.5,
        )
        return travel_length_mm(polylines)[0]

    black, mid, light = draw_mm(0), draw_mm(128), draw_mm(210)
    assert black > 0
    assert mid < black * 0.8, f"midtone {mid:.0f}mm vs black {black:.0f}mm — no shading"
    assert light < mid, f"light {light:.0f}mm not lighter than mid {mid:.0f}mm"
