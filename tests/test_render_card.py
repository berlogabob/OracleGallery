"""The shared render -> preview -> estimate -> print card.

Three workspaces carried their own copy of this pipeline, with three slightly different cost
sentences and one of them borrowing the estimator from a sibling view module. The property
that matters most is the one an operator's trust rests on: **with travel lines off, the
preview is not a picture of the output, it is the output** -- the same bytes, byte for byte.

That is not pedantry. travel_preview_svg draws pen-up moves as real <polyline> elements, and
svg_gcode will happily draw every one of them, so a preview that quietly leaked into the print
path would put travel hairlines on the paper.
"""

from __future__ import annotations

from typing import Any

import pytest
from nicegui import ui

from neje_oracle.blocks.gui import ui as oracle
from neje_oracle.blocks.gui.context import GuiContext
from neje_oracle.blocks.imaging.modes import polylines_to_svg
from neje_oracle.shared.gui_settings import GuiSettings

_SQUARE = [[(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0), (0.0, 0.0)]]
_SECOND = [[(20.0, 20.0), (30.0, 30.0)]]


def _ctx(monkeypatch: pytest.MonkeyPatch) -> GuiContext:
    monkeypatch.setattr("neje_oracle.blocks.gui.context.load_gui_settings", lambda *a, **k: GuiSettings())
    return GuiContext()


def _render(polylines: Any = None) -> oracle.Render:
    return oracle.Render(
        polylines=polylines if polylines is not None else _SQUARE,
        width_mm=50.0,
        height_mm=50.0,
        name="probe",
    )


def test_travel_off_means_the_preview_is_the_printed_bytes(monkeypatch: pytest.MonkeyPatch) -> None:
    ctx = _ctx(monkeypatch)
    with ui.column():
        card = oracle.render_card(ctx, title="Probe", render=lambda: _render(_SQUARE + _SECOND), travel_default=False)

    card.refresh()

    expected = polylines_to_svg(
        _SQUARE + _SECOND, width_mm=50.0, height_mm=50.0, pen_width_mm=ctx.settings.pen_width_mm
    )
    assert card.svg == expected
    # The load-bearing assertion: what is on screen IS what goes to the machine.
    assert card.preview.content == expected


def test_travel_on_shows_moves_that_never_reach_the_print_bytes(monkeypatch: pytest.MonkeyPatch) -> None:
    """The travel overlay is screen-only. If it ever reached `.svg`, the pen would draw it."""
    ctx = _ctx(monkeypatch)
    with ui.column():
        card = oracle.render_card(ctx, title="Probe", render=lambda: _render(_SQUARE + _SECOND), travel_default=True)

    card.refresh()

    printed = polylines_to_svg(_SQUARE + _SECOND, width_mm=50.0, height_mm=50.0, pen_width_mm=ctx.settings.pen_width_mm)
    assert card.svg == printed, "the print bytes must not depend on the travel toggle"
    # _SECOND starts away from where _SQUARE ends, so there is a real pen-up move to draw.
    # Travel renders as <line> elements; the print bytes contain none.
    assert card.preview.content != printed, "travel lines should be visible on screen"
    assert "<line" in card.preview.content
    assert "<line" not in printed, "a travel hairline in the print bytes is ink on the paper"


def test_a_render_failure_speaks_to_the_operator_instead_of_raising(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every copy of this block already treated a breached cap as a normal outcome."""
    ctx = _ctx(monkeypatch)

    def boom() -> oracle.Render:
        raise ValueError("cell size too small for this sheet")

    with ui.column():
        card = oracle.render_card(ctx, title="Probe", render=boom)

    card.refresh()

    assert card.svg == "", "a failed render must not leave stale bytes ready to print"
    assert card.preview.content == "", "nor a stale picture suggesting it worked"


def test_cost_line_only_mentions_pen_lifts_when_they_matter() -> None:
    """On a servo pen the lift term routinely dominates; a 488-stroke halftone reading
    '1.7 min' is how a plot gets started that is still running an hour later."""
    quiet = oracle.cost_line(_SQUARE, draw_mm=1000.0, travel_mm=500.0, minutes=(2.0, 0.0))
    loud = oracle.cost_line(_SQUARE, draw_mm=1000.0, travel_mm=500.0, minutes=(2.0, 14.6))

    assert "pen lifts" not in quiet
    assert "15 min pen lifts" in loud
    assert "~17 min" in loud
