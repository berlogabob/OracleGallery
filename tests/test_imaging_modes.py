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
    travel_length_mm,
)


def _png(image: Image.Image) -> bytes:
    output = io.BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


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
    assert set(MODES) == {"halftone", "hatch", "dither", "contour"}


def test_solid_white_produces_no_ink() -> None:
    data = _png(Image.new("L", (64, 64), 255))
    for mode in MODES:
        assert image_to_polylines(data, mode=mode, width_mm=64, height_mm=64) == []


def test_monotonic_ink_vs_brightness() -> None:
    gradient = np.tile(np.arange(256, dtype=np.uint8), (64, 1))
    data = _png(Image.fromarray(gradient, mode="L"))
    tone = load_tone(data, width_mm=80, height_mm=20, cell_mm=1)
    for name, mode in MODES.items():
        if name == "halftone":
            polylines = mode(tone, angle_deg=0.0)
        elif name == "contour":
            polylines = mode(tone, bands=8)
        else:
            polylines = mode(tone)
        buckets = _bucket_draw_lengths(polylines, tone.width_mm)
        assert buckets[0] > buckets[-1], (name, buckets)
        assert all(right <= left * 1.15 + 0.01 for left, right in zip(buckets, buckets[1:], strict=False)), (
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


def test_conversion_under_two_seconds() -> None:
    gradient = np.tile(np.arange(256, dtype=np.uint8), (1024, 4))
    data = _png(Image.fromarray(gradient, mode="L"))
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
        assert timings[mode] < 2.0, timings
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
