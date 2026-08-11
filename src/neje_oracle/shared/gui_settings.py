from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, TypedDict

from .config import PlotterSettings
from .models import PlotterRuntimeConfig, SystemMode
from .modes import apply_mode_to_config, mode_policy
from .origin_markers import ALL_ORIGINS, DEFAULT_MARKER_DIAMETER_MM


class GuiDefaults(TypedDict):
    system_mode: str
    sheet_width_mm: float
    sheet_height_mm: float
    sheet_margin_mm: float
    cell_diameter_mm: float
    gap_mm: float
    organic_enabled: bool
    organic_cell_size_mm: float
    organic_rotation_ramp: float
    organic_scale_ramp: float
    organic_seed: int
    global_scale: float
    randomness: float
    randomness_fine: float
    include_rings: bool
    include_markers: bool
    marker_diameter_mm: float
    sample_step_mm: float
    sample_reference_cell_mm: float
    sample_density_exponent: float
    sample_min_step_mm: float
    sample_max_step_mm: float
    streaming_mode: str
    travel_rate: float
    draw_rate: float
    xy_acceleration_mm_s2: float
    z_down_mm: float
    z_up_mm: float
    z_feed_mm_min: float
    pen_width_mm: float
    direct_svg_origin_x_mm: float
    direct_svg_origin_y_mm: float


type NumericGuiDefaultKey = Literal[
    "sheet_width_mm",
    "sheet_height_mm",
    "sheet_margin_mm",
    "cell_diameter_mm",
    "gap_mm",
    "organic_cell_size_mm",
    "organic_rotation_ramp",
    "organic_scale_ramp",
    "organic_seed",
    "global_scale",
    "randomness",
    "randomness_fine",
    "marker_diameter_mm",
    "sample_step_mm",
    "sample_reference_cell_mm",
    "sample_density_exponent",
    "sample_min_step_mm",
    "sample_max_step_mm",
    "travel_rate",
    "draw_rate",
    "xy_acceleration_mm_s2",
    "z_down_mm",
    "z_up_mm",
    "z_feed_mm_min",
    "pen_width_mm",
    "direct_svg_origin_x_mm",
    "direct_svg_origin_y_mm",
]


GUI_DEFAULTS: GuiDefaults = {
    "system_mode": SystemMode.EXHIBITION.value,
    "sheet_width_mm": 250.0,
    "sheet_height_mm": 440.0,
    "sheet_margin_mm": 0.0,
    "cell_diameter_mm": 80.0,
    "gap_mm": 0.0,
    "organic_enabled": False,
    "organic_cell_size_mm": 18.0,
    "organic_rotation_ramp": 0.0,
    "organic_scale_ramp": 0.0,
    "organic_seed": 1007,
    "global_scale": 1.0,
    "randomness": 35.0,
    "randomness_fine": 0.0,
    "include_rings": True,
    "include_markers": True,
    "marker_diameter_mm": DEFAULT_MARKER_DIAMETER_MM,
    "sample_step_mm": 1.0,
    "sample_reference_cell_mm": 80.0,
    "sample_density_exponent": 1.0,
    "sample_min_step_mm": 0.25,
    "sample_max_step_mm": 3.0,
    "streaming_mode": "row",
    "travel_rate": 5000.0,
    "draw_rate": 1800.0,
    "xy_acceleration_mm_s2": 1000.0,
    "z_down_mm": -25.0,
    "z_up_mm": 0.0,
    "z_feed_mm_min": 1000.0,
    "pen_width_mm": 0.3,
    "direct_svg_origin_x_mm": 25.0,
    "direct_svg_origin_y_mm": 25.0,
}


@dataclass
class GuiSettings:
    system_mode: str = GUI_DEFAULTS["system_mode"]
    layout_mode: str = "hex"
    sheet_width_mm: float = GUI_DEFAULTS["sheet_width_mm"]
    sheet_height_mm: float = GUI_DEFAULTS["sheet_height_mm"]
    sheet_margin_mm: float = GUI_DEFAULTS["sheet_margin_mm"]
    cell_diameter_mm: float = GUI_DEFAULTS["cell_diameter_mm"]
    gap_mm: float = GUI_DEFAULTS["gap_mm"]
    organic_enabled: bool = GUI_DEFAULTS["organic_enabled"]
    organic_cell_size_mm: float = GUI_DEFAULTS["organic_cell_size_mm"]
    organic_rotation_ramp: float = GUI_DEFAULTS["organic_rotation_ramp"]
    organic_scale_ramp: float = GUI_DEFAULTS["organic_scale_ramp"]
    organic_seed: int = GUI_DEFAULTS["organic_seed"]
    run_mode: str = "exhibition"
    # apply_system_mode() always resolves this from mode_policy(); keep the default in sync with that reality.
    dry_run: bool = False
    global_scale: float = GUI_DEFAULTS["global_scale"]
    randomness: float = GUI_DEFAULTS["randomness"]
    randomness_fine: float = GUI_DEFAULTS["randomness_fine"]
    include_rings: bool = GUI_DEFAULTS["include_rings"]
    include_markers: bool = GUI_DEFAULTS["include_markers"]
    marker_diameter_mm: float = GUI_DEFAULTS["marker_diameter_mm"]
    sample_step_mm: float = GUI_DEFAULTS["sample_step_mm"]
    sample_reference_cell_mm: float = GUI_DEFAULTS["sample_reference_cell_mm"]
    sample_density_exponent: float = GUI_DEFAULTS["sample_density_exponent"]
    sample_min_step_mm: float = GUI_DEFAULTS["sample_min_step_mm"]
    sample_max_step_mm: float = GUI_DEFAULTS["sample_max_step_mm"]
    streaming_mode: str = GUI_DEFAULTS["streaming_mode"]
    show_origins: list[str] = field(default_factory=lambda: list(ALL_ORIGINS))
    print_origins: list[str] = field(default_factory=lambda: list(ALL_ORIGINS))
    travel_rate: float = 5000.0
    draw_rate: float = 1800.0
    xy_acceleration_mm_s2: float = GUI_DEFAULTS["xy_acceleration_mm_s2"]
    z_down_mm: float = -25.0
    z_up_mm: float = 0.0
    z_feed_mm_min: float = 1000.0
    # Nib calibration: the width of the emitted SVG stroke, and how many passes trace
    # needs to fill a bold line. halftone's min_ink_mm is NOT wired to this yet — it keeps
    # its own 0.15 default, so a very different nib still wants that adjusted by hand.
    pen_width_mm: float = GUI_DEFAULTS["pen_width_mm"]
    direct_svg_origin_x_mm: float = GUI_DEFAULTS["direct_svg_origin_x_mm"]
    direct_svg_origin_y_mm: float = GUI_DEFAULTS["direct_svg_origin_y_mm"]
    user_count: int = 1
    live_interval_seconds: float = 12.0
    idle_count: int = 8
    idle_variations_per_symbol: int = 2
    selected_symbol: str = "__cycle__"

    def apply_system_mode(self) -> None:
        policy = mode_policy(self.system_mode)
        self.system_mode = policy.mode.value
        self.run_mode = policy.run_mode
        self.dry_run = policy.dry_run

    @property
    def mode(self) -> SystemMode:
        return SystemMode(self.system_mode)


def _repair_xy_acceleration(value: float) -> float:
    if 0.0 < value < 100.0:
        return GUI_DEFAULTS["xy_acceleration_mm_s2"]
    return value


def gui_settings_to_plotter_config(settings: GuiSettings) -> PlotterRuntimeConfig:
    settings.apply_system_mode()
    plotter_settings = PlotterSettings()
    return apply_mode_to_config(
        PlotterRuntimeConfig(
            layout_mode=settings.layout_mode,
            sheet_width_mm=settings.sheet_width_mm,
            sheet_height_mm=settings.sheet_height_mm,
            sheet_margin_mm=settings.sheet_margin_mm,
            cell_diameter_mm=settings.cell_diameter_mm,
            gap_mm=settings.gap_mm,
            organic_enabled=settings.organic_enabled,
            organic_cell_size_mm=settings.organic_cell_size_mm,
            organic_rotation_ramp=settings.organic_rotation_ramp,
            organic_scale_ramp=settings.organic_scale_ramp,
            organic_seed=settings.organic_seed,
            run_mode=settings.run_mode,
            dry_run=settings.dry_run,
            include_rings=settings.include_rings,
            include_markers=settings.include_markers,
            marker_diameter_mm=settings.marker_diameter_mm,
            travel_rate=settings.travel_rate,
            draw_rate=settings.draw_rate,
            xy_acceleration_mm_s2=_repair_xy_acceleration(settings.xy_acceleration_mm_s2),
            use_z_servo=plotter_settings.use_z_servo,
            z_down_mm=settings.z_down_mm,
            z_up_mm=settings.z_up_mm,
            z_feed_mm_min=settings.z_feed_mm_min,
            work_zero_command=plotter_settings.work_zero_command,
            sample_step_mm=settings.sample_step_mm,
            sample_reference_cell_mm=settings.sample_reference_cell_mm,
            sample_density_exponent=settings.sample_density_exponent,
            sample_min_step_mm=settings.sample_min_step_mm,
            sample_max_step_mm=settings.sample_max_step_mm,
            streaming_mode=settings.streaming_mode,
        ),
        settings.mode,
    )
