"""Contract + quadtree-specific coverage for the recursive-squares mode."""

from __future__ import annotations

import numpy as np
from mode_contract import check_mode_contract

from neje_oracle.blocks.imaging.art.quadtree import quadtree, quality_params
from neje_oracle.blocks.imaging.modes import ToneGrid


def test_quadtree_contract() -> None:
    print(check_mode_contract(quadtree, quality_params))


def _uniform(darkness: float) -> ToneGrid:
    return ToneGrid(np.full((64, 64), darkness), 1.0, 64.0, 64.0)


def test_dark_splits_further_than_light() -> None:
    """The split rule is tone, not variance: both fields here are perfectly smooth, and the
    dark one must still come out as more, smaller cells."""
    dark = quadtree(_uniform(0.95))
    light = quadtree(_uniform(0.22))
    assert len(dark) > len(light) > 0


def test_a_leaf_is_a_closed_square() -> None:
    """Closed, so the pen returns to where it started and no cell shows a gap on paper."""
    for cell in quadtree(_uniform(0.5)):
        assert cell[0] == cell[-1], cell
