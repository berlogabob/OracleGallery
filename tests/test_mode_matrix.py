"""Contract + matrix-specific coverage for the code-generated pseudo-katakana mode."""

from __future__ import annotations

from mode_contract import check_mode_contract

from neje_oracle.blocks.imaging.art.matrix import (
    _DIAGONALS,
    _OUTER_EDGES,
    _SPINE_STROKES,
    _alphabet,
    _connected,
    _stroke_length,
    matrix,
    quality_params,
)


def test_matrix_contract() -> None:
    report = check_mode_contract(matrix, quality_params, monotonic=True)
    print(report)
    print(f"alphabet size: {len(_alphabet())}")


def test_every_stroke_lies_inside_the_unit_cell() -> None:
    """Whatever combination a glyph is built from, its strokes never leave the [0, 1] lattice.

    This is what makes `_place_glyph`'s scale-and-gutter placement safe: a stroke already
    inside the unit square can only shrink further inside its own cell, never poke out of it.
    """
    for glyph in _alphabet():
        for start, end in glyph:
            for x, y in (start, end):
                assert 0.0 <= x <= 1.0, f"stroke endpoint {(x, y)} outside the unit cell"
                assert 0.0 <= y <= 1.0, f"stroke endpoint {(x, y)} outside the unit cell"


def test_every_generated_glyph_is_connected() -> None:
    """Every glyph the alphabet produces can be BUILT one stroke at a time such that each
    stroke after the first shares a lattice point with a stroke already placed.

    The alphabet stores each glyph's strokes in vocabulary order, not build order, so this is
    an independent, order-agnostic re-check of `_connected`: grow a "placed" set of strokes
    greedily, at each step adding any remaining stroke that touches a lattice point already
    covered, and confirm every stroke is eventually reachable that way. A graph is connected
    exactly when such a greedy growth order exists, so this is the literal reading of the
    design rule, not merely a repeat of `_connected`'s own union-find.
    """
    for glyph in _alphabet():
        assert _connected(glyph), f"generator produced a disconnected glyph: {glyph}"
        remaining = list(glyph[1:])
        touched: set[tuple[float, float]] = set(glyph[0])
        progressed = True
        while remaining and progressed:
            progressed = False
            for stroke in list(remaining):
                if touched & set(stroke):
                    touched.update(stroke)
                    remaining.remove(stroke)
                    progressed = True
        assert not remaining, f"glyph has strokes unreachable by shared lattice points: {remaining}"


def test_alphabet_has_no_duplicate_or_zero_length_glyphs() -> None:
    seen = set()
    for glyph in _alphabet():
        key = frozenset(glyph)
        assert key not in seen, f"duplicate glyph: {glyph}"
        seen.add(key)
        assert sum(_stroke_length(stroke) for stroke in glyph) > 0


def test_no_glyph_uses_all_four_outer_edges() -> None:
    """A closed rectangle reads as tofu (a missing-character box), never a character."""
    for glyph in _alphabet():
        assert not set(glyph) >= _OUTER_EDGES, f"glyph traces a closed box: {glyph}"


def test_no_glyph_has_two_diagonals() -> None:
    """Two full diagonals together is the 'X in a box' look this alphabet must avoid."""
    for glyph in _alphabet():
        assert sum(1 for stroke in glyph if stroke in _DIAGONALS) <= 1, f"glyph has both diagonals: {glyph}"


def test_every_multi_stroke_glyph_has_a_spine() -> None:
    """A glyph of 2+ strokes needs at least one full-length horizontal or vertical: short
    strokes hang off that spine rather than floating as an unanchored cloud of ticks."""
    for glyph in _alphabet():
        if len(glyph) >= 2:
            assert any(stroke in _SPINE_STROKES for stroke in glyph), f"glyph has no spine: {glyph}"
