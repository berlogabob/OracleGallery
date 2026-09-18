"""The contract every imaging mode must meet, as one callable check.

Not collected by pytest (no test_ prefix). A new mode's own test file calls
check_mode_contract(fn, quality_params) so the mode is held to the same rules the registry-wide
tests in test_imaging_modes.py and test_gui_workspaces.py apply once it is registered -- before
it is registered, which is when the author can still cheaply fix it.
"""

from __future__ import annotations

import io
import math
import time
from collections.abc import Callable
from typing import Any

import numpy as np
from PIL import Image, ImageDraw

from neje_oracle.blocks.imaging.modes import ToneGrid, load_tone

# The quality fader's ladders (gui/workspaces/image.py), draft -> max. A mode's quality_params
# receives the spacing; the tone grid uses the cell size; the result must fit the segment cap.
SPACING_MM = (2.5, 2.0, 1.6, 1.2, 1.0)
TONE_CELL_MM = (1.5, 1.0, 0.7, 0.5, 0.4)
MAX_SEGMENTS = (40_000, 60_000, 90_000, 240_000, 640_000)


def _png(image: Image.Image) -> bytes:
    output = io.BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def _tone(image: Image.Image, width_mm: float, height_mm: float, cell_mm: float) -> ToneGrid:
    return load_tone(_png(image), width_mm=width_mm, height_mm=height_mm, cell_mm=cell_mm)


def _drawn(polylines: Any) -> list[list[tuple[float, float]]]:
    return [list(polyline) for polyline in polylines if len(polyline) >= 2]


def _ink_mm(polylines: Any) -> float:
    return sum(math.dist(p[i], p[i + 1]) for p in _drawn(polylines) for i in range(len(p) - 1))


def _segments(polylines: Any) -> int:
    return sum(len(p) - 1 for p in _drawn(polylines))


def dense_line_art() -> Image.Image:
    """The busy 1024 px drawing test_gui_workspaces uses to reach the segment caps."""
    image = Image.new("L", (1024, 1024), 255)
    draw = ImageDraw.Draw(image)
    draw.rectangle([60, 80, 960, 700], outline=0, width=8)
    draw.ellipse([180, 160, 840, 620], outline=0, width=3)
    for x in range(80, 950, 9):
        draw.line([x, 90, x + 40, 690], fill=0, width=1)
    for y in range(720, 1000, 7):
        draw.line([70, y, 950, y + 12], fill=0, width=1)
    return image


def photo_like() -> Image.Image:
    """Smooth blobs plus hard edges, non-square: what a real photo exercises."""
    y, x = np.mgrid[0:120, 0:200].astype(float)
    field = 128 + 90 * np.sin(x / 17.0) * np.cos(y / 13.0)
    field[40:80, 60:140] = 20
    return Image.fromarray(np.clip(field, 0, 255).astype(np.uint8), mode="L")


def bucket_ink(polylines: Any, width_mm: float, buckets: int = 8) -> list[float]:
    """Drawn length per vertical strip, split exactly at strip boundaries."""
    out = [0.0] * buckets
    step = width_mm / buckets
    for polyline in _drawn(polylines):
        for start, end in zip(polyline, polyline[1:], strict=False):
            length = math.dist(start, end)
            if length == 0:
                continue
            cuts = [0.0, 1.0]
            if start[0] != end[0]:
                for k in range(1, buckets):
                    t = (k * step - start[0]) / (end[0] - start[0])
                    if 0 < t < 1:
                        cuts.append(t)
            cuts.sort()
            for a, b in zip(cuts, cuts[1:], strict=False):
                mid = start[0] + (end[0] - start[0]) * (a + b) / 2
                out[min(buckets - 1, max(0, int(mid / step)))] += length * (b - a)
    return out


def check_mode_contract(
    fn: Callable[..., Any],
    quality_params: Callable[[float], dict[str, Any]],
    *,
    monotonic: bool = True,
    solid_ink: bool = True,
    monotonic_tolerance: float = 1.15,
    perf_budget_s: float = 30.0,
) -> dict[str, Any]:
    """Assert the mode contract; returns measurements for the caller to print.

    1. White paper draws nothing. Every mode is gated, or it inks every margin.
    2. Black draws something (solid_ink=False for outline modes: a flat field has no edge).
       Tone modes (monotonic=True): light grey draws less than black, but not nothing.
    3. Every point stays inside the frame, on a non-square picture.
    4. Same input, same output: seeded, never time- or hash-dependent.
    5. Monotonic (tone modes): a left-dark-to-right-light gradient lays more ink on the left,
       and no strip holds more than `monotonic_tolerance` x its darker neighbour.
    6. Every quality step fits its segment cap on the dense 150 mm drawing.
    7. A 200 mm gradient at cell 1 renders inside the perf budget.
    """
    report: dict[str, Any] = {}

    white = _tone(Image.new("L", (64, 64), 255), 64.0, 64.0, 1.0)
    assert _drawn(fn(white)) == [], "white paper must draw nothing"

    black = _tone(Image.new("L", (64, 64), 0), 64.0, 64.0, 1.0)
    report["black_ink_mm"] = _ink_mm(fn(black))
    assert report["black_ink_mm"] > 0 or not solid_ink, "solid black must draw something"
    if monotonic:
        # Light grey, well above the usual 0.05 gate: tsp once cut every neighbour pair here
        # and drew nothing, which none of the black, white or gradient checks noticed.
        light = _tone(Image.new("L", (64, 64), 215), 64.0, 64.0, 1.0)
        report["light_grey_ink_mm"] = _ink_mm(fn(light))
        assert 0 < report["light_grey_ink_mm"] < report["black_ink_mm"], (
            "light grey must draw less than black, but not nothing"
        )

    photo = _tone(photo_like(), 80.0, 48.0, 0.5)
    first = fn(photo)
    for polyline in _drawn(first):
        for x, y in polyline:
            assert -1e-6 <= x <= 80.0 + 1e-6 and -1e-6 <= y <= 48.0 + 1e-6, f"point {(x, y)} outside 80x48"
    assert fn(photo) == first, "same input must give the same output"
    report["photo_strokes"] = len(_drawn(first))

    if monotonic:
        gradient = np.tile(np.arange(256, dtype=np.uint8), (64, 1))
        tone = _tone(Image.fromarray(gradient, mode="L"), 80.0, 20.0, 1.0)
        buckets = bucket_ink(fn(tone), 80.0)
        report["gradient_buckets"] = [round(b) for b in buckets]
        assert buckets[0] > buckets[-1], ("darker side must carry more ink", buckets)
        for left, right in zip(buckets, buckets[1:], strict=False):
            assert right <= left * monotonic_tolerance + 0.01, ("ink must not rise toward the light", buckets)

    dense = dense_line_art()
    report["dense_segments"] = []
    for spacing, cell, cap in zip(SPACING_MM, TONE_CELL_MM, MAX_SEGMENTS, strict=True):
        segments = _segments(fn(_tone(dense, 150.0, 150.0, cell), **quality_params(spacing)))
        report["dense_segments"].append(segments)
        assert segments <= cap, f"spacing {spacing} / cell {cell}: {segments} segments > cap {cap}"

    ramp = Image.fromarray(np.tile(np.arange(256, dtype=np.uint8), (1024, 4)), mode="L")
    started = time.perf_counter()
    fn(_tone(ramp, 200.0, 200.0, 1.0))
    report["perf_200mm_s"] = round(time.perf_counter() - started, 3)
    assert report["perf_200mm_s"] < perf_budget_s, report

    return report
