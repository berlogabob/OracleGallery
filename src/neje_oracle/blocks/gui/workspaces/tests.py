"""Tests workspace: system-node status, G-code test draw, and direct-SVG print."""

from __future__ import annotations

from nicegui import ui

from ...gcode.pen_cal import Z_ABSOLUTE_FLOOR_MM
from ..context import GuiContext
from ..support import GUI_DEFAULTS
from ..ui import (
    card,
    file_upload,
    helper_text,
    number_control,
    primary_action_button,
    safe_action_button,
    toolbar,
)


def build(ctx: GuiContext) -> None:
    settings = ctx.settings
    fields = ctx.fields

    with ui.column().classes("w-full gap-2"):
        with card("Test prints", compact=True):
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
                f"The Z ladder stays within +/-1mm of the current pen-down depth (never past "
                f"{Z_ABSOLUTE_FLOOR_MM:g}mm); written to the spool as pen_cal_<profile>.gcode."
            )
            with toolbar():
                safe_action_button("GENERATE PEN CAL G-CODE", ctx.generate_pen_cal)
                primary_action_button("PRINT PEN CAL", ctx.print_pen_cal)
            ui.separator()
            helper_text(
                "Z range: sweeps pen-down depth from 0 to -12mm, then checks pen-up clearance by "
                "leaving a gap a dragging pen would mark. Use after a mechanics change, on a sheet "
                "you do not mind losing."
            )
            with toolbar():
                primary_action_button("PRINT Z RANGE", ctx.print_z_range)

        with card("Outline trace", compact=True):
            helper_text(
                "Walks the printable field, and the loaded SVG's own bounds, with the pen up. "
                "A minute of travel answers whether the drawing fits and whether the origin is "
                "where you think it is -- before hours of plotting say otherwise."
            )
            with toolbar():
                primary_action_button("TRACE OUTLINE", ctx.trace_outline)

        with card("SVG test draw", compact=True):
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
            file_upload("Drop an Inkscape SVG here, or click + to choose", ctx.handle_svg_upload, accept=".svg")
            with ui.row().classes("items-center gap-2"):
                primary_action_button("START SVG PRINT", ctx.print_uploaded_svg)
                ctx.uploaded_svg_label = ui.label("No SVG selected").classes("path-label text-xs")
            helper_text("Use generated G-code first when validating layout or sampling changes.")
