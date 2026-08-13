"""Live print state: the readouts for the sheet being drawn.

The START PRINT button that used to sit here is gone -- the machine rail's next-action
button is the one place a run starts. Two buttons for the same irreversible action, one of
them visible on every screen and one only here, meant an operator had to know which one was
"real"; the answer was both, which is worse.
"""

from __future__ import annotations

from nicegui import ui

from ..context import GuiContext


def build(ctx: GuiContext) -> None:
    with ui.column().classes("w-full gap-2"), ui.card().classes("oracle-card compact-card w-full"):
        ui.label("Live print state").classes("text-sm font-bold")
        ctx.plotter_labels["sheet"] = ui.label("no sheet yet").classes("path-label text-xs font-bold")
        ctx.plotter_labels["cells"] = ui.label("-").classes("text-xs text-[#8f4f2b]")
        ctx.progress = ui.linear_progress(value=0).classes("w-full")
        ctx.plotter_labels["message"] = ui.label("-").classes("path-label text-xs")
