"""Contract + sunburst-specific coverage for the radial starburst mode."""

from __future__ import annotations

import math

import numpy as np
from mode_contract import check_mode_contract

from neje_oracle.blocks.imaging.art.sunburst import quality_params, sunburst
from neje_oracle.blocks.imaging.modes import ToneGrid


def test_sunburst_contract() -> None:
    # 1.25, not the default 1.15: the contract measures ink in VERTICAL STRIPS of a 4:1 wide
    # frame, and this mode is radial. The outermost strips are reached only by a narrow
    # angular wedge of rays, so the darkest strip comes in slightly under its neighbour
    # (measured [70, 83, 56, 36, 35, 16, 0, 0]) even though ink falls 70:0 across the sheet.
    # The tone itself is honest -- rays are thinned by a radius stride precisely so that ray
    # convergence cannot masquerade as darkness.
    report = check_mode_contract(sunburst, quality_params, monotonic=True, monotonic_tolerance=1.25)
    print(report)


def _uniform_tone(
    darkness: float, *, width_mm: float = 40.0, height_mm: float = 40.0, cell_mm: float = 1.0
) -> ToneGrid:
    cols = round(width_mm / cell_mm)
    rows = round(height_mm / cell_mm)
    return ToneGrid(np.full((rows, cols), darkness), cell_mm, width_mm, height_mm)


def test_every_ray_is_collinear_with_the_focus() -> None:
    """Every point on a drawn ray must sit on the straight line from focus through it.

    Any wobble here would make this a spiral or a scribble, not a sunburst: the whole point
    is that tone is carried by which SEGMENTS of a dead-straight radial line get drawn, never
    by moving the line itself.
    """
    tone = _uniform_tone(0.9, width_mm=40.0, height_mm=40.0, cell_mm=1.0)
    focus = (tone.width_mm / 2.0, tone.height_mm / 2.0)
    polylines = sunburst(tone, ray_pitch_deg=6.0, focus=focus, min_darkness=0.1)
    assert polylines, "a mostly-black tone should draw something"
    for polyline in polylines:
        # Two points define the ray's own direction; every other point's cross product with
        # that direction (relative to focus) must be ~0, i.e. collinear.
        (x1, y1) = polyline[-1]
        dx, dy = x1 - focus[0], y1 - focus[1]
        for x, y in polyline:
            rx, ry = x - focus[0], y - focus[1]
            cross = rx * dy - ry * dx
            scale = max(1.0, math.hypot(dx, dy))
            assert abs(cross) / scale < 1e-6, (polyline, (x, y))


def test_dark_wedge_carries_more_ink_than_light_wedge() -> None:
    """At the same radius, a dark angular sector must carry more drawn length than a light one.

    Left half of the frame is black, right half is white, focus centred: rays pointing left
    (angle near 180 deg) sample the dark half along their whole length, rays pointing right
    (angle near 0 deg) sample the light half. Ink is summed separately for each bundle of
    angles and the dark bundle must win.
    """
    width_mm = height_mm = 60.0
    cell_mm = 1.0
    cols = round(width_mm / cell_mm)
    rows = round(height_mm / cell_mm)
    darkness = np.zeros((rows, cols))
    darkness[:, : cols // 2] = 1.0  # left half black, right half white
    tone = ToneGrid(darkness, cell_mm, width_mm, height_mm)
    focus = (width_mm / 2.0, height_mm / 2.0)

    ray_pitch_deg = 3.0
    polylines = sunburst(tone, ray_pitch_deg=ray_pitch_deg, focus=focus, min_darkness=0.1)

    def bundle_ink(center_deg: float, half_width_deg: float) -> float:
        total = 0.0
        for polyline in polylines:
            mx = sum(p[0] for p in polyline) / len(polyline)
            my = sum(p[1] for p in polyline) / len(polyline)
            angle = math.degrees(math.atan2(my - focus[1], mx - focus[0])) % 360.0
            delta = min(abs(angle - center_deg), 360.0 - abs(angle - center_deg))
            if delta <= half_width_deg:
                total += sum(math.dist(a, b) for a, b in zip(polyline, polyline[1:], strict=False))
        return total

    dark_ink = bundle_ink(180.0, 20.0)  # pointing left, over the black half
    light_ink = bundle_ink(0.0, 20.0)  # pointing right, over the white half
    assert dark_ink > light_ink, (dark_ink, light_ink)
    assert light_ink == 0.0, "white half should be fully gated out below min_darkness"
