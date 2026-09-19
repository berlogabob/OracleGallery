from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, TypedDict

from .config import PlotterSettings
from .models import PlotterRuntimeConfig, SystemMode
from .modes import apply_mode_to_config, mode_policy
from .origin_markers import ALL_ORIGINS, DEFAULT_MARKER_DIAMETER_MM
from .z_positions import (
    DEFAULT_BOTTOM_PULSE_US,
    DEFAULT_REAL_SPAN_MM,
    DEFAULT_REAL_SPAN_US,
    DEFAULT_TOP_PULSE_US,
    ZPositions,
    ZPulseRange,
    pulse_for_real_mm,
    with_material,
    z_for_pulse,
)


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
    stream_enabled: bool
    stream_interval_seconds: float
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
    z_fix_mm: float
    z_top_mech_us: int
    z_top_soft_us: int
    z_load_us: int
    z_bottom_soft_us: int
    z_bottom_mech_us: int
    z_pulse_top_us: int
    z_pulse_bottom_us: int
    z_real_span_mm: float
    z_real_span_us: int
    z_material_mm: float
    z_feed_mm_min: float
    pen_width_mm: float
    pen_down_dwell_ms: float
    direct_svg_origin_x_mm: float
    direct_svg_origin_y_mm: float
    # image.py kept these in-module as "per-image choices, not machine calibration ...
    # promote them if operators ask for sticky values" — the operator has now asked. Only the
    # tune-once knobs move here; the per-picture ones (file bytes, crop, names) stay transient.
    image_mode: str
    image_quality: str
    lift_budget: int
    image_source: str
    image_width_mm: float
    image_height_mm: float
    image_cell_mm: float
    image_detail: float
    image_gamma: float
    image_invert: bool
    image_show_travel: bool
    wave_orientation: str
    wave_connect: bool
    flow_dash_mm: float
    sheet_cell_width_mm: float
    sheet_cell_height_mm: float
    sheet_gap_mm: float
    sheet_padding_mm: float
    sheet_shape: str
    motif_mode: str
    motif_cell_mm: float
    motif_gamma: float
    motif_autocontrast: bool
    motif_invert: bool
    motif_despeckle_mm: float
    motif_simplify_mm: float


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
    "z_fix_mm",
    "z_top_mech_us",
    "z_top_soft_us",
    "z_load_us",
    "z_bottom_soft_us",
    "z_bottom_mech_us",
    "z_real_span_mm",
    "z_material_mm",
    "z_feed_mm_min",
    "pen_width_mm",
    "pen_down_dwell_ms",
    "direct_svg_origin_x_mm",
    "direct_svg_origin_y_mm",
    "stream_interval_seconds",
    "image_width_mm",
    "image_height_mm",
    "image_cell_mm",
    "image_detail",
    "image_gamma",
    "lift_budget",
    "flow_dash_mm",
    "sheet_cell_width_mm",
    "sheet_cell_height_mm",
    "sheet_gap_mm",
    "sheet_padding_mm",
    "motif_cell_mm",
    "motif_gamma",
    "motif_despeckle_mm",
    "motif_simplify_mm",
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
    # Unattended streaming survives a reload now; it used to reset to off with the
    # interval pinned at a literal 15, while the switch still rendered as ON.
    "stream_enabled": False,
    "stream_interval_seconds": 15.0,
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
    # Must match the controller's saved X/Y acceleration (echodraw/hardware/configs/config.yaml,
    # axes X/Y acceleration_mm_per_sec2: 100) -- estimate.py's limits_for(settings) uses this
    # value to predict plot time, and print G-code does not change the board's own setting.
    "xy_acceleration_mm_s2": 100.0,
    "z_down_mm": -25.0,
    "z_up_mm": 0.0,
    # Derived from the pulse positions below by sync_z_from_pulses -- the five microsecond
    # values are what an operator tunes, and these three are what the G-code needs. A value
    # here is overwritten on load and on every save.
    "z_fix_mm": -24.0,
    # The five named positions, in servo microseconds, top to bottom. The Z axis is a servo
    # and its millimetres are fiction (25 units span a measured 6.8 mm), so the tuning
    # happens in the units the servo really takes. See shared/z_positions.py.
    "z_top_mech_us": DEFAULT_TOP_PULSE_US,
    "z_top_soft_us": DEFAULT_TOP_PULSE_US,
    "z_load_us": 2388,
    # Drawing. Shipped at the bottom stop, which is where it has always been, so this change
    # moves nothing until the operator raises it and lets the holder's spring do the pressing.
    "z_bottom_soft_us": DEFAULT_BOTTOM_PULSE_US,
    "z_bottom_mech_us": DEFAULT_BOTTOM_PULSE_US,
    # The controller's own endpoints, mirrored here so a re-tuned servo moves every derived
    # millimetre with it. A system check compares these against the live board.
    "z_pulse_top_us": DEFAULT_TOP_PULSE_US,
    "z_pulse_bottom_us": DEFAULT_BOTTOM_PULSE_US,
    # One measured sweep, in real millimetres and the microseconds it covered: the linkage
    # turns pulse into an arc, so nothing but a rule can say what a position means on paper.
    "z_real_span_mm": DEFAULT_REAL_SPAN_MM,
    "z_real_span_us": DEFAULT_REAL_SPAN_US,
    # What is on the bed. A mat or a thicker sheet raises the drawing surface, so drawing and
    # pen load rise with it; pen-up does not, or every stroke of every plot pays the lift.
    "z_material_mm": 0.0,
    "z_feed_mm_min": 1000.0,
    "pen_width_mm": 0.3,
    "pen_down_dwell_ms": 0.0,
    "direct_svg_origin_x_mm": 25.0,
    "direct_svg_origin_y_mm": 25.0,
    # Mirrors of image.py's STATE / SHEET_STATE / MOTIF_STATE defaults, promoted per the note
    # there that they should move here once operators asked for sticky values. "contour" is
    # patterns.ingest.DEFAULT_MODE, spelled out so shared/ keeps depending on nothing in blocks/.
    "image_mode": "trace",
    "image_quality": "fine",
    "lift_budget": 1024,
    "image_source": "scan",
    "image_width_mm": 150.0,
    "image_height_mm": 150.0,
    "image_cell_mm": 0.10,
    "image_detail": 1.0,
    "image_gamma": 1.0,
    "image_invert": False,
    "image_show_travel": True,
    "wave_orientation": "horizontal",
    "wave_connect": False,
    "flow_dash_mm": 0.0,
    "sheet_cell_width_mm": 40.0,
    "sheet_cell_height_mm": 60.0,
    "sheet_gap_mm": 5.0,
    "sheet_padding_mm": 2.0,
    "sheet_shape": "rect",
    "motif_mode": "contour",
    "motif_cell_mm": 0.8,
    "motif_gamma": 1.0,
    "motif_autocontrast": True,
    "motif_invert": False,
    "motif_despeckle_mm": 1.5,
    "motif_simplify_mm": 0.4,
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
    stream_enabled: bool = GUI_DEFAULTS["stream_enabled"]
    stream_interval_seconds: float = GUI_DEFAULTS["stream_interval_seconds"]
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
    z_fix_mm: float = GUI_DEFAULTS["z_fix_mm"]
    z_top_mech_us: int = GUI_DEFAULTS["z_top_mech_us"]
    z_top_soft_us: int = GUI_DEFAULTS["z_top_soft_us"]
    z_load_us: int = GUI_DEFAULTS["z_load_us"]
    z_bottom_soft_us: int = GUI_DEFAULTS["z_bottom_soft_us"]
    z_bottom_mech_us: int = GUI_DEFAULTS["z_bottom_mech_us"]
    z_pulse_top_us: int = GUI_DEFAULTS["z_pulse_top_us"]
    z_pulse_bottom_us: int = GUI_DEFAULTS["z_pulse_bottom_us"]
    z_real_span_mm: float = GUI_DEFAULTS["z_real_span_mm"]
    z_real_span_us: int = GUI_DEFAULTS["z_real_span_us"]
    z_material_mm: float = GUI_DEFAULTS["z_material_mm"]
    # Name of the material last applied from the library (shared/materials.py). A label, like
    # pen_profile: the thickness above is the value that counts.
    z_material: str = ""
    z_feed_mm_min: float = 1000.0
    # Nib calibration: the width of the emitted SVG stroke, and how many passes trace
    # needs to fill a bold line. halftone's min_ink_mm is NOT wired to this yet — it keeps
    # its own 0.15 default, so a very different nib still wants that adjusted by hand.
    pen_width_mm: float = GUI_DEFAULTS["pen_width_mm"]
    # Time held at pen-down before the first move. Gel and ballpoint ink needs a moment
    # to reach the tip or the first millimetres of every stroke come out dry. Zero emits
    # no dwell at all, so a fineliner's G-code is unchanged.
    pen_down_dwell_ms: float = GUI_DEFAULTS["pen_down_dwell_ms"]
    # Name of the last applied pen profile (assets/pen_profiles.json). Recorded so the
    # GUI can show which pen is fitted; the values above are the source of truth.
    pen_profile: str = ""
    direct_svg_origin_x_mm: float = GUI_DEFAULTS["direct_svg_origin_x_mm"]
    direct_svg_origin_y_mm: float = GUI_DEFAULTS["direct_svg_origin_y_mm"]
    user_count: int = 1
    live_interval_seconds: float = 12.0
    idle_count: int = 8
    idle_variations_per_symbol: int = 2
    selected_symbol: str = "__cycle__"
    # Image workspace knobs, sticky by operator request (see the note at image.py:29). The
    # per-picture ones — uploaded bytes/names, the crop box, motif name, sheet folder and
    # index — deliberately stay in-module: a stale crop on a fresh photo is a bug, not a preference.
    image_mode: str = GUI_DEFAULTS["image_mode"]
    image_quality: str = GUI_DEFAULTS["image_quality"]
    lift_budget: int = GUI_DEFAULTS["lift_budget"]
    image_source: str = GUI_DEFAULTS["image_source"]
    image_width_mm: float = GUI_DEFAULTS["image_width_mm"]
    image_height_mm: float = GUI_DEFAULTS["image_height_mm"]
    image_cell_mm: float = GUI_DEFAULTS["image_cell_mm"]
    image_detail: float = GUI_DEFAULTS["image_detail"]
    image_gamma: float = GUI_DEFAULTS["image_gamma"]
    image_invert: bool = GUI_DEFAULTS["image_invert"]
    image_show_travel: bool = GUI_DEFAULTS["image_show_travel"]
    wave_orientation: str = GUI_DEFAULTS["wave_orientation"]
    wave_connect: bool = GUI_DEFAULTS["wave_connect"]
    flow_dash_mm: float = GUI_DEFAULTS["flow_dash_mm"]
    sheet_cell_width_mm: float = GUI_DEFAULTS["sheet_cell_width_mm"]
    sheet_cell_height_mm: float = GUI_DEFAULTS["sheet_cell_height_mm"]
    sheet_gap_mm: float = GUI_DEFAULTS["sheet_gap_mm"]
    sheet_padding_mm: float = GUI_DEFAULTS["sheet_padding_mm"]
    sheet_shape: str = GUI_DEFAULTS["sheet_shape"]
    motif_mode: str = GUI_DEFAULTS["motif_mode"]
    motif_cell_mm: float = GUI_DEFAULTS["motif_cell_mm"]
    motif_gamma: float = GUI_DEFAULTS["motif_gamma"]
    motif_autocontrast: bool = GUI_DEFAULTS["motif_autocontrast"]
    motif_invert: bool = GUI_DEFAULTS["motif_invert"]
    motif_despeckle_mm: float = GUI_DEFAULTS["motif_despeckle_mm"]
    motif_simplify_mm: float = GUI_DEFAULTS["motif_simplify_mm"]
    # CREATE -> GRID. The GRID pane writes these straight onto settings and never registers
    # them in ctx.fields, so pull_settings_from_fields has nothing to read back.
    # grid_cell_modes is a flat 9x9 table indexed row * 9 + col ("" = empty cell), so a
    # cell keeps its mode when the grid size changes.
    grid_size: int = 4
    grid_quality: str = "balanced"
    grid_photo_filter: bool = False
    # Solve each cell's detail for a target ink coverage instead of rendering at the shipped
    # spacings, which are tuned for a ~150 mm sheet and leave a few-centimetre cell nearly
    # blank. See blocks/imaging/exposure.py.
    grid_match_ink: bool = True
    # Minutes the whole grid sheet may take. Match ink buys coverage with plot time, so it
    # backs off its target until the estimate fits. 0 means no ceiling. 180 because a 36-cell
    # sheet measured 190 min at the shipped spacings and 413 with the solve at full target --
    # a tighter default would clamp the solve back to its floor on an ordinary sheet.
    grid_time_budget_min: float = 180.0
    grid_labels: bool = True
    grid_cell_modes: list[str] = field(default_factory=list)

    def apply_system_mode(self) -> None:
        policy = mode_policy(self.system_mode)
        self.system_mode = policy.mode.value
        self.run_mode = policy.run_mode
        self.dry_run = policy.dry_run

    @property
    def mode(self) -> SystemMode:
        return SystemMode(self.system_mode)


def z_pulse_range(settings: GuiSettings) -> ZPulseRange:
    """The controller's endpoints as this GUI has them recorded."""
    return ZPulseRange(top_us=int(settings.z_pulse_top_us), bottom_us=int(settings.z_pulse_bottom_us))


def material_offset_us(settings: GuiSettings) -> int:
    """The pulse correction for whatever is on the bed, from its measured thickness."""
    return pulse_for_real_mm(float(settings.z_material_mm), settings.z_real_span_mm, settings.z_real_span_us)


def z_positions(settings: GuiSettings, *, with_material_offset: bool = False) -> ZPositions:
    positions = _z_positions_raw(settings)
    return with_material(positions, material_offset_us(settings)) if with_material_offset else positions


def _z_positions_raw(settings: GuiSettings) -> ZPositions:
    return ZPositions(
        top_mech_us=int(settings.z_top_mech_us),
        top_soft_us=int(settings.z_top_soft_us),
        load_us=int(settings.z_load_us),
        bottom_soft_us=int(settings.z_bottom_soft_us),
        bottom_mech_us=int(settings.z_bottom_mech_us),
    )


def sync_z_from_pulses(settings: GuiSettings) -> GuiSettings:
    """Recompute the millimetre Z targets from the microsecond positions, in place.

    The pulses are what the operator tunes; these three are what every emitter already
    reads (svg_gcode's pen up/down, the calibration sheets, the daemon, the supervisor's
    manual moves). Deriving them in one place means none of that had to learn about pulses.
    """
    pulses = z_pulse_range(settings)
    # The commanded set, material included: what is on the bed lifts the surface the pen
    # meets, so the millimetres the G-code carries have to account for it.
    commanded = z_positions(settings, with_material_offset=True)

    def target(pulse_us: int) -> float:
        # Clamped to the axis. A pulse outside the servo's range derives a Z metres off the
        # machine -- one settings file carried z_top_soft_us = 7, which is Z+174 mm, and the
        # estimate for a sheet read 1499 minutes of pen lifts because every stroke was
        # travelling 174 mm twice. The board would refuse the move; better never to emit it.
        return min(0.0, max(pulses.bottom_mm, z_for_pulse(pulse_us, pulses)))

    settings.z_up_mm = target(commanded.top_soft_us)
    settings.z_down_mm = target(commanded.bottom_soft_us)
    settings.z_fix_mm = target(commanded.load_us)
    return settings


def _repair_xy_acceleration(value: float) -> float:
    # Guards against a near-zero garbage value surviving a bad save/migration (0 itself is
    # legitimate -- it means "no comment, use the controller's saved acceleration", see
    # svg_gcode._xy_acceleration_comment). The threshold used to be 100 because the old
    # default was 1000 (10% of it); now the real, legitimate value IS 100 -- the controller's
    # own acceleration -- so a value like 50 or 80 is a plausible measurement, not corruption,
    # and must not be clobbered back up to the default. Scaled to the same 10%-of-default
    # ratio against the new 100 default.
    if 0.0 < value < 10.0:
        return GUI_DEFAULTS["xy_acceleration_mm_s2"]
    return value


def effective_randomness(settings: GuiSettings) -> float:
    """The two Random sliders folded into one 0..100 number: coarse pulls half-weight, fine trims."""
    return max(0.0, min(settings.randomness * 0.5 + settings.randomness_fine, 100.0))


# The slider defaults (35 / 0) fold to 17.5, and 17.5 must mean "the layout jitter exactly as
# shipped" -- an operator who never touches Random gets byte-identical G-code to before the
# sliders were wired.
_NEUTRAL_RANDOMNESS = GUI_DEFAULTS["randomness"] * 0.5 + GUI_DEFAULTS["randomness_fine"]


def layout_jitter_scale(settings: GuiSettings) -> float:
    """The Random sliders as a multiplier on the shipped layout jitter (1.0 at defaults)."""
    return effective_randomness(settings) / _NEUTRAL_RANDOMNESS


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
            layout_jitter_scale=layout_jitter_scale(settings),
            global_scale=settings.global_scale,
            run_mode=settings.run_mode,
            dry_run=settings.dry_run,
            include_rings=settings.include_rings,
            include_markers=settings.include_markers,
            marker_diameter_mm=settings.marker_diameter_mm,
            travel_rate=settings.travel_rate,
            draw_rate=settings.draw_rate,
            xy_acceleration_mm_s2=_repair_xy_acceleration(settings.xy_acceleration_mm_s2),
            use_z_servo=plotter_settings.use_z_servo,
            # Derived here too: a caller that built a GuiSettings by hand (a script, a test)
            # never passed through load or save, so its millimetres could be stale.
            z_down_mm=z_for_pulse(settings.z_bottom_soft_us, z_pulse_range(settings)),
            z_up_mm=z_for_pulse(settings.z_top_soft_us, z_pulse_range(settings)),
            z_fix_mm=z_for_pulse(settings.z_load_us, z_pulse_range(settings)),
            z_feed_mm_min=settings.z_feed_mm_min,
            pen_down_dwell_ms=settings.pen_down_dwell_ms,
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
