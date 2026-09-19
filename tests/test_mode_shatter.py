"""Contract + shatter-specific coverage for the broken-glass crack mode."""

from __future__ import annotations

import math

import numpy as np
from mode_contract import check_mode_contract

from neje_oracle.blocks.imaging.art.shatter import quality_params, shatter
from neje_oracle.blocks.imaging.modes import ToneGrid


def test_shatter_contract() -> None:
    report = check_mode_contract(shatter, quality_params, monotonic=True)
    print(report)


def _uniform_tone(
    darkness: float, *, width_mm: float = 40.0, height_mm: float = 40.0, cell_mm: float = 1.0
) -> ToneGrid:
    cols = round(width_mm / cell_mm)
    rows = round(height_mm / cell_mm)
    return ToneGrid(np.full((rows, cols), darkness), cell_mm, width_mm, height_mm)


def _segments(polylines: list[list[tuple[float, float]]]) -> list[tuple[tuple[float, float], tuple[float, float]]]:
    out = []
    for polyline in polylines:
        for a, b in zip(polyline, polyline[1:], strict=False):
            if a != b:
                out.append((a, b))
    return out


def _properly_intersects(
    p: tuple[float, float], q: tuple[float, float], a: tuple[float, float], b: tuple[float, float], tol: float = 1e-7
) -> bool:
    """Independent segment-intersection check (no shared code with shatter.py's own).

    Excludes touches at either pair of shared endpoints, since a T-junction -- one segment's
    endpoint landing on another's endpoint or interior -- is exactly what this mode is
    supposed to produce; only a proper interior crossing (both t and u strictly inside (0,1),
    away from every endpoint of either segment) would mean two cracks visibly cross.
    """
    r = (q[0] - p[0], q[1] - p[1])
    s = (b[0] - a[0], b[1] - a[1])
    denom = r[0] * s[1] - r[1] * s[0]
    if abs(denom) < 1e-12:
        return False
    diff = (a[0] - p[0], a[1] - p[1])
    t = (diff[0] * s[1] - diff[1] * s[0]) / denom
    u = (diff[0] * r[1] - diff[1] * r[0]) / denom
    if not (tol < t < 1 - tol and tol < u < 1 - tol):
        return False
    point = (p[0] + t * r[0], p[1] + t * r[1])
    # A crossing that lands within tol of an ENDPOINT of either segment is a near-miss T-junction
    # (float slop), not a proper cross -- only flag ones clearly away from every endpoint.
    endpoints = (p, q, a, b)
    return all(math.dist(point, endpoint) > tol for endpoint in endpoints)


def test_cracks_stop_at_a_junction_instead_of_crossing() -> None:
    """No two emitted segments, across the whole drawing, properly cross one another.

    A dense-ish uniform-dark tile packs many cracks into a small frame, which is exactly the
    condition most likely to force a crossing if the termination geometry were wrong.
    """
    tone = _uniform_tone(0.9, width_mm=36.0, height_mm=36.0, cell_mm=0.5)
    polylines = shatter(tone, crack_spacing_mm=3.0, seed=7, max_cracks=400)
    segments = _segments(polylines)
    assert len(segments) > 20, "expected a reasonably dense crack field to test against"
    for i in range(len(segments)):
        p, q = segments[i]
        for j in range(i + 1, len(segments)):
            a, b = segments[j]
            assert not _properly_intersects(p, q, a, b), f"segments {segments[i]} and {segments[j]} properly cross"


def test_darker_region_carries_more_crack_length_per_area() -> None:
    """Left half black, right half near-white: ink density must be higher on the dark side.

    Uses ink LENGTH per unit AREA (not just total length) so the comparison is honest even
    though both halves are the same size here.
    """
    width_mm, height_mm, cell_mm = 40.0, 40.0, 0.5
    cols, rows = round(width_mm / cell_mm), round(height_mm / cell_mm)
    darkness = np.zeros((rows, cols))
    darkness[:, : cols // 2] = 0.95
    darkness[:, cols // 2 :] = 0.08
    tone = ToneGrid(darkness, cell_mm, width_mm, height_mm)

    polylines = shatter(tone, crack_spacing_mm=3.0, seed=3, max_cracks=2000)
    left_len = right_len = 0.0
    midpoint_x = width_mm / 2.0
    for polyline in polylines:
        for a, b in zip(polyline, polyline[1:], strict=False):
            length = math.dist(a, b)
            mid_x = (a[0] + b[0]) / 2.0
            if mid_x < midpoint_x:
                left_len += length
            else:
                right_len += length

    left_density = left_len / (width_mm / 2.0 * height_mm)
    right_density = right_len / (width_mm / 2.0 * height_mm)
    assert left_density > right_density, (left_density, right_density)
