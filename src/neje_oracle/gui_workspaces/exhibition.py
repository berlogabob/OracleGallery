"""Exhibition workspace for the Oracle GUI."""

from __future__ import annotations

from typing import Any, Callable

from nicegui import ui


def build_exhibition_workspace(*, start_print: Callable[..., Any]) -> Any:
    """Build minimal live-print controls and return the start-print button."""
    with ui.column().classes("workspace-scroll gap-2"):
        with ui.card().classes("oracle-card compact-card w-full"):
            ui.label("Exhibition controls").classes("text-sm font-bold")
            ui.label("Minimal live-print controls. No layout, jog, scale or test generation here.").classes("text-xs text-[#8f4f2b]")
            with ui.column().classes("gap-2"):
                return ui.button("START PRINT", on_click=start_print).props("dense color=positive").classes("w-full")


def build_exhibition_status_workspace(plotter_labels: dict[str, Any]) -> Any:
    """Build live print status and return the progress bar."""
    with ui.column().classes("workspace-scroll gap-2"):
        with ui.card().classes("oracle-card compact-card w-full"):
            ui.label("Live print state").classes("text-sm font-bold")
            with ui.grid(columns=2).classes("w-full gap-1"):
                with ui.element("div").classes("mini-metric"):
                    ui.label("Print").classes("label")
                    plotter_labels["state"] = ui.label("-").classes("value")
                with ui.element("div").classes("mini-metric"):
                    ui.label("Mode").classes("label")
                    plotter_labels["mode"] = ui.label("-").classes("value")
            plotter_labels["sheet"] = ui.label("no sheet yet").classes("path-label text-xs font-bold")
            plotter_labels["cells"] = ui.label("-").classes("text-xs text-[#8f4f2b]")
            progress = ui.linear_progress(value=0).classes("w-full")
            plotter_labels["progress"] = ui.label("-").classes("text-xs text-[#8f4f2b]")
            plotter_labels["message"] = ui.label("-").classes("path-label text-xs")
            return progress
