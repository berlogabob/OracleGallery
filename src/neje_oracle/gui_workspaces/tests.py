"""Tests workspace for the Oracle GUI."""

from __future__ import annotations

from typing import Any, Callable

from nicegui import ui

from ..gui_support import GUI_DEFAULTS, GuiSettings
from ..gui_ui import number_control, status_pill


def build_tests_workspace(
    settings: GuiSettings,
    fields: dict[str, Any],
    node_pills: dict[str, Any],
    *,
    generate_dry_run: Callable[..., Any],
    start_test_print: Callable[..., Any],
    handle_svg_upload: Callable[..., Any],
    print_uploaded_svg: Callable[..., Any],
    persist_and_refresh: Callable[..., Any],
) -> Any:
    """Build test-print and direct-SVG controls.

    Returns the selected-SVG label so upload callbacks in ``gui_service`` can
    update it without keeping the whole tests panel in the monolith.
    """
    with ui.column().classes("workspace-scroll gap-2"):
        with ui.card().classes("oracle-card compact-card w-full"):
            ui.label("System nodes").classes("text-sm font-bold")
            ui.label("Green = ready/running, yellow = warning, gray = offline/stopped, red = error.").classes("text-xs text-[#8f4f2b]")
            with ui.row().classes("gap-2 flex-wrap"):
                node_pills["fluidnc"] = status_pill("Plotter")
                node_pills["macmini"] = status_pill("Mac mini")
                node_pills["firebase"] = status_pill("Firebase")
                node_pills["queue"] = status_pill("Queue")
                node_pills["print"] = status_pill("Print")

        with ui.card().classes("oracle-card compact-card w-full"):
            ui.label("G-code test draw").classes("text-sm font-bold")
            ui.label("Generates a local sheet from bundled symbols or starts a test print from the current queue/settings.").classes("text-xs text-[#8f4f2b]")
            with ui.row().classes("items-center gap-2"):
                ui.button("GENERATE G-CODE", on_click=generate_dry_run).props("dense")
                ui.button("START TEST PRINT", on_click=start_test_print).props("dense color=positive")

        with ui.card().classes("oracle-card compact-card w-full"):
            ui.label("SVG test draw").classes("text-sm font-bold")
            ui.label("Prints the selected Inkscape SVG directly to FluidNC. Requires passing system checks, work zero, CONNECT and Idle.").classes("text-xs text-[#8f4f2b]")
            with ui.row().classes("gap-2 w-full"):
                number_control(
                    fields,
                    "direct_svg_origin_x_mm",
                    label="SVG X0",
                    value=settings.direct_svg_origin_x_mm,
                    default=float(GUI_DEFAULTS["direct_svg_origin_x_mm"]),
                    min_value=0,
                    width_class="w-full",
                    tooltip="Direct SVG print: machine/work X position for SVG coordinate 0.",
                    on_change=persist_and_refresh,
                )
                number_control(
                    fields,
                    "direct_svg_origin_y_mm",
                    label="SVG Y0",
                    value=settings.direct_svg_origin_y_mm,
                    default=float(GUI_DEFAULTS["direct_svg_origin_y_mm"]),
                    min_value=0,
                    width_class="w-full",
                    tooltip="Direct SVG print: machine/work Y position for SVG coordinate 0.",
                    on_change=persist_and_refresh,
                )
            ui.upload(on_upload=handle_svg_upload).props("accept=.svg max-files=1 auto-upload").classes("w-full")
            with ui.row().classes("items-center gap-2"):
                ui.button("START SVG PRINT", on_click=print_uploaded_svg).props("dense color=positive")
                return ui.label("No SVG selected").classes("path-label text-xs")


def build_tests_notes() -> None:
    """Build the right-column notes for the Tests workspace."""
    with ui.column().classes("workspace-scroll gap-2"):
        with ui.card().classes("oracle-card compact-card w-full"):
            ui.label("Test workspace notes").classes("text-sm font-bold")
            ui.label("Tests run real FluidNC motion after the same readiness checks.").classes("text-xs text-[#8f4f2b]")
            ui.label("Use generated G-code first when validating layout or sampling changes.").classes("text-xs text-[#8f4f2b]")
            ui.label("The preview remains centered so the expected sheet is visible before print.").classes("text-xs text-[#8f4f2b]")
