"""Shared manual-motion card (jog pad, homing, pen).

One implementation used by both the Connection and Calibration workspaces — replaces
the copies that used to live in service.py, connection.py, and calibration.py.
"""

from __future__ import annotations

from nicegui import ui

from ..context import GuiContext
from ..ui import helper_text


def render_motion_panel(ctx: GuiContext) -> None:
    with ui.card().classes("oracle-card compact-card w-full"):
        ui.label("Manual motion").classes("text-sm font-bold")
        helper_text("Jog and homing for setup. Manual movement is blocked while G-code streams.")
        with ui.row().classes("gap-2 items-end"):
            ctx.fields["jog_step"] = (
                ui.select(
                    {1.0: "1", 5.0: "5", 10.0: "10", 25.0: "25", 50.0: "50", 100.0: "100"},
                    value=1.0,
                    label="Step mm",
                )
                .props("dense outlined")
                .classes("w-24")
            )
            ctx.fields["jog_feed"] = (
                ui.number("Feed", value=1000, min=1, step=100).props("dense outlined").classes("w-24")
            )
            ui.button("Home all", on_click=ctx.home_xy).props("dense color=warning")
        with ui.grid(columns=3).classes("w-full gap-1 jog-pad"):
            ui.label("")
            ui.button("Y+", on_click=ctx.jog_y_positive).props("dense").classes("w-12 h-12")
            ui.label("")
            ui.button("X-", on_click=ctx.jog_x_negative).props("dense").classes("w-12 h-12")
            ui.button("Y-", on_click=ctx.jog_y_negative).props("dense").classes("w-12 h-12")
            ui.button("X+", on_click=ctx.jog_x_positive).props("dense").classes("w-12 h-12")
        with ui.row().classes("gap-1"):
            ui.button("Z up / Pen up", on_click=ctx.pen_up).props("dense flat")
            ui.button("Z- / Pen down", on_click=ctx.pen_down).props("dense flat")
            ui.button("Home X", on_click=lambda: ctx.home_axis("X")).props("dense flat")
            ui.button("Home Y", on_click=lambda: ctx.home_axis("Y")).props("dense flat")
