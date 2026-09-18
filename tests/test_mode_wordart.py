"""Contract + wordart-specific coverage: the mode's whole point is a readable, ordered message."""

from __future__ import annotations

import io

from mode_contract import check_mode_contract
from PIL import Image

from neje_oracle.blocks.imaging.art.wordart import (
    _layout,
    quality_params,
    wordart,
)
from neje_oracle.blocks.imaging.modes import ToneGrid, load_tone


def _tone(image: Image.Image, width_mm: float, height_mm: float, cell_mm: float) -> ToneGrid:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return load_tone(buffer.getvalue(), width_mm=width_mm, height_mm=height_mm, cell_mm=cell_mm)


def test_contract():
    report = check_mode_contract(wordart, quality_params, monotonic=True)
    print(report)


def test_layout_follows_input_text_in_order_with_wraparound():
    """Every drawn cell's character is `text` cycling in order -- proven on the layout grid
    itself, not by reading glyphs back out of the rendered polylines (OCR would only tell us
    a glyph looks roughly right, not that it is the correct one in the correct position).

    A uniformly solid-black tone means no cell is gated, so the flattened row-major grid is
    exactly text[i % len(text)] for i in range(rows * cols) with nothing skipped or reordered.
    """
    tone = _tone(Image.new("L", (40, 40), 0), 40.0, 40.0, 1.0)
    text = "NEJE"
    cap_height_mm = 5.0
    aspect = 0.7  # any positive placeholder; _layout only needs cell geometry, not a real font
    cell_w = cap_height_mm * aspect * 1.3
    cell_h = cap_height_mm * 1.9

    grid = _layout(tone, cell_w, cell_h, text, min_darkness=0.05)
    flattened = [cell for line in grid for cell in line]
    assert flattened, "a solid black tone must produce at least one cell"
    assert all(cell is not None for cell in flattened), "solid black must not gate any cell"

    characters = [character for character, _ in flattened]
    expected = [text[index % len(text)] for index in range(len(characters))]
    assert characters == expected


def test_same_text_renders_identically_twice_longer_text_changes_it():
    tone = _tone(Image.new("L", (60, 40), 96), 60.0, 40.0, 0.5)

    first = wordart(tone, text="NEJE ORACLE")
    second = wordart(tone, text="NEJE ORACLE")
    assert first == second, "same tone and text must render byte-identical polylines"

    longer = wordart(tone, text="NEJE ORACLE DRAWS PLOTTER ART FROM A SENTENCE")
    assert longer != first, "a longer message must change the render, not just repeat the short one"
