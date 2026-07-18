"""Tests workspace: system-node status, G-code test draw, and direct-SVG print."""

from __future__ import annotations

from nicegui import ui

from ..context import GuiContext
from ..support import GUI_DEFAULTS
from ..ui import number_control, status_pill


def build(ctx: GuiContext) -> None:
    settings = ctx.settings
    fields = ctx.fields

    with ui.column().classes("workspace-scroll gap-2"):
        with ui.card().classes("oracle-card compact-card w-full"):
            ui.label("System nodes").classes("text-sm font-bold")
            ui.label("Green = ready/running, yellow = warning, gray = offline/stopped, red = error.").classes("text-xs text-[#8f4f2b]")
            with ui.row().classes("gap-2 flex-wrap"):
                ctx.node_pills["fluidnc"] = status_pill("Plotter")
                ctx.node_pills["macmini"] = status_pill("Mac mini")
                ctx.node_pills["firebase"] = status_pill("Firebase")
                ctx.node_pills["queue"] = status_pill("Queue")
                ctx.node_pills["print"] = status_pill("Print")

        with ui.card().classes("oracle-card compact-card w-full"):
            ui.label("G-code test draw").classes("text-sm font-bold")
            ui.label("Generates a local sheet from bundled symbols or starts a test print from the current queue/settings.").classes("text-xs text-[#8f4f2b]")
            with ui.row().classes("items-center gap-2"):
                ui.button("GENERATE G-CODE", on_click=ctx.generate_dry_run).props("dense")
                ui.button("START TEST PRINT", on_click=ctx.start_test_print).props("dense color=positive")

        with ui.card().classes("oracle-card compact-card w-full"):
            ui.label("SVG test draw").classes("text-sm font-bold")
            ui.label("Prints the selected Inkscape SVG directly to FluidNC. Requires passing system checks, work zero, CONNECT and Idle.").classes("text-xs text-[#8f4f2b]")
            with ui.row().classes("gap-2 w-full"):
                number_control(
                    fields, "direct_svg_origin_x_mm", label="SVG X0", value=settings.direct_svg_origin_x_mm,
                    default=float(GUI_DEFAULTS["direct_svg_origin_x_mm"]), min_value=0, width_class="w-full",
                    tooltip="Direct SVG print: machine/work X position for SVG coordinate 0.", on_change=ctx.persist_and_refresh,
                )
                number_control(
                    fields, "direct_svg_origin_y_mm", label="SVG Y0", value=settings.direct_svg_origin_y_mm,
                    default=float(GUI_DEFAULTS["direct_svg_origin_y_mm"]), min_value=0, width_class="w-full",
                    tooltip="Direct SVG print: machine/work Y position for SVG coordinate 0.", on_change=ctx.persist_and_refresh,
                )
            ui.upload(on_upload=ctx.handle_svg_upload).props("accept=.svg max-files=1 auto-upload").classes("w-full")
            with ui.row().classes("items-center gap-2"):
                ui.button("START SVG PRINT", on_click=ctx.print_uploaded_svg).props("dense color=positive")
                ctx.uploaded_svg_label = ui.label("No SVG selected").classes("path-label text-xs")

        with ui.card().classes("oracle-card compact-card w-full"):
            ui.label("Test workspace notes").classes("text-sm font-bold")
            ui.label("Tests run real FluidNC motion after the same readiness checks.").classes("text-xs text-[#8f4f2b]")
            ui.label("Use generated G-code first when validating layout or sampling changes.").classes("text-xs text-[#8f4f2b]")
            ui.label("The preview remains centered so the expected sheet is visible before print.").classes("text-xs text-[#8f4f2b]")
