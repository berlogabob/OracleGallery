"""Contract + ripple-specific coverage for the water-rings mode."""

from __future__ import annotations

import math

import numpy as np
from mode_contract import check_mode_contract

from neje_oracle.blocks.imaging.art.ripple import quality_params, ripple
from neje_oracle.blocks.imaging.modes import ToneGrid


def test_ripple_contract() -> None:
    report = check_mode_contract(ripple, quality_params, monotonic=True)
    print(report)


def _uniform_tone(darkness: float, *, size_mm: float = 40.0, cell_mm: float = 1.0) -> ToneGrid:
    cells = round(size_mm / cell_mm)
    return ToneGrid(np.full((cells, cells), darkness), cell_mm, size_mm, size_mm)


def test_rings_stay_clipped_inside_the_frame() -> None:
    """A ring near the frame's far corner spends most of its circumference off-sheet; every
    point it draws must still land inside [0, width] x [0, height] once clipped."""
    tone = _uniform_tone(1.0, size_mm=30.0, cell_mm=1.0)
    polylines = ripple(tone, ring_spacing_mm=3.0, amplitude_mm=1.0)
    assert polylines, "solid black must draw something"
    for polyline in polylines:
        for x, y in polyline:
            assert -1e-6 <= x <= 30.0 + 1e-6, f"x {x} outside [0, 30]"
            assert -1e-6 <= y <= 30.0 + 1e-6, f"y {y} outside [0, 30]"


def test_dark_region_displaces_a_ring_more_than_a_light_one() -> None:
    """A ring passing through a dark patch must be pushed farther from its base radius than
    the same ring passing through a light (but still gated) patch."""
    size_mm = 40.0
    cell_mm = 1.0
    cells = round(size_mm / cell_mm)
    darkness = np.full((cells, cells), 0.2)
    # A dark patch straight above the focus (frame centre): a ring whose radius reaches it
    # gets pushed there, while the rest of that same ring only ever sees the light background.
    darkness[2:8, 15:25] = 0.95
    tone = ToneGrid(darkness, cell_mm, size_mm, size_mm)

    ring_spacing_mm = 2.0
    polylines = ripple(tone, ring_spacing_mm=ring_spacing_mm, amplitude_mm=1.0, min_darkness=0.1)
    assert polylines

    focus = (size_mm / 2.0, size_mm / 2.0)
    # The patch sits ~15-18 mm above the focus; radius 16 mm lands inside it.
    target_radius_mm = 16.0
    k = round(target_radius_mm / ring_spacing_mm)
    base_radius = k * ring_spacing_mm

    def radius_at(angle_deg: float) -> float | None:
        target = (
            focus[0] + base_radius * math.cos(math.radians(angle_deg)),
            focus[1] + base_radius * math.sin(math.radians(angle_deg)),
        )
        best = None
        best_dist = math.inf
        for polyline in polylines:
            for point in polyline:
                dist = math.hypot(point[0] - target[0], point[1] - target[1])
                if dist < best_dist:
                    best_dist = dist
                    best = point
        if best is None or best_dist > ring_spacing_mm:
            return None
        return math.hypot(best[0] - focus[0], best[1] - focus[1])

    # The wobble rides along the ring as a sine, so a single sample can catch it at a zero
    # crossing: compare how far the ring swings over a span of angles instead, which is the
    # amplitude the darkness actually sets. -90 degrees (screen "up", y grows downward)
    # points into the dark patch; 90 degrees is plain light background.
    def swing_near(angle_deg: float) -> float:
        radii = [radius_at(angle_deg + offset) for offset in range(-12, 13, 2)]
        seen = [radius for radius in radii if radius is not None]
        assert seen, f"no ring found near {angle_deg} degrees"
        return max(abs(radius - base_radius) for radius in seen)

    dark_swing = swing_near(-90.0)
    light_swing = swing_near(90.0)
    assert dark_swing > light_swing, (dark_swing, light_swing)
