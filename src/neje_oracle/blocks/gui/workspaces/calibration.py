"""Calibration workspace: motion, speed, grid/layout, organic, and advanced sampling.

One column, one builder. Motion controls come from the shared `motion` card; all
handlers live on `ctx`.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from nicegui import ui

from ....shared.gui_settings import NumericGuiDefaultKey
from ....shared.origin_markers import ALL_ORIGINS, ORIGIN_LABELS
from ....shared.pen_profiles import (
    PEN_PROFILE_FIELDS,
    apply_pen_profile,
    capture_pen_profile,
    load_pen_profiles,
    profile_matches,
    save_pen_profiles,
)
from ..context import GuiContext
from ..support import GUI_DEFAULTS
from ..ui import helper_text, mini_metric, number_control, primary_action_button
from .motion import render_motion_panel


def build(ctx: GuiContext) -> None:
    settings = ctx.settings
    fields = ctx.fields
    scales = ctx.scales
    gcode_labels = ctx.gcode_labels
    persist_and_refresh = ctx.persist_and_refresh

    def calibration_slider_row(
        label: str,
        key: str,
        *,
        value: float,
        default: float,
        min_value: float,
        max_value: float,
        step: float,
        on_change: Callable,
    ) -> Any:
        with ui.grid(columns="135px 1fr 74px 28px 28px").classes("w-full items-center gap-2"):
            helper_text(label)
            control = (
                ui.slider(min=min_value, max=max_value, step=step, value=value)
                .props("dense")
                .classes("w-full tight-slider")
            )
            number = (
                ui.number(value=value, min=min_value, max=max_value, step=step)
                .props("dense outlined")
                .classes("w-full")
            )

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

    def num(
        key: NumericGuiDefaultKey,
        label: str,
        value: float,
        min_value: float,
        tooltip: str,
        *,
        step: float = 1.0,
    ) -> None:
        number_control(
            fields,
            key,
            label=label,
            value=value,
            default=float(GUI_DEFAULTS.get(key, min_value)),
            min_value=min_value,
            step=step,
            width_class="w-full",
            tooltip=tooltip,
            on_change=persist_and_refresh,
        )

    with ui.column().classes("workspace-scroll gap-2"):
        # Manual motion (shared card)
        render_motion_panel(ctx)

        # Motion speed
        with ui.card().classes("oracle-card compact-card w-full"):
            ui.label("Motion speed").classes("text-sm font-bold")
            helper_text(
                "XY speed writes G-code feed rates in mm/min. Acceleration uses the controller's saved FluidNC settings."
            )
            with ui.grid(columns=2).classes("w-full gap-2"):
                number_control(
                    fields,
                    "travel_rate",
                    label="Travel mm/min",
                    value=settings.travel_rate,
                    default=5000,
                    min_value=1,
                    width_class="w-full",
                    tooltip="Pen-up movement speed. Saved directly to G-code F.",
                    on_change=persist_and_refresh,
                )
                number_control(
                    fields,
                    "draw_rate",
                    label="Draw mm/min",
                    value=settings.draw_rate,
                    default=1800,
                    min_value=1,
                    width_class="w-full",
                    tooltip="Drawing movement speed. Saved directly to G-code F.",
                    on_change=persist_and_refresh,
                )
                number_control(
                    fields,
                    "xy_acceleration_mm_s2",
                    label="XY accel mm/s^2",
                    value=settings.xy_acceleration_mm_s2,
                    default=float(GUI_DEFAULTS["xy_acceleration_mm_s2"]),
                    min_value=0,
                    width_class="w-full",
                    tooltip="Recorded in manifests only. Print G-code uses the controller's saved acceleration settings.",
                    on_change=persist_and_refresh,
                )
                number_control(
                    fields,
                    "z_up_mm",
                    label="Pen-up Z (mm)",
                    value=settings.z_up_mm,
                    default=0,
                    min_value=-25,
                    width_class="w-full",
                    tooltip="Height the pen lifts to between strokes. Emitted as G0 Z when the Z servo is in use.",
                    on_change=persist_and_refresh,
                )
                number_control(
                    fields,
                    "z_down_mm",
                    label="Pen-down Z (mm)",
                    value=settings.z_down_mm,
                    default=-25,
                    min_value=-25,
                    width_class="w-full",
                    tooltip="Pen pressure: how far the pen presses into the paper. Too shallow leaves gaps, too deep splays the nib.",
                    on_change=persist_and_refresh,
                )
                number_control(
                    fields,
                    "z_feed_mm_min",
                    label="Z mm/min",
                    value=settings.z_feed_mm_min,
                    default=1000,
                    min_value=1,
                    width_class="w-full",
                    tooltip="Z servo axis feed rate. FluidNC maps this Z axis to PWM.",
                    on_change=persist_and_refresh,
                )
                number_control(
                    fields,
                    "pen_width_mm",
                    label="Pen width mm",
                    value=settings.pen_width_mm,
                    default=float(GUI_DEFAULTS["pen_width_mm"]),
                    min_value=0.05,
                    step=0.05,
                    width_class="w-full",
                    tooltip="Measured nib width. Sets stroke weight and the finest detail the image modes will attempt.",
                    on_change=persist_and_refresh,
                )
                number_control(
                    fields,
                    "pen_down_dwell_ms",
                    label="Pen-down dwell ms",
                    value=settings.pen_down_dwell_ms,
                    default=float(GUI_DEFAULTS["pen_down_dwell_ms"]),
                    min_value=0,
                    step=10,
                    width_class="w-full",
                    tooltip="Pause after the pen lands, before it moves. Gel and ballpoint ink needs this or stroke starts come out dry. 0 emits no dwell.",
                    on_change=persist_and_refresh,
                )

            _build_pen_profile_row(ctx)

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
                fields["layout_mode"] = (
                    ui.select(
                        {"grid": "Straight", "hex": "Hex"},
                        value=settings.layout_mode,
                        label="Layout",
                    )
                    .props("dense outlined")
                    .classes("w-32")
                    .on_value_change(persist_and_refresh)
                )
                fields["include_rings"] = ui.switch("Rings", value=settings.include_rings).on_value_change(
                    persist_and_refresh
                )
                fields["include_markers"] = ui.switch("Origin dots", value=settings.include_markers).on_value_change(
                    persist_and_refresh
                )
            with ui.grid(columns=2).classes("w-full gap-2"):
                num("sheet_width_mm", "Field W", settings.sheet_width_mm, 1, "Printable field width in mm.")
                num("sheet_height_mm", "Field H", settings.sheet_height_mm, 1, "Printable field height in mm.")
                num(
                    "cell_diameter_mm",
                    "Cell",
                    settings.cell_diameter_mm,
                    1,
                    "Packing cell diameter and grid step base.",
                )
                num("gap_mm", "Gap", settings.gap_mm, 0, "Distance between neighboring cell diameters.")
                num("sheet_margin_mm", "Margin", settings.sheet_margin_mm, 0, "Safe border inside printable field.")
                num("marker_diameter_mm", "Dot mm", settings.marker_diameter_mm, 0.5, "Printed origin-dot diameter.")

        # Organic / Voronoi
        with ui.card().classes("oracle-card compact-card w-full"):
            with ui.row().classes("items-center gap-2"):
                fields["organic_enabled"] = ui.switch(
                    "Organic / Voronoi", value=settings.organic_enabled
                ).on_value_change(persist_and_refresh)
            with ui.grid(columns=2).classes("w-full gap-2"):
                num(
                    "organic_cell_size_mm",
                    "Voronoi cell",
                    settings.organic_cell_size_mm,
                    0,
                    "Maximum organic position drift in mm.",
                    step=1,
                )
                num(
                    "organic_seed",
                    "Seed",
                    settings.organic_seed,
                    1,
                    "Repeats the same organic layout for preview and print.",
                    step=1,
                )
            calibration_slider_row(
                "Rotation ramp",
                "organic_rotation_ramp",
                value=settings.organic_rotation_ramp,
                default=float(GUI_DEFAULTS.get("organic_rotation_ramp", 0)),
                min_value=0,
                max_value=1,
                step=0.01,
                on_change=persist_and_refresh,
            )
            calibration_slider_row(
                "Scale ramp",
                "organic_scale_ramp",
                value=settings.organic_scale_ramp,
                default=float(GUI_DEFAULTS.get("organic_scale_ramp", 0)),
                min_value=0,
                max_value=1,
                step=0.01,
                on_change=persist_and_refresh,
            )

        # Advanced
        with ui.expansion("Advanced calibration", icon="tune").classes("oracle-card compact-card w-full"):
            helper_text(
                "Use these controls for curve sampling, origin filters, and symbol correction after the physical layout is stable."
            )
            ui.label("Drawing detail").classes("text-sm font-bold")
            helper_text(
                "Sets how many G-code points are generated from SVG curves. Smaller spacing is smoother and slower; larger spacing is lighter and faster."
            )
            with ui.grid(columns=3).classes("w-full gap-1"):
                for key, label in (
                    ("effective", "Active spacing"),
                    ("points", "Path density"),
                    ("load", "G-code load"),
                ):
                    gcode_labels[key] = mini_metric(label)
            ui.label("Main detail").classes("text-[10px] font-bold text-[#8f4f2b] uppercase")
            num(
                "sample_step_mm",
                "Spacing at normal cell size (mm)",
                settings.sample_step_mm,
                0.05,
                "Distance between sampled points for an 80 mm reference cell.",
                step=0.05,
            )
            ui.label("Auto-adjust for cell size").classes("text-[10px] font-bold text-[#8f4f2b] uppercase")
            num(
                "sample_density_exponent",
                "Auto density strength",
                settings.sample_density_exponent,
                0.0,
                "0 disables cell-size compensation. 1 is normal. Higher values make large cells denser.",
                step=0.1,
            )
            with ui.row().classes("items-center gap-2"):
                ui.label("Clamp").classes("text-[10px] font-bold text-[#8f4f2b] uppercase")
                gcode_labels["limits"] = ui.label("-").classes("text-xs text-[#8f4f2b]")
            with ui.grid(columns=2).classes("w-full gap-2"):
                num(
                    "sample_min_step_mm",
                    "Finest allowed spacing",
                    settings.sample_min_step_mm,
                    0.01,
                    "Lower safety limit. Prevents extremely dense G-code.",
                    step=0.01,
                )
                num(
                    "sample_max_step_mm",
                    "Coarsest allowed spacing",
                    settings.sample_max_step_mm,
                    0.05,
                    "Upper safety limit. Prevents overly simplified curves.",
                    step=0.05,
                )
            fields["streaming_mode"] = (
                ui.select(
                    {"row": "Row at a time", "cell": "Cell at a time"},
                    value=settings.streaming_mode,
                    label="Send to FluidNC",
                )
                .props("dense outlined")
                .classes("w-full")
                .on_value_change(persist_and_refresh)
            )
            ctx.update_gcode_detail_labels()

            ui.label("Filters / markers").classes("text-sm font-bold")
            helper_text(
                "Display filters affect preview immediately. Print filters apply from the next row, never mid-row."
            )
            # The two columns do different jobs and reading them as a pair misleads: Preview
            # only hides cells on screen, and Print only decides which remote job origins may
            # be claimed. Filler is the fallback that completes every sheet either way, so
            # unchecking its Print box does not stop it reaching paper.
            helper_text("Preview hides cells on screen only. Print selects claimable job origins; filler always fills.")
            with ui.grid(columns=3).classes("w-full gap-1"):
                ui.label("Origin").classes("text-[10px] font-bold text-[#8f4f2b]")
                ui.label("Preview").classes("text-[10px] font-bold text-[#8f4f2b]")
                ui.label("Print").classes("text-[10px] font-bold text-[#8f4f2b]")
                for origin in ALL_ORIGINS:
                    ui.label(ORIGIN_LABELS[origin]).classes("text-xs")
                    fields[f"show_origin:{origin}"] = (
                        ui.checkbox(value=origin in settings.show_origins)
                        .props("dense")
                        .on_value_change(persist_and_refresh)
                    )
                    fields[f"print_origin:{origin}"] = (
                        ui.checkbox(value=origin in settings.print_origins)
                        .props("dense")
                        .on_value_change(persist_and_refresh)
                    )

            ui.label("Symbol scale correction").classes("text-sm font-bold")
            helper_text("Global scale multiplies every per-symbol scale, on screen and on paper.")
            # ponytail: Random coarse/fine are read by nothing but this card -- the jitter that
            # reaches paper is baked in by session_generator from its own defaults. Left in
            # place and labelled rather than deleted; wire them to the generator or drop them.
            helper_text("Random coarse/fine do not reach the plotter yet -- they change no output.")
            calibration_slider_row(
                "Random coarse",
                "randomness",
                value=settings.randomness,
                default=float(GUI_DEFAULTS.get("randomness", 0)),
                min_value=0,
                max_value=100,
                step=1,
                on_change=persist_and_refresh,
            )
            calibration_slider_row(
                "Random fine",
                "randomness_fine",
                value=settings.randomness_fine,
                default=float(GUI_DEFAULTS.get("randomness_fine", 0)),
                min_value=-10,
                max_value=10,
                step=0.1,
                on_change=persist_and_refresh,
            )
            calibration_slider_row(
                "Global scale",
                "global_scale",
                value=settings.global_scale,
                default=1.0,
                min_value=0.3,
                max_value=3.0,
                step=0.01,
                on_change=persist_and_refresh,
            )
            helper_text(
                "Double-click any scale slider to reset it to 1.0. Scale changes are applied and saved immediately."
            )
            with ui.column().classes("w-full gap-0"):
                for symbol in ctx.symbols:
                    calibration_slider_row(
                        symbol.stem[:20],
                        f"scale:{symbol.name}",
                        value=scales.get(symbol.name, 1.0),
                        default=1.0,
                        min_value=0.3,
                        max_value=5.0,
                        step=0.01,
                        on_change=ctx.update_scales_from_fields,
                    )


def _build_pen_profile_row(ctx: GuiContext) -> None:
    """Pen profile picker and save-as, beside the settings a profile actually carries.

    Selecting a profile overwrites only PEN_PROFILE_FIELDS and pushes them live -- every
    control here autosaves through persist_and_refresh, which writes the settings JSON
    and the runtime store, so the plotter daemon sees a pen change without a restart.
    """
    profiles = load_pen_profiles()

    # flex-wrap: this row needs ~796px (helper + modified label + select + name + button)
    # in a column that is 622px at 1200px wide, and .workspace-scroll clips overflow-x
    # with no scrollbar -- so SAVE AS PROFILE was simply invisible below ~1360px.
    with ui.row().classes("w-full items-center gap-2 mt-2 flex-wrap"):
        helper_text("Pen profile")
        modified_label = ui.label("").classes("text-xs text-[#8f4f2b]")

        def refresh_modified() -> None:
            current = ctx.settings.pen_profile
            dirty = bool(current) and not profile_matches(ctx.settings, current, profiles)
            modified_label.set_text(f"· {current} modified, not saved" if dirty else "")

        def apply_selected(name: str) -> None:
            if not name or name == ctx.settings.pen_profile:
                return
            # Applying overwrites every PEN_PROFILE_FIELDS value, so tuned-but-unsaved
            # numbers would vanish silently -- and typing numbers off the calibration
            # sheet before saving is exactly the loop RUNBOOK section 9 prescribes.
            previous = ctx.settings.pen_profile
            if previous and not profile_matches(ctx.settings, previous, profiles):
                profile_select.value = previous
                profile_select.update()
                ui.notify(
                    f"'{previous}' has unsaved changes. SAVE AS PROFILE first, or rename to keep both.",
                    color="warning",
                )
                return
            try:
                apply_pen_profile(ctx.settings, name, profiles)
            except ValueError as exc:
                ui.notify(str(exc), color="negative")
                return
            # Push the profile's values into the widgets first: persist_and_refresh reads
            # back from ctx.fields, so writing only ctx.settings would be overwritten.
            for pen_field in PEN_PROFILE_FIELDS:
                control = ctx.fields.get(pen_field)
                if control is not None:
                    control.value = getattr(ctx.settings, pen_field)
            ctx.persist_and_refresh()
            refresh_modified()
            ui.notify(f"Pen profile '{name}' applied", color="positive")

        profile_select = (
            ui.select(
                sorted(profiles),
                value=ctx.settings.pen_profile or None,
                label="Fitted pen",
                on_change=lambda e: apply_selected(str(e.value or "")),
            )
            .props("dense outlined")
            .classes("w-44")
        )
        name_input = ui.input("Save as", value=ctx.settings.pen_profile).props("dense outlined").classes("w-40")

        def save_current() -> None:
            name = str(name_input.value or "").strip()
            if not name:
                ui.notify("Name the profile before saving", color="warning")
                return
            # Pull the widgets into settings first, so an untyped-but-unsaved edit in a
            # number box is captured rather than silently dropped.
            ctx.pull_settings_from_fields()
            profiles[name] = capture_pen_profile(ctx.settings)
            save_pen_profiles(profiles)
            ctx.settings.pen_profile = name
            # The profile file was written but gui_settings.json was not, so which pen is
            # fitted was lost on reload until some unrelated control happened to save.
            ctx.persist_and_refresh()
            profile_select.options = sorted(profiles)
            profile_select.value = name
            profile_select.update()
            refresh_modified()
            ui.notify(f"Saved pen profile '{name}'", color="positive")

        primary_action_button("SAVE AS PROFILE", lambda: save_current())

    # Subscribe to the pen controls rather than polling on a timer. The 2s ui.timer this
    # replaces kept firing after its slot was torn down on client disconnect -- one browser
    # session left 24 "The parent slot of Timer(...) has been deleted" errors in the log.
    # These controls already run persist_and_refresh on change and it is registered first,
    # so ctx.settings is current by the time this handler sees it.
    for pen_field in PEN_PROFILE_FIELDS:
        control = ctx.fields.get(pen_field)
        if control is not None:
            control.on_value_change(lambda: refresh_modified())
    refresh_modified()

    helper_text(
        "Shipped values are starting points, not measurements. Print the pen calibration sheet "
        "on the TESTS tab, read the best rung off each ladder, then save the result here."
    )
