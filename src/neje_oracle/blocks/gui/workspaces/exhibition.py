"""Exhibition workspace: minimal live-print control and status."""

from __future__ import annotations

from nicegui import ui

from ..context import GuiContext


def build(ctx: GuiContext) -> None:
    with ui.column().classes("workspace-scroll gap-2"):
        with ui.card().classes("oracle-card compact-card w-full"):
            ui.label("Exhibition controls").classes("text-sm font-bold")
            ui.label("Minimal live-print controls. No layout, jog, scale or test generation here.").classes("text-xs text-[#8f4f2b]")
            ctx.start_print_button = ui.button("START PRINT", on_click=ctx.start_print).props("dense color=positive").classes("w-full")

        with ui.card().classes("oracle-card compact-card w-full"):
            ui.label("Live print state").classes("text-sm font-bold")
            with ui.grid(columns=2).classes("w-full gap-1"):
                for key, label in (("state", "Print"), ("mode", "Mode")):
                    with ui.element("div").classes("mini-metric"):
                        ui.label(label).classes("label")
                        ctx.plotter_labels[key] = ui.label("-").classes("value")
            ctx.plotter_labels["sheet"] = ui.label("no sheet yet").classes("path-label text-xs font-bold")
            ctx.plotter_labels["cells"] = ui.label("-").classes("text-xs text-[#8f4f2b]")
            ctx.progress = ui.linear_progress(value=0).classes("w-full")
            ctx.plotter_labels["progress"] = ui.label("-").classes("text-xs text-[#8f4f2b]")
            ctx.plotter_labels["message"] = ui.label("-").classes("path-label text-xs")
