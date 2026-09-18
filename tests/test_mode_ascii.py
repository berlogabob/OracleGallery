from __future__ import annotations

import io

import pytest
from mode_contract import check_mode_contract
from PIL import Image

from neje_oracle.blocks.imaging.art.ascii import (
    DEFAULT_CHARSET,
    _build_ramp,
    _char_grid,
    _measure_aspect,
    _pick_font,
    ascii,
    quality_params,
)
from neje_oracle.blocks.imaging.modes import ToneGrid, load_tone


def _tone(image: Image.Image, width_mm: float, height_mm: float, cell_mm: float) -> ToneGrid:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return load_tone(buffer.getvalue(), width_mm=width_mm, height_mm=height_mm, cell_mm=cell_mm)


def test_contract():
    report = check_mode_contract(ascii, quality_params, monotonic=True)
    print(report)


def test_ramp_is_sorted_by_measured_ink_not_charset_order():
    font = _pick_font(None)
    ramp = _build_ramp(font, 3.0, DEFAULT_CHARSET)
    inks = [ink for _, ink in ramp]
    assert len(ramp) >= 2, "at least two distinct glyphs must render non-empty ink"
    assert inks == sorted(inks)
    # The ramp characters need not equal the typed charset order once resorted by ink.
    assert {character for character, _ in ramp} <= set(DEFAULT_CHARSET)


def test_black_field_uses_only_inkiest_glyph_white_field_uses_none():
    font = _pick_font(None)
    ramp = _build_ramp(font, 3.0, DEFAULT_CHARSET)
    inkiest_character = ramp[-1][0]
    aspect = _measure_aspect(font, 3.0)
    cell_w, cell_h = 3.0 * aspect, 3.0

    black = _tone(Image.new("L", (30, 30), 0), 30.0, 30.0, 1.0)
    white = _tone(Image.new("L", (30, 30), 255), 30.0, 30.0, 1.0)

    black_grid = _char_grid(black, cell_w, cell_h, ramp, 0.05)
    white_grid = _char_grid(white, cell_w, cell_h, ramp, 0.05)

    assert black_grid, "the black field must produce at least one row of cells"
    assert all(character == inkiest_character for row in black_grid for character in row)
    assert all(character is None for row in white_grid for character in row)


def test_max_glyphs_guard_raises():
    tone = _tone(Image.new("L", (200, 200), 128), 200.0, 200.0, 1.0)
    with pytest.raises(ValueError, match="max_glyphs"):
        ascii(tone, char_mm=0.5, max_glyphs=10)
