"""Contract + packing-specific coverage for the circle-packing mode."""

from __future__ import annotations

import math

import numpy as np
from mode_contract import check_mode_contract

from neje_oracle.blocks.imaging.art.circlepack import circlepack, quality_params
from neje_oracle.blocks.imaging.modes import ToneGrid


def test_circlepack_contract() -> None:
    print(check_mode_contract(circlepack, quality_params))


def _uniform(darkness: float) -> ToneGrid:
    return ToneGrid(np.full((64, 64), darkness), 1.0, 64.0, 64.0)


def _circles(polylines: list[list[tuple[float, float]]]) -> list[tuple[float, float, float]]:
    out = []
    for ring in polylines:
        xs = [x for x, _ in ring]
        ys = [y for _, y in ring]
        cx, cy = (min(xs) + max(xs)) / 2.0, (min(ys) + max(ys)) / 2.0
        out.append((cx, cy, (max(xs) - min(xs)) / 2.0))
    return out


def _gradient() -> ToneGrid:
    return ToneGrid(np.tile(np.linspace(1.0, 0.12, 64), (64, 1)), 1.0, 64.0, 64.0)


def test_circles_do_not_overlap() -> None:
    """The one property a packing has to have, checked on a GRADIENT and not a flat tone.

    A flat field gives every circle the same radius, and at one radius the bucket grid cannot
    get its neighbour window wrong. Mixed sizes can: the first version bucketed at one radius
    instead of two and left visibly crossed circles wherever a big one met a small one.
    """
    circles = _circles(circlepack(_gradient()))
    assert len(circles) > 50
    for index, (x, y, r) in enumerate(circles):
        for ox, oy, orad in circles[index + 1 :]:
            # Ring points are sampled, so a measured radius runs a hair under the true one.
            assert math.dist((x, y), (ox, oy)) >= r + orad - 0.05, ((x, y, r), (ox, oy, orad))


def test_dark_packs_smaller_circles_than_light() -> None:
    dark = _circles(circlepack(_uniform(0.95)))
    light = _circles(circlepack(_uniform(0.15)))
    assert max(r for _, _, r in dark) < max(r for _, _, r in light)
    assert len(dark) > len(light)
