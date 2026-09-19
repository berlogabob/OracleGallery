"""Calibration workspace: motion, speed, grid/layout, organic, and advanced sampling.

One column, one builder. Motion controls come from the shared `motion` card; all
handlers live on `ctx`.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from nicegui import ui

from ....shared.gui_settings import NumericGuiDefaultKey
from ....shared.materials import (
    apply_material,
    capture_material,
    delete_material,
    load_materials,
    save_materials,
)
from ....shared.origin_markers import ALL_ORIGINS, ORIGIN_LABELS
from ....shared.pen_profiles import (
    PEN_PROFILE_FIELDS,
    apply_pen_profile,
    capture_pen_profile,
    delete_pen_profile,
    load_pen_profiles,
    profile_matches,
    rename_pen_profile,
    save_pen_profiles,
)
from ....shared.z_positions import is_measured, mm_per_us, real_mm_between
from ..context import GuiContext
from ..support import GUI_DEFAULTS
from ..ui import (
    Section,
    card,
    danger_action_button,
    helper_text,
    micro_label,
    mini_metric,
    nudge_button,
    number_control,
    primary_action_button,
    safe_action_button,
    select,
    toolbar,
)


def build_sections(ctx: GuiContext) -> dict[str, Section]:
    """Build the calibration content as three sections and hand back their containers.

    The SETUP screen shows one section at a time behind a segmented switch, which is how
    2000px of stacked calibration fits a 760px viewport with zero page scroll. Everything
    is still *built* -- every field registers, persistence and the workspace tests see the
    identical control set -- only visibility is segmented.
    """
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
            nudge_button("-", lambda: nudge(-step))
            nudge_button("+", lambda: nudge(step))
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

    sections: dict[str, Any] = {}
    with ui.column().classes("w-full gap-2"):
        # -- PEN: feeds, Z, pen geometry, profiles -----------------------------------
        sections["pen"] = ui.column().classes("w-full gap-2")
        with sections["pen"], card("Motion speed", compact=True):
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
                    tooltip=(
                        "Must match the controller's saved X/Y acceleration -- used for plot-time estimates. "
                        "Print G-code always uses the controller's own saved acceleration; this setting does not "
                        "change the board."
                    ),
                    on_change=persist_and_refresh,
                )
                # z_up_mm / z_down_mm / z_fix_mm used to live here as editable fields. They
                # are DERIVED now (sync_z_from_pulses, from the five microsecond positions
                # below), so a widget here would edit a number the next save overwrites --
                # see the "Z positions (us)" card, which is where they actually get tuned.
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

        with sections["pen"]:
            # Tune first, then the table: the jog-and-capture loop is what an operator runs
            # to FIND a position, and the table below is where the result lands.
            _build_z_tune_card(ctx)
            _build_z_positions_card(ctx)

        # -- SHEET: layout geometry + organic ----------------------------------------
        sections["sheet"] = ui.column().classes("w-full gap-2")
        with sections["sheet"], card(compact=True):
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
                num("sheet_width_mm", "Field W mm", settings.sheet_width_mm, 1, "Printable field width in mm.")
                num("sheet_height_mm", "Field H mm", settings.sheet_height_mm, 1, "Printable field height in mm.")
                num(
                    "cell_diameter_mm",
                    "Cell",
                    settings.cell_diameter_mm,
                    1,
                    "Packing cell diameter and grid step base.",
                )
                num("gap_mm", "Gap mm", settings.gap_mm, 0, "Distance between neighboring cell diameters.")
                num("sheet_margin_mm", "Margin mm", settings.sheet_margin_mm, 0, "Safe border inside printable field.")
                num("marker_diameter_mm", "Dot mm", settings.marker_diameter_mm, 0.5, "Printed origin-dot diameter.")

        with sections["sheet"], card(compact=True):
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

        # -- ADVANCED: sampling, filters, symbol correction --------------------------
        # A plain section now; it used to be an expansion, but inside a segmented switch a
        # second layer of fold-away is exactly the accordion-inside-tabs anti-pattern.
        sections["advanced"] = ui.column().classes("w-full gap-2")
        with sections["advanced"], card(compact=True):
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
            micro_label("Main detail")
            num(
                "sample_step_mm",
                "Spacing at normal cell size (mm)",
                settings.sample_step_mm,
                0.05,
                "Distance between sampled points for an 80 mm reference cell.",
                step=0.05,
            )
            micro_label("Auto-adjust for cell size")
            num(
                "sample_density_exponent",
                "Auto density strength",
                settings.sample_density_exponent,
                0.0,
                "0 disables cell-size compensation. 1 is normal. Higher values make large cells denser.",
                step=0.1,
            )
            with ui.row().classes("items-center gap-2"):
                micro_label("Clamp")
                gcode_labels["limits"] = helper_text("-")
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
                micro_label("Origin")
                micro_label("Preview")
                micro_label("Print")
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
            helper_text("Random coarse/fine scale the organic layout scatter on paper. 35 / 0 = as shipped.")
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
            # One slider per symbol used to render as a wall -- unbounded rows, most of the
            # Advanced section's height. Every row is still built (the scale: fields are the
            # persistence contract), but only the selected symbol's row is visible.
            symbol_rows: dict[str, Any] = {}
            with ui.column().classes("w-full gap-0"):
                picker = ui.select(
                    {symbol.name: symbol.stem[:30] for symbol in ctx.symbols},
                    value=ctx.symbols[0].name if ctx.symbols else None,
                    label="Symbol",
                    with_input=True,
                ).props("dense outlined")
                for symbol in ctx.symbols:
                    row = ui.column().classes("w-full")
                    with row:
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
                    symbol_rows[symbol.name] = row

                def show_symbol(name: object) -> None:
                    for key, box in symbol_rows.items():
                        box.set_visibility(key == name)

                picker.on_value_change(lambda e: show_symbol(e.value))
                show_symbol(picker.value)

    return {name: Section(root=container) for name, container in sections.items()}


# Leash for hand-editing a pulse field, matching the tuner's own guard against a stuck
# key walking the servo into a stall (scripts/z_servo_tune.py:52-56). number_control has
# no max_value parameter, so the ceiling is added as a Quasar prop after construction.
_PULSE_FLOOR_US = 400
_PULSE_CEILING_US = 2600


def _build_z_positions_card(ctx: GuiContext) -> None:
    """The five named Z positions, in the servo microseconds the operator actually tunes.

    z_up_mm / z_down_mm / z_fix_mm are DERIVED from these (sync_z_from_pulses), so this is
    the card that matters. Five, not two, because parking the servo on its bottom mechanical
    stop to draw is a stall -- it killed a servo on 2026-08-31 -- and "bottom soft" exists so
    the holder's spring takes the last of the pressure instead.

    Every row carries the same columns (real mm below pen-up, the pulse, GO TO, SET), so the
    table reads down a column: what the operator compares is one position against the next,
    and a row missing a control breaks that scan.

    The machine's own Z millimetres are deliberately not shown anywhere. They are an
    interpolation across a made-up 25-unit travel, so a row reading "-16.7 mm" invites the
    operator to measure it against a rule and find it wrong. Only two units are real here:
    the microseconds the servo takes, and the millimetres measured off the nib.
    """
    if not ctx.supervisor.plotter_settings.use_z_servo:
        # Same self-explaining stand-in as the Z tune card: no servo, nothing to tune.
        with card(
            "Z positions (us)",
            "Needs the Z servo (NEJE_PLOTTER_USE_Z_SERVO). This machine drives the pen as an on/off solenoid.",
        ):
            pass
        return

    settings = ctx.settings
    fields = ctx.fields
    rows: list[tuple[str, Callable[[], None]]] = []

    def pulse_of(key: str) -> float:
        # Falls back to the stored value: the rows build top-down and each one's real-mm
        # column is measured against pen-up, which the first row reaches before its widget
        # exists.
        control = fields.get(key)
        return float(control.value if control is not None else getattr(ctx.settings, key)) or 0.0

    def build_row(key: str, label: str, tooltip: str) -> None:
        with toolbar(full_width=True):
            real_label = mini_metric("mm")

            def refresh_label() -> None:
                # Real travel is measured DOWN from pen-up: that is the number an operator
                # checks against a rule and against the thickness of what is on the bed.
                real = real_mm_between(
                    pulse_of("z_top_soft_us"), pulse_of(key), ctx.settings.z_real_span_mm, ctx.settings.z_real_span_us
                )
                # A dash, not a zero: until the sweep below is measured there is no scale, and
                # a plausible-looking millimetre is the one number an operator would act on.
                real_label.set_text("-" if real is None else f"{real:+.2f}")

            def on_change() -> None:
                # commit_z_position reverts the widget itself on refusal, so the labels
                # always end up showing whatever value actually won.
                ctx.commit_z_position(key)
                for _, refresh in rows:
                    refresh()

            number_control(
                fields,
                key,
                label=label,
                value=getattr(settings, key),
                default=float(GUI_DEFAULTS[key]),
                min_value=_PULSE_FLOOR_US,
                step=1,
                width_class="w-40",
                tooltip=tooltip,
                on_change=on_change,
            ).props(f"max={_PULSE_CEILING_US}")
            safe_action_button("GO TO", lambda key=key: ctx.goto_z_position(key)).tooltip(f"Move the servo to {label}.")
            safe_action_button("SET", lambda key=key: ctx.capture_z_us(key)).tooltip(
                f"Store the machine's current Z as {label}."
            )
            rows.append((key, refresh_label))
            refresh_label()

    with card(
        "Z positions (us)",
        "Top to bottom, with each position's real travel below pen-up. The two mechanical "
        "marks are what the operator measures against; only the three between them are used "
        "when plotting.",
    ):
        build_row(
            "z_top_mech_us",
            "Top mechanical",
            "The limit above pen-up: past it the linkage can cross over and lock. Measured, not plotted with.",
        )
        build_row(
            "z_top_soft_us",
            "Top soft (pen-up)",
            "Where the pen parks between strokes, and where homing leaves the axis. Every "
            "stroke pays this height twice, and lifts are about half of this machine's plot time.",
        )
        build_row(
            "z_load_us",
            "Pen load",
            "Park position for getting a pen in and out of the holder. Rises with the material on the bed.",
        )
        build_row(
            "z_bottom_soft_us",
            "Bottom soft (drawing)",
            "Where the servo stops to draw, short of the mechanical floor, so the holder's "
            "spring gives the last of the pressure instead of stalling the servo.",
        )
        build_row(
            "z_bottom_mech_us",
            "Bottom mechanical",
            "The floor: past this the arm is square to the body and something breaks. GO TO it "
            "only to measure, and never with a pen fitted.",
        )

        micro_label(
            "Scale: GO TO pen-up, measure the nib against a rule, GO TO bottom soft, measure "
            "again, type the difference. Until you do, the mm column stays blank -- this servo "
            "has never been measured and nothing here can guess it."
        )
        with toolbar(full_width=True):
            scale_label = mini_metric("mm per 100us")

            def refresh_scale() -> None:
                measured = is_measured(ctx.settings.z_real_span_mm, ctx.settings.z_real_span_us)
                scale_label.set_text(
                    f"{mm_per_us(ctx.settings.z_real_span_mm, ctx.settings.z_real_span_us) * 100:.2f}"
                    if measured
                    else "not measured"
                )
                span_label.set_text(f"over {int(abs(ctx.settings.z_real_span_us))}us" if measured else "")
                material_note.set_text(
                    ""
                    if measured
                    else "A thickness needs the scale above: measure the sweep first, or set the "
                    "drawing position by hand."
                )
                for _, refresh in rows:
                    refresh()

            def on_span_change() -> None:
                # The sweep the number describes is the one currently between the two soft
                # positions, so the span in microseconds is recorded with it: change a
                # position later and the old measurement still means what it meant.
                settings.z_real_span_mm = float(fields["z_real_span_mm"].value or 0.0)
                settings.z_real_span_us = max(1, int(abs(pulse_of("z_bottom_soft_us") - pulse_of("z_top_soft_us"))))
                ctx.persist_and_refresh()
                refresh_scale()

            number_control(
                fields,
                "z_real_span_mm",
                label="Measured sweep mm",
                value=float(settings.z_real_span_mm),
                default=float(GUI_DEFAULTS["z_real_span_mm"]),
                min_value=0,
                step=0.1,
                width_class="w-40",
                tooltip="Real pen travel between pen-up and bottom soft, off a rule. Nothing "
                "derives this: the linkage turns a linear pulse ramp into an arc, so the only "
                "honest number is the one you measured on this machine.",
                on_change=on_span_change,
            )
            span_label = micro_label("")

        material_note = micro_label("")
        _build_material_row(ctx, refresh_scale)
        refresh_scale()


def _build_material_row(ctx: GuiContext, on_change: Callable[[], None]) -> None:
    """What is on the bed, as a thickness that lifts the drawing and pen-load positions.

    A silicone mat or a sheet of card raises the surface the pen meets, so without this the
    operator re-tunes bottom soft every time the bed changes. Pen-up deliberately does not
    move: it is referenced to the machine, and lifting it for every sheet of card would add
    pen-lift time to every stroke of every plot.
    """
    settings = ctx.settings
    materials = load_materials()

    def apply_named(name: str) -> None:
        if not name or name == settings.z_material:
            return
        try:
            thickness = apply_material(name, materials)
        except ValueError as exc:
            ui.notify(str(exc), color="negative")
            return
        settings.z_material = name
        settings.z_material_mm = thickness
        thickness_field.value = thickness
        thickness_field.update()
        ctx.persist_and_refresh()
        on_change()
        ui.notify(f"Material '{name}' applied: {thickness:g} mm", color="positive")

    with toolbar(full_width=True):
        material_select = select(
            {name: f"{name} ({values['thickness_mm']:g} mm)" for name, values in sorted(materials.items())},
            value=settings.z_material or None,
            label="On the bed",
            on_change=lambda event: apply_named(str(event.value or "")),
        )
        thickness_field = number_control(
            ctx.fields,
            "z_material_mm",
            label="Thickness mm",
            value=float(settings.z_material_mm),
            default=float(GUI_DEFAULTS["z_material_mm"]),
            min_value=0,
            step=0.1,
            width_class="w-36",
            tooltip="How much the bed has risen. Drawing and pen load lift by this much; pen-up does not.",
            on_change=lambda: (
                setattr(settings, "z_material_mm", float(ctx.fields["z_material_mm"].value or 0.0)),
                ctx.persist_and_refresh(),
                on_change(),
            ),
        )
        name_input = ui.input("Save as", value=settings.z_material).props("dense outlined").classes("w-36")

        def save_current() -> None:
            name = str(name_input.value or "").strip()
            if not name:
                ui.notify("Name the material before saving", color="warning")
                return
            materials[name] = capture_material(float(settings.z_material_mm))
            save_materials(materials)
            settings.z_material = name
            ctx.persist_and_refresh()
            material_select.options = {
                key: f"{key} ({values['thickness_mm']:g} mm)" for key, values in sorted(materials.items())
            }
            material_select.value = name
            material_select.update()
            ui.notify(f"Saved material '{name}'", color="positive")

        def delete_current() -> None:
            current = settings.z_material
            try:
                remaining = delete_material(current, materials)
            except ValueError as exc:
                ui.notify(str(exc), color="warning")
                return
            materials.clear()
            materials.update(remaining)
            settings.z_material = ""
            ctx.persist_and_refresh()
            material_select.options = {
                key: f"{key} ({values['thickness_mm']:g} mm)" for key, values in sorted(materials.items())
            }
            material_select.value = None
            material_select.update()
            ui.notify(f"Deleted material '{current}'", color="positive")

        primary_action_button("SAVE MATERIAL", save_current)
        danger_action_button(
            "DELETE",
            lambda: ctx.confirm_action(
                "DELETE MATERIAL",
                f"Removes '{ctx.settings.z_material}' from the material library. The thickness on the bed stays as it is.",
                delete_current,
            ),
        )


def _build_z_tune_card(ctx: GuiContext) -> None:
    """Interactive Z calibration: step the servo, read the machine Z, capture it.

    Replaces the plot-a-ladder-sheet loop for finding the soft positions: jog until the
    nib just marks, SET AS BOTTOM SOFT; jog to the shallowest clean clearance, SET AS TOP
    SOFT. Both land in the "Z positions (us)" fields above, so SAVE AS PROFILE keeps them.
    """
    if not ctx.supervisor.plotter_settings.use_z_servo:
        # With use_z_servo off, Z is a binary M5/M3 pen solenoid: there is no position
        # to jog or capture, so the card explains itself instead of offering dead buttons.
        with card(
            "Z tune",
            "Z jogging needs the Z servo (NEJE_PLOTTER_USE_Z_SERVO). This machine drives the pen as an on/off solenoid.",
        ):
            pass
        return
    with card(
        "Z tune",
        "Jog Z until the nib just marks the paper, then SET AS BOTTOM SOFT. "
        "Jog up to the shallowest height that clears the paper, then SET AS TOP SOFT. "
        "SAVE AS PROFILE above keeps both. The readout is the pulse the servo is holding "
        "and how far below pen-up that really is.",
    ):
        with toolbar(full_width=True):
            # The tuner's own ladder (scripts/z_servo_tune.py): an SG90's dead band is 5-10us,
            # so 1 and 2 are for settling a position and 10-50 for finding it.
            ctx.fields["z_step"] = select(
                {1: "1", 2: "2", 5: "5", 10: "10", 20: "20", 50: "50"}, value=10, label="Z step us"
            )
            safe_action_button("Z+", ctx.jog_z_up).tooltip("Raise the pen by one step")
            safe_action_button("Z−", ctx.jog_z_down).tooltip("Lower the pen by one step")
            ctx.machine_z_label = mini_metric("us")
            ctx.machine_real_mm_label = mini_metric("mm below pen-up")
        with toolbar(full_width=True):
            safe_action_button("SET AS BOTTOM SOFT", lambda: ctx.capture_z_us("z_bottom_soft_us")).tooltip(
                "Current machine Z becomes Bottom soft (us), converted through pulse_for_z"
            )
            safe_action_button("SET AS TOP SOFT", lambda: ctx.capture_z_us("z_top_soft_us")).tooltip(
                "Current machine Z becomes Top soft (us), converted through pulse_for_z"
            )
            safe_action_button("SET AS PEN LOAD", lambda: ctx.capture_z_us("z_load_us")).tooltip(
                "Current machine Z becomes Pen load (us) -- where the holder clamps the pen"
            )
            safe_action_button("GO TO LOAD", ctx.goto_load).tooltip(
                "Move to the saved Pen load position. Put the calibration plate down first; keep the canvas clear."
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
        modified_label = helper_text("")

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

        def rename_current() -> None:
            current = ctx.settings.pen_profile
            name = str(name_input.value or "").strip()
            if not current:
                ui.notify("Select the fitted pen before renaming", color="warning")
                return
            try:
                renamed = rename_pen_profile(current, name, profiles)
            except ValueError as exc:
                ui.notify(str(exc), color="warning")
                return
            profiles.clear()
            profiles.update(renamed)
            ctx.settings.pen_profile = name
            ctx.persist_and_refresh()
            profile_select.options = sorted(profiles)
            profile_select.value = name
            profile_select.update()
            refresh_modified()
            ui.notify(f"Renamed to '{name}'", color="positive")

        def delete_current() -> None:
            current = ctx.settings.pen_profile
            if not current:
                ui.notify("Select the fitted pen before deleting", color="warning")
                return
            try:
                remaining = delete_pen_profile(current, profiles)
            except ValueError as exc:
                ui.notify(str(exc), color="warning")
                return
            profiles.clear()
            profiles.update(remaining)
            # The live values stay exactly as they are -- they simply stop claiming to be
            # that pen. Nothing about the fitted instrument changed by deleting a label.
            ctx.settings.pen_profile = ""
            ctx.persist_and_refresh()
            profile_select.options = sorted(profiles)
            profile_select.value = None
            profile_select.update()
            refresh_modified()
            ui.notify(f"Deleted pen profile '{current}'", color="positive")

        primary_action_button("SAVE AS PROFILE", lambda: save_current())
        safe_action_button("RENAME", lambda: rename_current())
        # Behind a confirm: the numbers in a profile cost a printed sheet and a read-off to
        # find, and nothing else in the app holds a copy of them.
        danger_action_button(
            "DELETE",
            lambda: ctx.confirm_action(
                "DELETE PEN PROFILE",
                f"Deletes '{ctx.settings.pen_profile}' from the pen library. The fitted pen's live "
                "settings stay as they are. This cannot be undone.",
                delete_current,
            ),
        )

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
        "(Pen calibration, below), read the best rung off each ladder, then save the result here."
    )
