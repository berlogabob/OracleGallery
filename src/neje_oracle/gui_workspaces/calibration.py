"""Calibration workspace for the Oracle GUI.

The Calibration workspace handles grid configuration and layout tuning:
- Layout mode selection (grid vs hex)
- Field dimensions and cell sizing
- Organic/Voronoi pattern generation
- G-code sampling and curve detail
- Symbol origin filters
- Per-symbol scale correction
- Real-time preview updates
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from nicegui import ui

from ..gui_support import (
    GUI_DEFAULTS,
    build_preview_svg,
    build_realtime_preview_svg,
    compute_effective_sample_step,
    list_base_symbols,
    read_plotter_status,
    read_queue_status,
    save_gui_settings,
    save_oracle_plotter_config,
    save_symbol_scales,
)
from ..models import GUISettings, Symbol
from ..origin_markers import ALL_ORIGINS, ORIGIN_LABELS
from ..supervisor import SupervisorService


def build_calibration_workspace(
    supervisor: SupervisorService,
    settings: GUISettings,
    scales: dict[str, float],
    preview_mode_value: dict[str, str],
    persist_and_refresh: Callable,
    update_scales_from_fields: Callable,
    update_preview: Callable,
    preview_elem: Any,
    capacity_label: Any,
    gcode_labels: dict[str, Any],
    fields: dict[str, Any],
) -> None:
    """Build the Calibration workspace UI.
    
    This workspace handles all grid configuration, layout tuning, G-code
    sampling parameters, and symbol scale correction.
    
    Args:
        supervisor: The SupervisorService instance
        settings: Current plotter settings
        scales: Symbol scale overrides
        preview_mode_value: Current preview mode ("preview" or "printing")
        persist_and_refresh: Callback to save settings and refresh preview
        update_scales_from_fields: Callback to update symbol scales
        update_preview: Callback to refresh preview SVG
        preview_elem: The preview HTML element
        capacity_label: Label showing grid capacity
        gcode_labels: Dict of labels for G-code detail display
        fields: Dict of UI field elements for settings
    """
    symbols = list_base_symbols()
    
    # ========== Handlers ==========
    
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
        """Create a labeled slider with number input and nudge buttons.
        
        Features:
        - Slider and number input stay in sync
        - +/- buttons for fine adjustment
        - Double-click to reset to default
        
        Args:
            label: Display label
            key: Settings key for storage
            value: Initial value
            default: Reset-to value
            min_value, max_value, step: Slider range
            on_change: Callback when value changes
        """
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
    
    def preview_mode_changed(value: Any) -> None:
        """Handle preview mode change (preview vs printing)."""
        preview_mode_value["value"] = value
        save_gui_settings(settings)
        update_preview()
    
    def update_gcode_detail_labels() -> None:
        """Update G-code detail display (spacing, load, etc.)."""
        if not gcode_labels:
            return
        
        effective_step = compute_effective_sample_step(
            sample_step_mm=settings.sample_step_mm,
            cell_diameter_mm=settings.cell_diameter_mm,
            sample_reference_cell_mm=settings.sample_reference_cell_mm,
            sample_density_exponent=settings.sample_density_exponent,
            sample_min_step_mm=settings.sample_min_step_mm,
            sample_max_step_mm=settings.sample_max_step_mm,
        )
        points_per_100mm = 100.0 / max(effective_step, 0.001)
        
        if effective_step <= 0.25:
            load = "VERY FINE"
        elif effective_step <= 0.75:
            load = "FINE"
        elif effective_step <= 1.5:
            load = "NORMAL"
        else:
            load = "LIGHT"
        
        gcode_labels["effective"].set_text(f"{effective_step:.2f} mm")
        gcode_labels["points"].set_text(f"{points_per_100mm:.0f} pts / 100 mm")
        gcode_labels["load"].set_text(load)
        gcode_labels["limits"].set_text(f"{settings.sample_min_step_mm:g} to {settings.sample_max_step_mm:g} mm")
    
    # ========== UI RENDERING ==========
    
    with ui.column().classes("workspace-scroll gap-2"):
        # Layout Configuration Card
        with ui.card().classes("oracle-card compact-card w-full"):
            with ui.row().classes("w-full items-center justify-between"):
                ui.label("Layout").classes("text-sm font-bold")
                capacity_label.classes("status-pill text-xs font-bold")
            
            # Preview mode selection
            ui.select(
                {"preview": "Preview tuning", "printing": "Printing live"},
                value=preview_mode_value["value"],
                label="Preview mode",
                on_change=lambda event: preview_mode_changed(event.value),
            ).props("dense outlined").classes("w-full")
            
            # Layout mode and markers
            with ui.row().classes("items-end gap-2"):
                fields["layout_mode"] = ui.select(
                    {"grid": "Straight", "hex": "Hex"},
                    value=settings.layout_mode,
                    label="Layout",
                ).props("dense outlined").classes("w-32").on_value_change(persist_and_refresh)
                
                fields["include_rings"] = ui.switch("Rings", value=settings.include_rings).on_value_change(persist_and_refresh)
                fields["include_markers"] = ui.switch("Origin dots", value=settings.include_markers).on_value_change(persist_and_refresh)
            
            # Field dimensions and cell settings
            with ui.grid(columns=2).classes("w-full gap-2"):
                _number_control_wrapper(fields, "sheet_width_mm", "Field W", settings.sheet_width_mm, 1, persist_and_refresh, "Printable field width in mm.")
                _number_control_wrapper(fields, "sheet_height_mm", "Field H", settings.sheet_height_mm, 1, persist_and_refresh, "Printable field height in mm.")
                _number_control_wrapper(fields, "cell_diameter_mm", "Cell", settings.cell_diameter_mm, 1, persist_and_refresh, "Packing cell diameter and grid step base.")
                _number_control_wrapper(fields, "gap_mm", "Gap", settings.gap_mm, 0, persist_and_refresh, "Distance between neighboring cell diameters.")
                _number_control_wrapper(fields, "sheet_margin_mm", "Margin", settings.sheet_margin_mm, 0, persist_and_refresh, "Safe border inside printable field.")
                _number_control_wrapper(fields, "marker_diameter_mm", "Dot mm", settings.marker_diameter_mm, 0.5, persist_and_refresh, "Printed origin-dot diameter.")
        
        # Organic/Voronoi Settings Card
        with ui.card().classes("oracle-card compact-card w-full"):
            with ui.row().classes("items-center gap-2"):
                fields["organic_enabled"] = ui.switch("Organic / Voronoi", value=settings.organic_enabled).on_value_change(persist_and_refresh)
            
            with ui.grid(columns=2).classes("w-full gap-2"):
                _number_control_wrapper(fields, "organic_cell_size_mm", "Voronoi cell", settings.organic_cell_size_mm, 0, persist_and_refresh, "Maximum organic position drift in mm.")
                _number_control_wrapper(fields, "organic_seed", "Seed", settings.organic_seed, 1, persist_and_refresh, "Repeats the same organic layout for preview and print.")
            
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
        
        # Advanced Calibration (Collapsible)
        with ui.expansion("Advanced calibration", icon="tune").classes("oracle-card compact-card w-full"):
            ui.label("Use these controls for curve sampling, origin filters, and symbol correction after the physical layout is stable.").classes("text-xs text-[#8f4f2b]")
            
            # Drawing Detail Section
            ui.label("Drawing detail").classes("text-sm font-bold")
            ui.label("Sets how many G-code points are generated from SVG curves. Smaller spacing is smoother and slower; larger spacing is lighter and faster.").classes("text-xs text-[#8f4f2b]")
            
            with ui.grid(columns=3).classes("w-full gap-1"):
                with ui.element("div").classes("mini-metric"):
                    ui.label("Active spacing").classes("label")
                    gcode_labels["effective"] = ui.label("-").classes("value")
                with ui.element("div").classes("mini-metric"):
                    ui.label("Path density").classes("label")
                    gcode_labels["points"] = ui.label("-").classes("value")
                with ui.element("div").classes("mini-metric"):
                    ui.label("G-code load").classes("label")
                    gcode_labels["load"] = ui.label("-").classes("value")
            
            ui.label("Main detail").classes("text-[10px] font-bold text-[#8f4f2b] uppercase")
            _number_control_wrapper(
                fields, "sample_step_mm", "Spacing at normal cell size (mm)", settings.sample_step_mm, 0.05, persist_and_refresh,
                "Distance between sampled points for an 80 mm reference cell."
            )
            
            ui.label("Auto-adjust for cell size").classes("text-[10px] font-bold text-[#8f4f2b] uppercase")
            _number_control_wrapper(
                fields, "sample_density_exponent", "Auto density strength", settings.sample_density_exponent, 0.0, persist_and_refresh,
                "0 disables cell-size compensation. 1 is normal. Higher values make large cells denser."
            )
            
            # Clamping limits
            with ui.row().classes("items-center gap-2"):
                ui.label("Clamp").classes("text-[10px] font-bold text-[#8f4f2b] uppercase")
                gcode_labels["limits"] = ui.label("-").classes("text-xs text-[#8f4f2b]")
            
            with ui.grid(columns=2).classes("w-full gap-2"):
                _number_control_wrapper(
                    fields, "sample_min_step_mm", "Finest allowed spacing", settings.sample_min_step_mm, 0.01, persist_and_refresh,
                    "Lower safety limit. Prevents extremely dense G-code."
                )
                _number_control_wrapper(
                    fields, "sample_max_step_mm", "Coarsest allowed spacing", settings.sample_max_step_mm, 0.05, persist_and_refresh,
                    "Upper safety limit. Prevents overly simplified curves."
                )
            
            # Streaming mode
            fields["streaming_mode"] = ui.select(
                {"row": "Row at a time", "cell": "Cell at a time"},
                value=settings.streaming_mode,
                label="Send to FluidNC",
            ).props("dense outlined").classes("w-full").on_value_change(persist_and_refresh)
            
            update_gcode_detail_labels()
            
            # Filters / Markers Section
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
            
            # Symbol Scale Correction
            ui.label("Symbol scale correction").classes("text-sm font-bold")
            ui.label("These controls define how generated symbols will look before test generation and printing.").classes("text-xs text-[#8f4f2b]")
            
            calibration_slider_row(
                "Random coarse", "randomness",
                value=settings.randomness, default=float(GUI_DEFAULTS.get("randomness", 0)),
                min_value=0, max_value=100, step=1, on_change=persist_and_refresh
            )
            calibration_slider_row(
                "Random fine", "randomness_fine",
                value=settings.randomness_fine, default=float(GUI_DEFAULTS.get("randomness_fine", 0)),
                min_value=-10, max_value=10, step=0.1, on_change=persist_and_refresh
            )
            calibration_slider_row(
                "Global scale", "global_scale",
                value=settings.global_scale, default=1.0,
                min_value=0.3, max_value=3.0, step=0.01, on_change=persist_and_refresh
            )
            
            ui.label("Double-click any scale slider to reset it to 1.0. Scale changes are applied and saved immediately.").classes("text-xs text-[#8f4f2b]")
            
            # Per-symbol scales
            with ui.column().classes("w-full gap-0"):
                for symbol in symbols:
                    calibration_slider_row(
                        symbol.stem[:20],
                        f"scale:{symbol.name}",
                        value=scales.get(symbol.name, 1.0),
                        default=1.0,
                        min_value=0.3,
                        max_value=5.0,
                        step=0.01,
                        on_change=update_scales_from_fields,
                    )


def _number_control_wrapper(
    fields: dict[str, Any],
    key: str,
    label: str,
    value: float,
    min_value: float,
    on_change: Callable,
    tooltip: str,
) -> None:
    """Helper to create number_control inputs with consistent formatting.
    
    Args:
        fields: Dict to store field references
        key: Settings key
        label: Display label
        value: Initial value
        min_value: Minimum allowed value
        on_change: Callback on change
        tooltip: Help text
    """
    from ..gui_ui import number_control as gui_number_control
    
    gui_number_control(
        fields, key, label=label, value=value,
        default=float(GUI_DEFAULTS.get(key, min_value)),
        min_value=min_value, width_class="w-full", tooltip=tooltip,
        on_change=on_change
    )
