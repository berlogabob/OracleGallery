"""Tests workspace: system-node status, G-code test draw, and direct-SVG print."""

from __future__ import annotations

from nicegui import ui

from ..context import GuiContext
from ..support import GUI_DEFAULTS
from ..ui import helper_text, number_control, primary_action_button, safe_action_button


def build(ctx: GuiContext) -> None:
    settings = ctx.settings
    fields = ctx.fields

    with ui.column().classes("w-full gap-2"):
        with ui.card().classes("oracle-card compact-card w-full"):
            ui.label("Test prints").classes("text-sm font-bold")
            helper_text(
                "Generates a local sheet from bundled symbols or starts a test print from the current queue/settings."
            )
            with ui.row().classes("items-center gap-2"):
                safe_action_button("GENERATE G-CODE", ctx.generate_dry_run)
                primary_action_button("START TEST PRINT", ctx.start_test_print)
            ui.separator()
            helper_text(
                "Pen calibration: one sheet, a ladder per setting — draw feed, pen-down Z and dwell vary row "
                "by row. Read the best rung off each ladder, type it into Motion speed, then SAVE AS PROFILE."
            )
            helper_text(
                "The Z ladder stays within +/-1mm of the current pen-down depth (never past -30mm); "
                "written to the spool as pen_cal_<profile>.gcode."
            )
            with ui.row().classes("items-center gap-2"):
                safe_action_button("GENERATE PEN CAL G-CODE", ctx.generate_pen_cal)

        with ui.card().classes("oracle-card compact-card w-full"):
            ui.label("SVG test draw").classes("text-sm font-bold")
            helper_text(
                "Prints the selected Inkscape SVG directly to FluidNC. Requires passing system checks, work zero, CONNECT and Idle."
            )
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
                    on_change=ctx.persist_and_refresh,
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
                    on_change=ctx.persist_and_refresh,
                )
            ui.upload(on_upload=ctx.handle_svg_upload).props("accept=.svg max-files=1 auto-upload").classes("w-full")
            with ui.row().classes("items-center gap-2"):
                primary_action_button("START SVG PRINT", ctx.print_uploaded_svg)
                ctx.uploaded_svg_label = ui.label("No SVG selected").classes("path-label text-xs")
            helper_text("Use generated G-code first when validating layout or sampling changes.")
