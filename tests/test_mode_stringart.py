"""Contract + thread-specific coverage for the string-art mode."""

from __future__ import annotations

import math

import numpy as np
from mode_contract import check_mode_contract

from neje_oracle.blocks.imaging.art.stringart import quality_params, stringart
from neje_oracle.blocks.imaging.modes import ToneGrid


def test_stringart_contract() -> None:
    """monotonic=False, and not because the mode is sloppy.

    Every chord is a straight line from rim to rim: ink lands along its whole length, including
    over paper the thread is only crossing to reach the dark side. A per-strip measure counts
    that through-traffic, so the registry-wide monotonic test excludes this mode too (see
    tests/test_imaging_modes.py). What must hold instead is that the thread SPENDS its length
    on the dark side, which is the next test.
    """
    print(check_mode_contract(stringart, quality_params, monotonic=False))


def test_the_thread_spends_its_length_on_the_dark_side() -> None:
    darkness = np.zeros((64, 64))
    darkness[:, :32] = 1.0
    thread = stringart(ToneGrid(darkness, 1.0, 64.0, 64.0), chords=200)
    assert len(thread) == 1, "string art is one continuous stroke, not a pile of chords"

    left = right = 0.0
    for start, end in zip(thread[0], thread[0][1:], strict=False):
        length = math.dist(start, end)
        # Split at the midpoint of each chord: a chord is straight, so the halves land where
        # its own midpoint says they do, which is all this measure needs.
        if (start[0] + end[0]) / 2.0 < 32.0:
            left += length
        else:
            right += length
    assert left > right * 2.0, (left, right)


def test_white_paper_leaves_no_thread() -> None:
    assert stringart(ToneGrid(np.zeros((64, 64)), 1.0, 64.0, 64.0)) == []
