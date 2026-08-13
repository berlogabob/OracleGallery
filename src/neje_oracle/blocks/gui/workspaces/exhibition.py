"""Exhibition workspace: minimal live-print control and status."""

from __future__ import annotations

from nicegui import ui

from ..context import GuiContext
from ..ui import helper_text, primary_action_button


def build(ctx: GuiContext) -> None:
    with ui.column().classes("w-full gap-2"):
        with ui.card().classes("oracle-card compact-card w-full"):
            ui.label("Exhibition controls").classes("text-sm font-bold")
            helper_text("Minimal live-print controls. No layout, jog, scale or test generation here.")
            ctx.start_print_button = primary_action_button("START PRINT", ctx.start_print).classes("w-full")

        with ui.card().classes("oracle-card compact-card w-full"):
            ui.label("Live print state").classes("text-sm font-bold")
            ctx.plotter_labels["sheet"] = ui.label("no sheet yet").classes("path-label text-xs font-bold")
            ctx.plotter_labels["cells"] = ui.label("-").classes("text-xs text-[#8f4f2b]")
            ctx.progress = ui.linear_progress(value=0).classes("w-full")
            ctx.plotter_labels["message"] = ui.label("-").classes("path-label text-xs")
