"""Calibration workspace: motion, speed, grid/layout, organic, and advanced sampling.

One column, one builder. Motion controls come from the shared `motion` card; all
handlers live on `ctx`.
"""

from __future__ import annotations

from typing import Any, Callable

from nicegui import ui

from ..context import GuiContext
from ..support import GUI_DEFAULTS
from ..ui import number_control
from .motion import render_motion_panel
from ....shared.origin_markers import ALL_ORIGINS, ORIGIN_LABELS


def build(ctx: GuiContext) -> None:
    settings = ctx.settings
    fields = ctx.fields
    scales = ctx.scales
    gcode_labels = ctx.gcode_labels
    persist_and_refresh = ctx.persist_and_refresh

    def calibration_slider_row(
        label: str, key: str, *, value: float, default: float,
        min_value: float, max_value: float, step: float, on_change: Callable,
    ) -> Any:
        with ui.grid(columns="135px 1fr 74px 28px 28px").classes("w-full items-center gap-2"):
            ui.label(label).classes("text-xs text-[#8f4f2b]")
            control = ui.slider(min=min_value, max=max_value, step=step, value=value).props("dense").classes("w-full tight-slider")
            number = ui.number(value=value, min=min_value, max=max_value, step=step).props("dense outlined").classes("w-full")

            def sync_from_slider() -> None:
                number.value = control.value
                number.update()
                on_change()

            def sync_from_number() -> None:
                control.value = number.value
                control.update()
                on_change()

            def nudge(delta: float) -> None:
                current = float(number.value or 0)
                next_value = max(min_value, min(max_value, current + delta))
                control.value = next_value
                number.value = next_value
                control.update()
                number.update()
                on_change()

            def reset() -> None:
                control.value = default
                number.value = default
                control.update()
                number.update()
                on_change()

            control.on_value_change(sync_from_slider)
            control.on("dblclick", lambda _: reset())
            number.on_value_change(sync_from_number)
            number.on("dblclick", lambda _: reset())
            ui.button("-", on_click=lambda: nudge(-step)).props("dense flat").classes("w-full")
            ui.button("+", on_click=lambda: nudge(step)).props("dense flat").classes("w-full")
            fields[key] = control
            return control

    def num(key: str, label: str, value: float, min_value: float, tooltip: str, *, step: float = 1.0) -> None:
        number_control(
            fields, key, label=label, value=value,
            default=float(GUI_DEFAULTS.get(key, min_value)),
            min_value=min_value, step=step, width_class="w-full", tooltip=tooltip,
            on_change=persist_and_refresh,
        )

    with ui.column().classes("workspace-scroll gap-2"):
        # Manual motion (shared card)
        render_motion_panel(ctx)

        # Motion speed
        with ui.card().classes("oracle-card compact-card w-full"):
            ui.label("Motion speed").classes("text-sm font-bold")
            ui.label("XY speed writes G-code feed rates in mm/min. Acceleration uses the controller's saved FluidNC settings.").classes("text-xs text-[#8f4f2b]")
            with ui.grid(columns=2).classes("w-full gap-2"):
                number_control(fields, "travel_rate", label="Travel mm/min", value=settings.travel_rate, default=5000, min_value=1, width_class="w-full", tooltip="Pen-up movement speed. Saved directly to G-code F.", on_change=persist_and_refresh)
                number_control(fields, "draw_rate", label="Draw mm/min", value=settings.draw_rate, default=1800, min_value=1, width_class="w-full", tooltip="Drawing movement speed. Saved directly to G-code F.", on_change=persist_and_refresh)
                number_control(fields, "xy_acceleration_mm_s2", label="XY accel mm/s^2", value=settings.xy_acceleration_mm_s2, default=float(GUI_DEFAULTS["xy_acceleration_mm_s2"]), min_value=0, width_class="w-full", tooltip="Recorded in manifests only. Print G-code uses the controller's saved acceleration settings.", on_change=persist_and_refresh)
                number_control(fields, "z_up_mm", label="Z up legacy", value=settings.z_up_mm, default=0, min_value=-25, width_class="w-full", tooltip="Legacy absolute Z-up value; current pen-up behavior uses Z homing.", on_change=persist_and_refresh)
                number_control(fields, "z_down_mm", label="Z down legacy", value=settings.z_down_mm, default=-25, min_value=-25, width_class="w-full", tooltip="Legacy value; current pen-down behavior is fixed at absolute G0 Z-25.", on_change=persist_and_refresh)
                number_control(fields, "z_feed_mm_min", label="Z mm/min", value=settings.z_feed_mm_min, default=1000, min_value=1, width_class="w-full", tooltip="Z servo axis feed rate. FluidNC maps this Z axis to PWM.", on_change=persist_and_refresh)

        # Layout
        with ui.card().classes("oracle-card compact-card w-full"):
            with ui.row().classes("w-full items-center justify-between"):
                ui.label("Layout").classes("text-sm font-bold")
                ctx.capacity_label = ui.label("-").classes("status-pill text-xs font-bold")
            ui.select(
                {"preview": "Preview tuning", "printing": "Printing live"},
                value=ctx.preview_mode["value"],
                label="Preview mode",
                on_change=lambda event: ctx.preview_mode_changed(event.value),
            ).props("dense outlined").classes("w-full")
            with ui.row().classes("items-end gap-2"):
                fields["layout_mode"] = ui.select(
                    {"grid": "Straight", "hex": "Hex"}, value=settings.layout_mode, label="Layout",
                ).props("dense outlined").classes("w-32").on_value_change(persist_and_refresh)
                fields["include_rings"] = ui.switch("Rings", value=settings.include_rings).on_value_change(persist_and_refresh)
                fields["include_markers"] = ui.switch("Origin dots", value=settings.include_markers).on_value_change(persist_and_refresh)
            with ui.grid(columns=2).classes("w-full gap-2"):
                num("sheet_width_mm", "Field W", settings.sheet_width_mm, 1, "Printable field width in mm.")
                num("sheet_height_mm", "Field H", settings.sheet_height_mm, 1, "Printable field height in mm.")
                num("cell_diameter_mm", "Cell", settings.cell_diameter_mm, 1, "Packing cell diameter and grid step base.")
                num("gap_mm", "Gap", settings.gap_mm, 0, "Distance between neighboring cell diameters.")
                num("sheet_margin_mm", "Margin", settings.sheet_margin_mm, 0, "Safe border inside printable field.")
                num("marker_diameter_mm", "Dot mm", settings.marker_diameter_mm, 0.5, "Printed origin-dot diameter.")

        # Organic / Voronoi
        with ui.card().classes("oracle-card compact-card w-full"):
            with ui.row().classes("items-center gap-2"):
                fields["organic_enabled"] = ui.switch("Organic / Voronoi", value=settings.organic_enabled).on_value_change(persist_and_refresh)
            with ui.grid(columns=2).classes("w-full gap-2"):
                num("organic_cell_size_mm", "Voronoi cell", settings.organic_cell_size_mm, 0, "Maximum organic position drift in mm.", step=1)
                num("organic_seed", "Seed", settings.organic_seed, 1, "Repeats the same organic layout for preview and print.", step=1)
            calibration_slider_row("Rotation ramp", "organic_rotation_ramp", value=settings.organic_rotation_ramp, default=float(GUI_DEFAULTS.get("organic_rotation_ramp", 0)), min_value=0, max_value=1, step=0.01, on_change=persist_and_refresh)
            calibration_slider_row("Scale ramp", "organic_scale_ramp", value=settings.organic_scale_ramp, default=float(GUI_DEFAULTS.get("organic_scale_ramp", 0)), min_value=0, max_value=1, step=0.01, on_change=persist_and_refresh)

        # Advanced
        with ui.expansion("Advanced calibration", icon="tune").classes("oracle-card compact-card w-full"):
            ui.label("Use these controls for curve sampling, origin filters, and symbol correction after the physical layout is stable.").classes("text-xs text-[#8f4f2b]")
            ui.label("Drawing detail").classes("text-sm font-bold")
            ui.label("Sets how many G-code points are generated from SVG curves. Smaller spacing is smoother and slower; larger spacing is lighter and faster.").classes("text-xs text-[#8f4f2b]")
            with ui.grid(columns=3).classes("w-full gap-1"):
                for key, label in (("effective", "Active spacing"), ("points", "Path density"), ("load", "G-code load")):
                    with ui.element("div").classes("mini-metric"):
                        ui.label(label).classes("label")
                        gcode_labels[key] = ui.label("-").classes("value")
            ui.label("Main detail").classes("text-[10px] font-bold text-[#8f4f2b] uppercase")
            num("sample_step_mm", "Spacing at normal cell size (mm)", settings.sample_step_mm, 0.05, "Distance between sampled points for an 80 mm reference cell.", step=0.05)
            ui.label("Auto-adjust for cell size").classes("text-[10px] font-bold text-[#8f4f2b] uppercase")
            num("sample_density_exponent", "Auto density strength", settings.sample_density_exponent, 0.0, "0 disables cell-size compensation. 1 is normal. Higher values make large cells denser.", step=0.1)
            with ui.row().classes("items-center gap-2"):
                ui.label("Clamp").classes("text-[10px] font-bold text-[#8f4f2b] uppercase")
                gcode_labels["limits"] = ui.label("-").classes("text-xs text-[#8f4f2b]")
            with ui.grid(columns=2).classes("w-full gap-2"):
                num("sample_min_step_mm", "Finest allowed spacing", settings.sample_min_step_mm, 0.01, "Lower safety limit. Prevents extremely dense G-code.", step=0.01)
                num("sample_max_step_mm", "Coarsest allowed spacing", settings.sample_max_step_mm, 0.05, "Upper safety limit. Prevents overly simplified curves.", step=0.05)
            fields["streaming_mode"] = ui.select(
                {"row": "Row at a time", "cell": "Cell at a time"}, value=settings.streaming_mode, label="Send to FluidNC",
            ).props("dense outlined").classes("w-full").on_value_change(persist_and_refresh)
            ctx.update_gcode_detail_labels()

            ui.label("Filters / markers").classes("text-sm font-bold")
            ui.label("Display filters affect preview immediately. Print filters apply from the next row, never mid-row.").classes("text-xs text-[#8f4f2b]")
            with ui.grid(columns=3).classes("w-full gap-1"):
                ui.label("Origin").classes("text-[10px] font-bold text-[#8f4f2b]")
                ui.label("Preview").classes("text-[10px] font-bold text-[#8f4f2b]")
                ui.label("Print").classes("text-[10px] font-bold text-[#8f4f2b]")
                for origin in ALL_ORIGINS:
                    ui.label(ORIGIN_LABELS[origin]).classes("text-xs")
                    fields[f"show_origin:{origin}"] = ui.checkbox(value=origin in settings.show_origins).props("dense").on_value_change(persist_and_refresh)
                    fields[f"print_origin:{origin}"] = ui.checkbox(value=origin in settings.print_origins).props("dense").on_value_change(persist_and_refresh)

            ui.label("Symbol scale correction").classes("text-sm font-bold")
            ui.label("These controls define how generated symbols will look before test generation and printing.").classes("text-xs text-[#8f4f2b]")
            calibration_slider_row("Random coarse", "randomness", value=settings.randomness, default=float(GUI_DEFAULTS.get("randomness", 0)), min_value=0, max_value=100, step=1, on_change=persist_and_refresh)
            calibration_slider_row("Random fine", "randomness_fine", value=settings.randomness_fine, default=float(GUI_DEFAULTS.get("randomness_fine", 0)), min_value=-10, max_value=10, step=0.1, on_change=persist_and_refresh)
            calibration_slider_row("Global scale", "global_scale", value=settings.global_scale, default=1.0, min_value=0.3, max_value=3.0, step=0.01, on_change=persist_and_refresh)
            ui.label("Double-click any scale slider to reset it to 1.0. Scale changes are applied and saved immediately.").classes("text-xs text-[#8f4f2b]")
            with ui.column().classes("w-full gap-0"):
                for symbol in ctx.symbols:
                    calibration_slider_row(
                        symbol.stem[:20], f"scale:{symbol.name}",
                        value=scales.get(symbol.name, 1.0), default=1.0,
                        min_value=0.3, max_value=5.0, step=0.01,
                        on_change=ctx.update_scales_from_fields,
                    )
