"""Contract + barcode-specific coverage for the stacked-barcode mode."""

from __future__ import annotations

import numpy as np
from mode_contract import check_mode_contract

from neje_oracle.blocks.imaging.art.barcode import barcode, quality_params
from neje_oracle.blocks.imaging.modes import ToneGrid


def test_barcode_contract() -> None:
    print(check_mode_contract(barcode, quality_params))


def _uniform(darkness: float, *, width_mm: float = 40.0, height_mm: float = 16.0) -> ToneGrid:
    return ToneGrid(np.full((16, 40), darkness), 1.0, width_mm, height_mm)


def test_darker_columns_get_wider_bars() -> None:
    """Tone is bar width, and bar width is a line count -- that is the whole mapping."""
    dark = barcode(_uniform(0.9))
    light = barcode(_uniform(0.2))
    assert len(dark) > len(light) > 0


def test_bands_leave_an_alley_between_them() -> None:
    """Without the alley a dark region is one black rectangle, not a stack of rows."""
    bars = barcode(_uniform(1.0), band_height_mm=8.0)
    tops = sorted({round(min(y for _, y in bar), 3) for bar in bars})
    bottoms = sorted({round(max(y for _, y in bar), 3) for bar in bars})
    assert len(tops) == 2, tops
    assert tops[1] - bottoms[0] > 0.5, "the second band must start below the first band's bars"
