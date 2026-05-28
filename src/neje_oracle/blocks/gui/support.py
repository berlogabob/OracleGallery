from __future__ import annotations

import inspect
import json
import random
import re
import xml.etree.ElementTree as ET
from base64 import b64encode
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from ...shared.config import SYMBOL_FIT_RATIO, FirebaseSettings, OracleSupervisorSettings, PlotterSettings, UploaderSettings, _repo_root, ensure_dir, ensure_parent
from ..firebase.repository import FirebaseRemoteRepository
from .modes import apply_mode_to_config, mode_policy
from ..gcode.layout import build_sheet_layout, calculate_layout_capacity
from ...shared.models import PlotterRuntimeConfig, RuntimeStatus, SheetItem, SheetPlacement, SystemMode
from ...shared.origin_markers import (
    ALL_ORIGINS,
    DEFAULT_MARKER_DIAMETER_MM,
    ORIGIN_FILLER_MACBOOK,
    ORIGIN_PREVIEW_COLORS,
    ORIGIN_REAL_MACMINI,
    ORIGIN_TEST_MACBOOK,
    marker_center_for_position,
    marker_position_for_origin,
    normalize_origin,
    normalize_tags,
)
from ..gcode.sampling import compute_effective_sample_step
from ..symbols.session_generator import build_variant_svg, generate_filler_session_packages, generate_idle_symbols, generate_user_sessions
from ...shared.store import OracleRuntimeStore, PlotterStore
from ..gcode.svg_gcode import generate_absolute_svg_gcode, generate_sheet_gcode, symbol_diameter_for_cell
from ..symbols.svg_normalizer import CANONICAL_BASE_DIAMETER, CANONICAL_CANVAS_SIZE, normalize_svg_file, read_normalized_svg_metadata


_QUEUE_STATUS_CACHE: tuple[datetime, dict[str, Any]] | None = None
PREVIEW_PX_PER_MM = 2.0


@dataclass(frozen=True)
class LivePreviewItem:
    sheet_index: int
    source_kind: str
    origin: str
    state: str
    svg_path: Path | None = None
    center_x_mm: float | None = None
    center_y_mm: float | None = None
    cell_diameter_mm: float | None = None
    rotation_deg: float = 0.0
    symbol_scale: float = 1.0
    row_y_mm: float | None = None


@dataclass(frozen=True)
class DirectSvgPrintJob:
    sheet_id: str
    svg_path: Path
    original_name: str
    label: str
    gcode: str
    effective_sample_step_mm: float


GUI_DEFAULTS = {
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
    # G-code optimisation
    "sample_step_mm": 1.0,
    "sample_reference_cell_mm": 80.0,
    "sample_density_exponent": 1.0,
    "sample_min_step_mm": 0.25,
    "sample_max_step_mm": 3.0,
    "streaming_mode": "row",
    "xy_acceleration_mm_s2": 1000.0,
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
    dry_run: bool = True
    global_scale: float = GUI_DEFAULTS["global_scale"]
    randomness: float = GUI_DEFAULTS["randomness"]
    randomness_fine: float = GUI_DEFAULTS["randomness_fine"]
    include_rings: bool = GUI_DEFAULTS["include_rings"]
    include_markers: bool = GUI_DEFAULTS["include_markers"]
    marker_diameter_mm: float = GUI_DEFAULTS["marker_diameter_mm"]
    # G-code optimisation
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

    @classmethod
    def from_plotter_settings(cls, settings: PlotterSettings) -> "GuiSettings":
        return cls(
            layout_mode=settings.layout_mode,
            sheet_width_mm=settings.sheet_width_mm,
            sheet_height_mm=settings.sheet_height_mm,
            sheet_margin_mm=settings.sheet_margin_mm,
            cell_diameter_mm=settings.cell_diameter_mm,
            gap_mm=settings.cell_gap_mm,
            organic_enabled=settings.organic_enabled,
            organic_cell_size_mm=settings.organic_cell_size_mm,
            organic_rotation_ramp=settings.organic_rotation_ramp,
            organic_scale_ramp=settings.organic_scale_ramp,
            organic_seed=settings.organic_seed,
            dry_run=settings.dry_run,
            travel_rate=settings.travel_rate,
            draw_rate=settings.draw_rate,
            xy_acceleration_mm_s2=_repair_xy_acceleration(settings.xy_acceleration_mm_s2),
            z_down_mm=settings.z_down_mm,
            z_up_mm=settings.z_up_mm,
            z_feed_mm_min=settings.z_feed_mm_min,
            direct_svg_origin_x_mm=GUI_DEFAULTS["direct_svg_origin_x_mm"],
            direct_svg_origin_y_mm=GUI_DEFAULTS["direct_svg_origin_y_mm"],
            include_markers=settings.include_markers,
            marker_diameter_mm=settings.marker_diameter_mm,
            sample_step_mm=settings.sample_step_mm,
            sample_reference_cell_mm=settings.sample_reference_cell_mm,
            sample_density_exponent=settings.sample_density_exponent,
            sample_min_step_mm=settings.sample_min_step_mm,
            sample_max_step_mm=settings.sample_max_step_mm,
            streaming_mode=settings.streaming_mode,
        )


def default_gui_settings_path() -> Path:
    return _repo_root() / "runtime" / "gui_settings.json"


def default_scale_config_path() -> Path:
    return _repo_root() / "assets" / "symbols" / "symbol_scales.json"


def default_symbol_root() -> Path:
    return _repo_root() / "assets" / "symbols"


def default_idle_root() -> Path:
    return _repo_root() / "assets" / "generated_idle_symbols"


def default_filler_package_root() -> Path:
    return _repo_root() / "assets" / "generated_filler_sessions"


def load_gui_settings(path: Path | None = None, plotter_settings: PlotterSettings | None = None) -> GuiSettings:
    settings_path = path or default_gui_settings_path()
    base = GuiSettings.from_plotter_settings(plotter_settings or PlotterSettings())
    if not settings_path.exists():
        base.apply_system_mode()
        return base
    payload = json.loads(settings_path.read_text(encoding="utf-8"))
    merged = asdict(base)
    if "system_mode" not in payload:
        run_mode = str(payload.get("run_mode", base.run_mode))
        if run_mode == "test":
            payload["system_mode"] = SystemMode.TEST.value
        else:
            payload["system_mode"] = SystemMode.EXHIBITION.value
    merged.update({key: value for key, value in payload.items() if key in merged})
    merged["xy_acceleration_mm_s2"] = _repair_xy_acceleration(float(merged.get("xy_acceleration_mm_s2", 0.0) or 0.0))
    settings = GuiSettings(**merged)
    plotter_defaults = plotter_settings or PlotterSettings()
    if plotter_defaults.use_z_servo and settings.z_up_mm == 25.0 and settings.z_down_mm == 0.0:
        settings.z_up_mm = plotter_defaults.z_up_mm
        settings.z_down_mm = plotter_defaults.z_down_mm
    settings.apply_system_mode()
    return settings


def _repair_xy_acceleration(value: float) -> float:
    if 0.0 < value < 100.0:
        return cast(float, GUI_DEFAULTS["xy_acceleration_mm_s2"])
    return value


def save_gui_settings(settings: GuiSettings, path: Path | None = None) -> None:
    settings.apply_system_mode()
    settings.xy_acceleration_mm_s2 = _repair_xy_acceleration(settings.xy_acceleration_mm_s2)
    settings_path = path or default_gui_settings_path()
    ensure_parent(settings_path)
    settings_path.write_text(json.dumps(asdict(settings), indent=2), encoding="utf-8")


def gui_settings_to_plotter_config(settings: GuiSettings) -> PlotterRuntimeConfig:
    settings.apply_system_mode()
    plotter_settings = PlotterSettings()
    return apply_mode_to_config(PlotterRuntimeConfig(
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
        # G-code optimisation
        sample_step_mm=settings.sample_step_mm,
        sample_reference_cell_mm=settings.sample_reference_cell_mm,
        sample_density_exponent=settings.sample_density_exponent,
        sample_min_step_mm=settings.sample_min_step_mm,
        sample_max_step_mm=settings.sample_max_step_mm,
        streaming_mode=settings.streaming_mode,
    ), settings.mode)


def save_oracle_plotter_config(settings: GuiSettings) -> None:
    settings.apply_system_mode()
    store = OracleRuntimeStore(OracleSupervisorSettings().runtime_db_path)
    store.save_system_mode(settings.mode)
    store.save_plotter_config(gui_settings_to_plotter_config(settings))
    store.save_origin_filters(show_origins=settings.show_origins, print_origins=settings.print_origins)


def list_base_symbols(symbol_root: Path | None = None) -> list[Path]:
    root = symbol_root or default_symbol_root()
    return sorted(path for path in root.glob("*.svg") if path.is_file())


def load_symbol_scales(scale_path: Path | None = None, symbol_root: Path | None = None) -> dict[str, float]:
    symbols = list_base_symbols(symbol_root)
    path = scale_path or default_scale_config_path()
    payload: dict[str, Any] = {}
    if path.exists():
        payload = json.loads(path.read_text(encoding="utf-8"))
    return {symbol.name: float(payload.get(symbol.name, 1.0)) for symbol in symbols}


def save_symbol_scales(scales: dict[str, float], scale_path: Path | None = None, symbol_root: Path | None = None) -> None:
    symbols = list_base_symbols(symbol_root)
    payload = {symbol.name: float(scales.get(symbol.name, 1.0)) for symbol in symbols}
    path = scale_path or default_scale_config_path()
    ensure_parent(path)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def layout_capacity(settings: GuiSettings) -> int:
    return calculate_layout_capacity(
        mode=settings.layout_mode,
        sheet_width_mm=settings.sheet_width_mm,
        sheet_height_mm=settings.sheet_height_mm,
        margin_mm=settings.sheet_margin_mm,
        diameter_mm=max(settings.cell_diameter_mm, 1.0),
        gap_mm=max(settings.gap_mm, 0.0),
    )


def _build_layout_for_settings(settings: GuiSettings, count: int) -> list[SheetPlacement]:
    return build_sheet_layout(
        count,
        mode=settings.layout_mode,
        sheet_width_mm=settings.sheet_width_mm,
        sheet_height_mm=settings.sheet_height_mm,
        margin_mm=settings.sheet_margin_mm,
        diameter_mm=max(settings.cell_diameter_mm, 1.0),
        gap_mm=max(settings.gap_mm, 0.0),
        organic_enabled=settings.organic_enabled,
        organic_cell_size_mm=settings.organic_cell_size_mm,
        organic_rotation_ramp=settings.organic_rotation_ramp,
        organic_scale_ramp=settings.organic_scale_ramp,
        organic_seed=settings.organic_seed,
    )


def build_preview_svg(
    settings: GuiSettings,
    *,
    user_count: int = 2,
    idle_count: int | None = None,
    randomize_symbols: bool = False,
    highlighted_row_index: int | None = None,
    highlighted_cell_index: int | None = None,
    symbol_root: Path | None = None,
    scale_path: Path | None = None,
) -> str:
    capacity = layout_capacity(settings)
    if capacity <= 0:
        return _empty_preview_svg(settings, "No printable cells")
    item_count = capacity
    user_count = max(0, min(user_count, item_count))
    idle_count = max(0, item_count - user_count) if idle_count is None else max(0, min(idle_count, item_count - user_count))
    placements = _build_layout_for_settings(settings, user_count + idle_count)
    scale = _preview_scale(settings)
    width = settings.sheet_width_mm * scale
    height = settings.sheet_height_mm * scale
    circles: list[str] = []
    symbol_images = _preview_symbol_images(settings, symbol_root=symbol_root, scale_path=scale_path)
    overscale = any(symbol_scale > 1.0 for _, symbol_scale in symbol_images)
    row_lookup = _placement_row_lookup(placements)
    for index, placement in enumerate(placements):
        kind = "user" if index < user_count else "idle"
        origin = ORIGIN_TEST_MACBOOK if kind == "user" else ORIGIN_FILLER_MACBOOK
        visible_origin = origin in settings.show_origins
        row_index = row_lookup.get(placement.index, 0)
        highlighted_row = highlighted_row_index is not None and row_index == highlighted_row_index
        highlighted_cell = highlighted_cell_index is not None and placement.index == highlighted_cell_index
        stroke = "#9a5b24" if kind == "user" else "#1f1a17"
        fill = "#fff0d4" if highlighted_cell else ("#f9f4ea" if kind == "user" else "#f3eadb")
        cx = placement.center_x_mm * scale
        cy = placement.center_y_mm * scale
        cell_radius = placement.diameter_mm * scale / 2.0
        mark_size = symbol_diameter_for_cell(placement.diameter_mm) * scale
        cell_stroke = "#c7472f" if highlighted_cell else ("#c78d2d" if highlighted_row else "#d8c7aa")
        cell_stroke_width = "4.0" if highlighted_cell else ("2.4" if highlighted_row else "1.0")
        circles.append(
            f'<circle cx="{cx:.2f}" cy="{cy:.2f}" r="{cell_radius:.2f}" fill="{fill}" '
            f'stroke="{cell_stroke}" stroke-width="{cell_stroke_width}"/>'
        )
        if settings.include_rings and visible_origin:
            circles.append(f'<circle cx="{cx:.2f}" cy="{cy:.2f}" r="{mark_size / 2.0:.2f}" fill="none" stroke="{stroke}" stroke-width="1.4" data-ring="outer"/>')
            if kind == "idle":
                circles.append(f'<circle cx="{cx:.2f}" cy="{cy:.2f}" r="{mark_size * 0.44:.2f}" fill="none" stroke="{stroke}" stroke-width="0.9" data-ring="inner"/>')
        if settings.include_markers and visible_origin:
            marker_x, marker_y = marker_center_for_position(
                placement,
                marker_position_for_origin(origin),
                marker_diameter_mm=settings.marker_diameter_mm,
            )
            marker_color = ORIGIN_PREVIEW_COLORS.get(origin, "#1f1a17")
            circles.append(
                f'<circle cx="{marker_x * scale:.2f}" cy="{marker_y * scale:.2f}" '
                f'r="{settings.marker_diameter_mm * scale / 2.0:.2f}" fill="none" '
                f'stroke="{marker_color}" stroke-width="1.6" data-origin-marker="{origin}"/>'
            )
        if symbol_images and visible_origin:
            symbol_index = _preview_symbol_index(index, symbol_images, randomize=randomize_symbols)
            href, _symbol_scale = symbol_images[symbol_index]
            image_size = _preview_image_size(mark_size, placement.symbol_scale)
            transform = _preview_rotation_transform(placement.rotation_deg, cx, cy)
            circles.append(
                f'<image href="{href}" x="{cx - image_size / 2.0:.2f}" y="{cy - image_size / 2.0:.2f}" '
                f'width="{image_size:.2f}" height="{image_size:.2f}" preserveAspectRatio="xMidYMid meet"'
                f'{transform} data-placement-rotation="{placement.rotation_deg:.3f}" '
                f'data-placement-scale="{placement.symbol_scale:.3f}"/>'
            )
        elif visible_origin:
            circles.append(
                f'<text x="{cx:.2f}" y="{cy + 4:.2f}" text-anchor="middle" font-size="12" '
                f'fill="{stroke}" font-family="monospace">{index + 1}</text>'
            )
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width:.2f} {height:.2f}" '
        f'width="{width:.0f}" height="{height:.0f}">'
        '<rect width="100%" height="100%" fill="#fbf7ef"/>'
        f'<rect x="{settings.sheet_margin_mm * scale:.2f}" y="{settings.sheet_margin_mm * scale:.2f}" '
        f'width="{(settings.sheet_width_mm - settings.sheet_margin_mm * 2) * scale:.2f}" '
        f'height="{(settings.sheet_height_mm - settings.sheet_margin_mm * 2) * scale:.2f}" '
        'fill="none" stroke="#d4c3a5" stroke-width="1"/>'
        + (
            '<text x="10" y="18" font-size="11" fill="#9a5b24" font-family="monospace">'
            'overscale may overlap cells</text>'
            if overscale
            else ""
        )
        + "".join(circles)
        + "</svg>"
    )


def _preview_symbol_index(cell_index: int, symbol_images: list[tuple[str, float]], *, randomize: bool) -> int:
    if not randomize:
        return cell_index % len(symbol_images)
    return random.Random(10_007 + cell_index * 101).randrange(len(symbol_images))


def build_realtime_preview_svg(
    settings: GuiSettings,
    status: dict[str, Any],
    queue: dict[str, Any],
    *,
    symbol_root: Path | None = None,
    scale_path: Path | None = None,
) -> str:
    items = _live_preview_items(settings, status, queue)
    if not items:
        pending_users = _pending_user_queue_count(queue)
        return build_preview_svg(
            settings,
            user_count=min(pending_users, layout_capacity(settings)),
            symbol_root=symbol_root,
            scale_path=scale_path,
        )
    return _build_live_preview_svg(settings, items)


def build_symbol_preview_svg(
    symbol_path: Path,
    *,
    marker_kind: str,
    scale: float,
    include_rings: bool,
    randomness: float,
) -> str:
    # Preview SVGs are displayed much smaller than the 800px source canvas, so the
    # UI uses amplified jitter to make the Randomness slider visually legible.
    jitter_px = max(0.0, min(randomness, 100.0)) / 100.0 * 80.0
    return build_variant_svg(
        symbol_path,
        marker_kind=marker_kind,
        scale=scale,
        rng=random.Random(1),
        jitter_px=jitter_px,
        include_rings=include_rings,
    )


def _preview_symbol_images(
    settings: GuiSettings,
    *,
    symbol_root: Path | None = None,
    scale_path: Path | None = None,
) -> list[tuple[str, float]]:
    symbols = list_base_symbols(symbol_root)
    if not symbols:
        return []
    scales = load_symbol_scales(scale_path, symbol_root)
    images: list[tuple[str, float]] = []
    for symbol in symbols:
        symbol_scale = scales.get(symbol.name, 1.0) * settings.global_scale
        svg = build_symbol_preview_svg(
            symbol,
            marker_kind="user",
            scale=symbol_scale,
            include_rings=False,
            randomness=effective_randomness(settings),
        )
        encoded = b64encode(svg.encode("utf-8")).decode("ascii")
        images.append((f"data:image/svg+xml;base64,{encoded}", symbol_scale))
    return images


def _build_live_preview_svg(settings: GuiSettings, items: list[LivePreviewItem]) -> str:
    capacity = layout_capacity(settings)
    if capacity <= 0:
        return _empty_preview_svg(settings, "No printable cells")
    placements = _build_layout_for_settings(settings, capacity)
    scale = _preview_scale(settings)
    width = settings.sheet_width_mm * scale
    height = settings.sheet_height_mm * scale
    item_by_index = {item.sheet_index: item for item in items}
    elements: list[str] = []
    for base_placement in placements:
        item = item_by_index.get(base_placement.index)
        placement = _preview_item_placement(item, base_placement)
        cx = placement.center_x_mm * scale
        cy = placement.center_y_mm * scale
        cell_radius = placement.diameter_mm * scale / 2.0
        mark_size = symbol_diameter_for_cell(placement.diameter_mm) * scale
        state = item.state if item else "empty"
        fill = {
            "drawn": "#fffdf8",
            "drawing": "#fff0d4",
            "next": "#e1ded8",
            "empty": "#f3eadb",
        }.get(state, "#f3eadb")
        stroke = {
            "drawn": "#1f1a17",
            "drawing": "#c7472f",
            "next": "#8f8980",
            "empty": "#d8c7aa",
        }.get(state, "#d8c7aa")
        stroke_width = {"drawing": "3.2", "next": "2.2"}.get(state, "1.0")
        dash = ' stroke-dasharray="5 4"' if state == "next" else ""
        elements.append(
            f'<circle cx="{cx:.2f}" cy="{cy:.2f}" r="{cell_radius:.2f}" fill="{fill}" '
            f'stroke="{stroke}" stroke-width="{stroke_width}" data-preview-state="{state}"{dash}/>'
        )
        if not item:
            continue
        if item.origin not in settings.show_origins:
            continue
        if settings.include_rings:
            ring_opacity = "0.35" if state == "next" else "0.9"
            elements.append(
                f'<circle cx="{cx:.2f}" cy="{cy:.2f}" r="{mark_size / 2.0:.2f}" fill="none" '
                f'stroke="{stroke}" stroke-width="1.2" opacity="{ring_opacity}" data-ring="outer"/>'
            )
            if item.source_kind != "user":
                elements.append(
                    f'<circle cx="{cx:.2f}" cy="{cy:.2f}" r="{mark_size * 0.44:.2f}" fill="none" '
                    f'stroke="{stroke}" stroke-width="0.8" opacity="{ring_opacity}" data-ring="inner"/>'
                )
        if settings.include_markers:
            marker_x, marker_y = marker_center_for_position(
                placement,
                marker_position_for_origin(item.origin),
                marker_diameter_mm=settings.marker_diameter_mm,
            )
            marker_color = ORIGIN_PREVIEW_COLORS.get(item.origin, "#1f1a17")
            marker_opacity = "0.35" if state == "next" else "1.0"
            elements.append(
                f'<circle cx="{marker_x * scale:.2f}" cy="{marker_y * scale:.2f}" '
                f'r="{settings.marker_diameter_mm * scale / 2.0:.2f}" fill="none" '
                f'stroke="{marker_color}" stroke-width="1.6" opacity="{marker_opacity}" '
                f'data-origin-marker="{item.origin}"/>'
            )
        href = _svg_file_data_uri(item.svg_path)
        if href:
            opacity = "0.35" if state == "next" else "1.0"
            grayscale = ' filter="grayscale(1)"' if state == "next" else ""
            image_size = _preview_image_size(mark_size, placement.symbol_scale, svg_path=item.svg_path)
            transform = _preview_rotation_transform(placement.rotation_deg, cx, cy)
            elements.append(
                f'<image href="{href}" x="{cx - image_size / 2.0:.2f}" y="{cy - image_size / 2.0:.2f}" '
                f'width="{image_size:.2f}" height="{image_size:.2f}" opacity="{opacity}"{grayscale} '
                f'preserveAspectRatio="xMidYMid meet"{transform} data-preview-state="{state}" '
                f'data-placement-rotation="{placement.rotation_deg:.3f}" '
                f'data-placement-scale="{placement.symbol_scale:.3f}"/>'
            )
        elif state == "next":
            elements.append(
                f'<circle cx="{cx:.2f}" cy="{cy:.2f}" r="{mark_size * 0.22:.2f}" '
                f'fill="none" stroke="{stroke}" stroke-width="1.4" opacity="0.45" data-preview-state="next-placeholder"/>'
            )
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width:.2f} {height:.2f}" '
        f'width="{width:.0f}" height="{height:.0f}">'
        '<rect width="100%" height="100%" fill="#fbf7ef"/>'
        f'<rect x="{settings.sheet_margin_mm * scale:.2f}" y="{settings.sheet_margin_mm * scale:.2f}" '
        f'width="{(settings.sheet_width_mm - settings.sheet_margin_mm * 2) * scale:.2f}" '
        f'height="{(settings.sheet_height_mm - settings.sheet_margin_mm * 2) * scale:.2f}" '
        'fill="none" stroke="#d4c3a5" stroke-width="1"/>'
        + "".join(elements)
        + "</svg>"
    )


def _live_preview_items(settings: GuiSettings, status: dict[str, Any], queue: dict[str, Any]) -> list[LivePreviewItem]:
    manifest_path = Path(str(status.get("latest_manifest") or ""))
    manifest_items = _manifest_preview_items(manifest_path)
    if not manifest_items:
        return []
    status_name = str(status.get("status") or "")
    cells_completed = max(0, int(status.get("cells_completed", 0) or 0))
    current_cell_in_row = int(status.get("current_cell_in_row", 0) or 0)
    is_drawing = status_name == RuntimeStatus.PRINTING.value and current_cell_in_row > 0
    current_ordinal = cells_completed if is_drawing else None
    next_ordinal = (current_ordinal + 1) if current_ordinal is not None else cells_completed
    if status_name == RuntimeStatus.OPERATOR_PAUSED.value and float(status.get("sheet_progress_percent", 0.0) or 0.0) >= 100.0:
        current_ordinal = None
        next_ordinal = len(manifest_items)

    live_items: list[LivePreviewItem] = []
    for ordinal, item in enumerate(manifest_items):
        if ordinal < cells_completed or current_ordinal is None and ordinal < next_ordinal:
            state = "drawn"
        elif current_ordinal is not None and ordinal == current_ordinal:
            state = "drawing"
        elif ordinal == next_ordinal:
            state = "next"
        else:
            continue
        live_items.append(_manifest_live_preview_item(item, state=state))

    if not any(item.state == "next" for item in live_items):
        ghost = _next_preview_ghost(settings, len(manifest_items), queue)
        if ghost is not None:
            live_items.append(ghost)
    return live_items


def _manifest_preview_items(manifest_path: Path) -> list[dict[str, Any]]:
    if not manifest_path.exists() or not manifest_path.is_file():
        return []
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    items = payload.get("items", [])
    if not items and isinstance(payload.get("rows"), list):
        items = [
            item
            for row in payload["rows"]
            if isinstance(row, dict)
            for item in row.get("items", [])
            if isinstance(item, dict)
        ]
    return [item for item in items if isinstance(item, dict)]


def _manifest_live_preview_item(item: dict[str, Any], *, state: str) -> LivePreviewItem:
    raw_svg_path = str(item.get("svg_path") or "")
    return LivePreviewItem(
        sheet_index=int(item.get("sheet_index", 0) or 0),
        source_kind=str(item.get("source_kind") or "placeholder"),
        origin=normalize_origin(item.get("origin") or ORIGIN_FILLER_MACBOOK),
        state=state,
        svg_path=Path(raw_svg_path) if raw_svg_path else None,
        center_x_mm=_optional_float(item.get("center_x_mm")),
        center_y_mm=_optional_float(item.get("center_y_mm")),
        cell_diameter_mm=_optional_float(item.get("cell_diameter_mm")),
        rotation_deg=float(item.get("rotation_deg", 0.0) or 0.0),
        symbol_scale=float(item.get("symbol_scale", 1.0) or 1.0),
        row_y_mm=_optional_float(item.get("row_y_mm")),
    )


def _next_preview_ghost(settings: GuiSettings, next_sheet_index: int, queue: dict[str, Any]) -> LivePreviewItem | None:
    capacity = layout_capacity(settings)
    if next_sheet_index < 0 or next_sheet_index >= capacity:
        return None
    pending_users = _pending_user_queue_count(queue)
    if pending_users > 0:
        return LivePreviewItem(
            sheet_index=next_sheet_index,
            source_kind="user",
            origin=ORIGIN_REAL_MACMINI,
            state="next",
        )
    return LivePreviewItem(
        sheet_index=next_sheet_index,
        source_kind="placeholder",
        origin=ORIGIN_FILLER_MACBOOK,
        state="next",
    )


def _svg_file_data_uri(path: Path | None) -> str:
    if path is None or not path.exists() or not path.is_file():
        return ""
    try:
        encoded = b64encode(path.read_bytes()).decode("ascii")
    except OSError:
        return ""
    return f"data:image/svg+xml;base64,{encoded}"


def _preview_item_placement(item: LivePreviewItem | None, fallback: SheetPlacement) -> SheetPlacement:
    if item is None or item.center_x_mm is None or item.center_y_mm is None:
        return fallback
    return SheetPlacement(
        index=fallback.index,
        center_x_mm=item.center_x_mm,
        center_y_mm=item.center_y_mm,
        diameter_mm=item.cell_diameter_mm if item.cell_diameter_mm is not None else fallback.diameter_mm,
        rotation_deg=item.rotation_deg,
        symbol_scale=item.symbol_scale,
        row_y_mm=item.row_y_mm,
    )


def _preview_rotation_transform(rotation_deg: float, cx: float, cy: float) -> str:
    if abs(rotation_deg) < 0.001:
        return ""
    return f' transform="rotate({rotation_deg:.2f} {cx:.2f} {cy:.2f})"'


def _optional_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _pending_user_queue_count(queue: dict[str, Any]) -> int:
    if "pendingUserAfterBaseline" in queue:
        return int(queue.get("pendingUserAfterBaseline", 0) or 0)
    return int(queue.get("pendingAfterBaseline", 0) or 0)


def _placement_row_lookup(placements) -> dict[int, int]:
    rows: dict[float, int] = {}
    lookup: dict[int, int] = {}
    for placement in sorted(placements, key=lambda item: (item.row_y_mm if item.row_y_mm is not None else item.center_y_mm, item.center_x_mm)):
        placement_row_y = placement.row_y_mm if placement.row_y_mm is not None else placement.center_y_mm
        row_key = next((key for key in rows if abs(key - placement_row_y) < 0.001), None)
        if row_key is None:
            row_key = placement_row_y
            rows[row_key] = len(rows) + 1
        lookup[placement.index] = rows[row_key]
    return lookup


def create_user_sessions_from_gui(
    settings: GuiSettings,
    *,
    output_root: Path | None = None,
    symbol_root: Path | None = None,
    scale_path: Path | None = None,
    start_index: int = 0,
) -> list[Path]:
    destination = output_root or UploaderSettings().session_root
    generated = generate_user_sessions(
        source_root=symbol_root or default_symbol_root(),
        output_root=destination,
        scale_config=scale_path or default_scale_config_path(),
        count=settings.user_count,
        jitter_px=effective_randomness(settings) / 100.0 * 8.0,
        symbol_name=settings.selected_symbol,
        global_scale=settings.global_scale,
        include_rings=False,
        start_index=start_index,
    )
    return [session.session_dir for session in generated]


def create_next_filler_upload_from_gui(
    settings: GuiSettings,
    *,
    output_root: Path | None = None,
    symbol_root: Path | None = None,
    scale_path: Path | None = None,
    start_index: int = 0,
) -> list[Path]:
    destination = output_root or UploaderSettings().session_root
    generated = generate_filler_session_packages(
        source_root=symbol_root or default_symbol_root(),
        output_root=destination,
        scale_config=scale_path or default_scale_config_path(),
        count=1,
        jitter_px=effective_randomness(settings) / 100.0 * 6.0,
        symbol_name=settings.selected_symbol,
        global_scale=settings.global_scale,
        include_rings=False,
        start_index=start_index,
        upload_to_firebase=True,
    )
    return [session.session_dir for session in generated]


def create_direct_svg_print_job_from_gui(
    settings: GuiSettings,
    *,
    svg_bytes: bytes,
    original_name: str,
    output_root: Path | None = None,
    plotter_settings: PlotterSettings | None = None,
) -> DirectSvgPrintJob:
    svg_text = _validated_svg_text(svg_bytes)
    resolved_plotter_settings = plotter_settings or PlotterSettings()
    destination = output_root or (resolved_plotter_settings.spool_root / "uploaded_svg")
    ensure_dir(destination)
    now = datetime.now(tz=UTC)
    sheet_id = _direct_svg_sheet_id(destination, now)
    label = _label_from_upload_name(original_name)
    svg_file = destination / f"{sheet_id}_{_safe_upload_stem(original_name)}.svg"
    svg_file.write_text(svg_text, encoding="utf-8")

    effective_step = compute_effective_sample_step(
        sample_step_mm=settings.sample_step_mm,
        cell_diameter_mm=settings.cell_diameter_mm,
        sample_reference_cell_mm=settings.sample_reference_cell_mm,
        sample_density_exponent=settings.sample_density_exponent,
        sample_min_step_mm=settings.sample_min_step_mm,
        sample_max_step_mm=settings.sample_max_step_mm,
    )
    gcode = generate_absolute_svg_gcode(
        svg_file,
        sample_step_mm=effective_step,
        travel_rate=settings.travel_rate,
        draw_rate=settings.draw_rate,
        xy_acceleration_mm_s2=_repair_xy_acceleration(settings.xy_acceleration_mm_s2),
        pen_up_command=resolved_plotter_settings.pen_up_command,
        pen_down_command=resolved_plotter_settings.pen_down_command,
        title=f"direct SVG {label}",
        return_home=True,
        use_z_servo=resolved_plotter_settings.use_z_servo,
        z_down_mm=settings.z_down_mm,
        z_up_mm=settings.z_up_mm,
        z_feed_mm_min=settings.z_feed_mm_min,
        origin_x_mm=settings.direct_svg_origin_x_mm,
        origin_y_mm=settings.direct_svg_origin_y_mm,
        keep_non_negative=True,
    )
    return DirectSvgPrintJob(
        sheet_id=sheet_id,
        svg_path=svg_file,
        original_name=original_name,
        label=label,
        gcode=gcode,
        effective_sample_step_mm=effective_step,
    )


def read_upload_content_bytes(content: Any) -> bytes:
    if isinstance(content, bytes):
        return content
    if isinstance(content, str):
        return content.encode("utf-8")

    if hasattr(content, "seek"):
        try:
            content.seek(0)
        except (OSError, ValueError):
            pass
    if hasattr(content, "getvalue"):
        value = content.getvalue()
    else:
        value = content.read()
    if isinstance(value, str):
        return value.encode("utf-8")
    return bytes(value or b"")


async def read_upload_event_payload(event: Any) -> tuple[str, bytes]:
    upload_file = getattr(event, "file", None)
    if upload_file is not None:
        name = str(getattr(upload_file, "name", "") or getattr(event, "name", "") or "uploaded.svg")
        value = upload_file.read()
        if inspect.isawaitable(value):
            value = await value
        if isinstance(value, str):
            return name, value.encode("utf-8")
        return name, bytes(value or b"")

    content = getattr(event, "content", None)
    if content is None:
        raise ValueError("no file content")
    name = str(getattr(event, "name", "") or "uploaded.svg")
    return name, read_upload_content_bytes(content)


def create_idle_bank_from_gui(
    settings: GuiSettings,
    *,
    output_root: Path | None = None,
    symbol_root: Path | None = None,
    scale_path: Path | None = None,
) -> list[Path]:
    symbol_count = len(list_base_symbols(symbol_root))
    count = max(settings.idle_count, symbol_count * max(settings.idle_variations_per_symbol, 1))
    destination = output_root or default_idle_root()
    if destination.exists():
        for old_svg in destination.glob("*.svg"):
            old_svg.unlink()
    return generate_idle_symbols(
        source_root=symbol_root or default_symbol_root(),
        output_root=destination,
        scale_config=scale_path or default_scale_config_path(),
        count=count,
        jitter_px=effective_randomness(settings) / 100.0 * 6.0,
        global_scale=settings.global_scale,
        include_rings=False,
    )


def create_filler_packages_from_gui(
    settings: GuiSettings,
    *,
    output_root: Path | None = None,
    symbol_root: Path | None = None,
    scale_path: Path | None = None,
) -> list[Path]:
    symbol_count = len(list_base_symbols(symbol_root))
    count = max(settings.idle_count, symbol_count * max(settings.idle_variations_per_symbol, 1))
    destination = output_root or default_filler_package_root()
    if destination.exists():
        for old_dir in destination.iterdir():
            if old_dir.is_dir() and old_dir.name.startswith("filler_"):
                for child in sorted(old_dir.rglob("*"), reverse=True):
                    if child.is_file() or child.is_symlink():
                        child.unlink()
                    elif child.is_dir():
                        child.rmdir()
                old_dir.rmdir()
    generated = generate_filler_session_packages(
        source_root=symbol_root or default_symbol_root(),
        output_root=destination,
        scale_config=scale_path or default_scale_config_path(),
        count=count,
        jitter_px=effective_randomness(settings) / 100.0 * 6.0,
        global_scale=settings.global_scale,
        include_rings=False,
    )
    return [session.session_dir for session in generated]


def read_plotter_status(db_path: Path | None = None, spool_root: Path | None = None) -> dict[str, Any]:
    plotter_settings = PlotterSettings()
    resolved_db_path = db_path or plotter_settings.db_path
    latest_manifest = latest_spool_manifest(spool_root or plotter_settings.spool_root)
    item_counts = _manifest_item_counts(latest_manifest)
    oracle_store = OracleRuntimeStore(OracleSupervisorSettings().runtime_db_path)
    oracle_control = oracle_store.load_print_control()
    if not resolved_db_path.exists():
        return {
            "status": "daemon_not_started",
            "message": "Plotter daemon has not created runtime state yet",
            "current_sheet_id": "",
            "last_sheet_path": "",
            "print_enabled": oracle_control.print_enabled,
            "operator_paused": oracle_control.operator_paused,
            "run_mode": oracle_control.run_mode,
            "dry_run": oracle_control.dry_run,
            "gcode_lines_sent": 0,
            "gcode_lines_total": 0,
            "gcode_progress_percent": 0.0,
            "current_row_index": 0,
            "row_count": 0,
            "current_cell_index": 0,
            "current_cell_in_row": 0,
            "row_cell_count": 0,
            "cells_completed": 0,
            "rows_completed": 0,
            "sheet_progress_percent": 0.0,
            "updated_at": "",
            "latest_manifest": str(latest_manifest) if latest_manifest else "",
            "user_count": item_counts["user"],
            "idle_count": item_counts["idle"],
            "processed_symbols": item_counts["total"],
        }
    store = PlotterStore(resolved_db_path)
    state = store.load_runtime_state()
    control = oracle_store.load_print_control(store.load_control_state())
    return {
        "status": state.status.value,
        "message": state.message,
        "current_sheet_id": state.current_sheet_id,
        "last_sheet_path": state.last_sheet_path,
        "print_enabled": control.print_enabled,
        "operator_paused": control.operator_paused,
        "run_mode": control.run_mode,
        "dry_run": control.dry_run,
        "gcode_lines_sent": state.gcode_lines_sent,
        "gcode_lines_total": state.gcode_lines_total,
        "gcode_progress_percent": state.gcode_progress_percent,
        "current_row_index": state.current_row_index,
        "row_count": state.row_count,
        "current_cell_index": state.current_cell_index,
        "current_cell_in_row": state.current_cell_in_row,
        "row_cell_count": state.row_cell_count,
        "cells_completed": state.cells_completed,
        "rows_completed": state.rows_completed,
        "sheet_progress_percent": state.sheet_progress_percent,
        "updated_at": state.updated_at.isoformat(),
        "latest_manifest": str(latest_manifest) if latest_manifest else "",
        "user_count": item_counts["user"],
        "idle_count": item_counts["idle"],
        "processed_symbols": item_counts["total"],
    }


def read_queue_status(*, force: bool = False, ttl_seconds: float = 10.0) -> dict[str, Any]:
    global _QUEUE_STATUS_CACHE
    now = datetime.now(tz=UTC)
    if not force and _QUEUE_STATUS_CACHE is not None:
        cached_at, cached_payload = _QUEUE_STATUS_CACHE
        if (now - cached_at).total_seconds() < ttl_seconds:
            return cached_payload
    if not force and _QUEUE_STATUS_CACHE is None:
        return _queue_status_offline("Queue status not loaded yet")

    firebase_settings = FirebaseSettings()
    if not firebase_settings.enabled:
        payload = _queue_status_offline("Firebase is not configured")
        _QUEUE_STATUS_CACHE = (now, payload)
        return payload

    try:
        oracle_store = OracleRuntimeStore(OracleSupervisorSettings().runtime_db_path)
        baseline = oracle_store.load_run_started_at()
        payload = FirebaseRemoteRepository(firebase_settings).get_plot_job_counts(run_started_at=baseline)
        payload["runStartedAt"] = baseline.isoformat() if baseline else ""
        _QUEUE_STATUS_CACHE = (now, payload)
        return payload
    except Exception as exc:  # noqa: BLE001
        payload = _queue_status_offline(str(exc))
        _QUEUE_STATUS_CACHE = (now, payload)
        return payload


def _queue_status_offline(message: str) -> dict[str, Any]:
    return {
        "online": False,
        "total": 0,
        "limitedTo": 0,
        "pending": 0,
        "pendingAfterBaseline": 0,
        "pendingUserAfterBaseline": 0,
        "pendingFillerAfterBaseline": 0,
        "pendingBeforeBaseline": 0,
        "leased": 0,
        "plotting": 0,
        "printed": 0,
        "failed": 0,
        "skipped": 0,
        "hidden": 0,
        "unknown": 0,
        "runStartedAt": "",
        "message": message,
    }


def generate_dry_run_sheet(settings: GuiSettings, *, spool_root: Path | None = None, symbol_root: Path | None = None) -> dict[str, Path]:
    output_root = spool_root or PlotterSettings().spool_root
    ensure_dir(output_root)
    symbols = list_base_symbols(symbol_root)
    if not symbols:
        raise FileNotFoundError("No symbols available for G-code-only sheet generation")
    scales = load_symbol_scales(symbol_root=symbol_root)
    cache_dir = output_root / "cache"
    ensure_dir(cache_dir)
    scaled_symbols: list[Path] = []
    for symbol in symbols:
        scale = scales.get(symbol.name, 1.0) * settings.global_scale
        cached = cache_dir / f"dry_run_{symbol.stem}.svg"
        cached.write_text(
            normalize_svg_file(symbol, marker_kind="idle", scale=scale, include_rings=False),
            encoding="utf-8",
        )
        scaled_symbols.append(cached)
    capacity = layout_capacity(settings)
    count = capacity
    placements = _build_layout_for_settings(settings, count)
    items = [
        SheetItem(
            source_kind="placeholder",
            session_id=f"gui_dry_run_{index + 1:03d}",
            title=symbols[index % len(symbols)].stem,
            svg_path=scaled_symbols[index % len(scaled_symbols)],
            origin=ORIGIN_FILLER_MACBOOK,
            tags=normalize_tags(["filler", "local", "macbook"]),
            marker_position=marker_position_for_origin(ORIGIN_FILLER_MACBOOK),
        )
        for index in range(len(placements))
    ]
    sheet_id = datetime.now(tz=UTC).strftime("gui_sheet_%Y%m%d_%H%M%S")
    effective_step = compute_effective_sample_step(
        sample_step_mm=settings.sample_step_mm,
        cell_diameter_mm=settings.cell_diameter_mm,
        sample_reference_cell_mm=settings.sample_reference_cell_mm,
        sample_density_exponent=settings.sample_density_exponent,
        sample_min_step_mm=settings.sample_min_step_mm,
        sample_max_step_mm=settings.sample_max_step_mm,
    )
    gcode = generate_sheet_gcode(
        items,
        placements,
        sample_step_mm=effective_step,
        cell_diameter_mm=settings.cell_diameter_mm,
        travel_rate=settings.travel_rate,
        draw_rate=settings.draw_rate,
        xy_acceleration_mm_s2=_repair_xy_acceleration(settings.xy_acceleration_mm_s2),
        pen_up_command=PlotterSettings().pen_up_command,
        pen_down_command=PlotterSettings().pen_down_command,
        include_rings=settings.include_rings,
        include_markers=settings.include_markers,
        marker_diameter_mm=settings.marker_diameter_mm,
        use_z_servo=PlotterSettings().use_z_servo,
        z_down_mm=settings.z_down_mm,
        z_up_mm=settings.z_up_mm,
        z_feed_mm_min=settings.z_feed_mm_min,
    )
    gcode_path = output_root / f"{sheet_id}.gcode"
    manifest_path = output_root / f"{sheet_id}.json"
    gcode_path.write_text(gcode, encoding="utf-8")
    manifest_path.write_text(
        json.dumps(
            {
                "sheet_id": sheet_id,
                "generated_by": "neje-gui",
                "layout_mode": settings.layout_mode,
                "cell_diameter_mm": settings.cell_diameter_mm,
                "gap_mm": settings.gap_mm,
                "organic_enabled": settings.organic_enabled,
                "organic_cell_size_mm": settings.organic_cell_size_mm,
                "organic_rotation_ramp": settings.organic_rotation_ramp,
                "organic_scale_ramp": settings.organic_scale_ramp,
                "organic_seed": settings.organic_seed,
                "symbol_fit_ratio": SYMBOL_FIT_RATIO,
                "include_markers": settings.include_markers,
                "marker_diameter_mm": settings.marker_diameter_mm,
                # G-code optimisation
                "sample_step_mm": settings.sample_step_mm,
                "sample_reference_cell_mm": settings.sample_reference_cell_mm,
                "sample_density_exponent": settings.sample_density_exponent,
                "sample_min_step_mm": settings.sample_min_step_mm,
                "sample_max_step_mm": settings.sample_max_step_mm,
                "effective_sample_step_mm": effective_step,
                "streaming_mode": settings.streaming_mode,
                "xy_acceleration_mm_s2": _repair_xy_acceleration(settings.xy_acceleration_mm_s2),
                "items": [
                    {
                        "session_id": item.session_id,
                        "source_kind": item.source_kind,
                        "origin": item.origin,
                        "tags": item.tags,
                        "marker_position": item.marker_position,
                        "marker_diameter_mm": settings.marker_diameter_mm,
                        "svg_path": str(item.svg_path),
                        "sheet_index": index,
                        "center_x_mm": placements[index].center_x_mm,
                        "center_y_mm": placements[index].center_y_mm,
                        "cell_diameter_mm": placements[index].diameter_mm,
                        "rotation_deg": placements[index].rotation_deg,
                        "symbol_scale": placements[index].symbol_scale,
                        "row_y_mm": placements[index].row_y_mm,
                    }
                    for index, item in enumerate(items)
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return {"gcode": gcode_path, "manifest": manifest_path}


def latest_spool_manifest(spool_root: Path) -> Path | None:
    if not spool_root.exists():
        return None
    manifests = sorted(spool_root.glob("*.json"), key=lambda path: path.stat().st_mtime, reverse=True)
    return manifests[0] if manifests else None


def effective_randomness(settings: GuiSettings) -> float:
    return max(0.0, min(settings.randomness * 0.5 + settings.randomness_fine, 100.0))


def _manifest_item_counts(manifest_path: Path | None) -> dict[str, int]:
    if not manifest_path or not manifest_path.exists():
        return {"user": 0, "idle": 0, "total": 0}
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    items = payload.get("items", [])
    if not items and isinstance(payload.get("rows"), list):
        items = [
            item
            for row in payload["rows"]
            if isinstance(row, dict)
            for item in row.get("items", [])
            if isinstance(item, dict)
        ]
    user = sum(1 for item in items if item.get("source_kind") == "user")
    idle = len(items) - user
    return {"user": user, "idle": idle, "total": len(items)}


def _preview_scale(settings: GuiSettings) -> float:
    return PREVIEW_PX_PER_MM


def _preview_image_size(mark_size: float, placement_symbol_scale: float, *, svg_path: Path | None = None) -> float:
    canvas_to_base_ratio = CANONICAL_CANVAS_SIZE / CANONICAL_BASE_DIAMETER
    if svg_path is not None:
        try:
            metadata = read_normalized_svg_metadata(svg_path)
        except Exception:  # noqa: BLE001
            canvas_to_base_ratio = 1.0
        else:
            if metadata.normalized and metadata.base_diameter > 0:
                canvas_to_base_ratio = metadata.canvas_size / metadata.base_diameter
            else:
                canvas_to_base_ratio = 1.0
    return mark_size * canvas_to_base_ratio * max(0.0, placement_symbol_scale)


def _empty_preview_svg(settings: GuiSettings, message: str) -> str:
    scale = _preview_scale(settings)
    width = max(settings.sheet_width_mm * scale, 300)
    height = max(settings.sheet_height_mm * scale, 200)
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width:.2f} {height:.2f}" '
        f'width="{width:.0f}" height="{height:.0f}">'
        '<rect width="100%" height="100%" fill="#fbf7ef"/>'
        f'<text x="{width / 2:.2f}" y="{height / 2:.2f}" text-anchor="middle" '
        f'font-size="18" fill="#8f4f2b">{message}</text></svg>'
    )


def _validated_svg_text(svg_bytes: bytes) -> str:
    if not svg_bytes or not svg_bytes.strip():
        raise ValueError("Uploaded SVG file is empty")
    try:
        root = ET.fromstring(svg_bytes)
    except ET.ParseError as exc:
        raise ValueError(f"Uploaded file is not valid SVG XML: {exc}") from exc
    tag = root.tag.rsplit("}", 1)[-1].lower()
    if tag != "svg":
        raise ValueError("Uploaded file root element must be <svg>")
    try:
        return svg_bytes.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError("Uploaded SVG must be UTF-8 encoded") from exc


def _direct_svg_sheet_id(output_root: Path, now: datetime) -> str:
    base = now.strftime("testsvg_%Y%m%d_%H%M%S")
    candidate = base
    suffix = 1
    while (output_root / f"{candidate}.gcode").exists() or any(output_root.glob(f"{candidate}_*.svg")):
        suffix += 1
        candidate = f"{base}_{suffix:03d}"
    return candidate


def _safe_upload_stem(original_name: str) -> str:
    stem = Path(original_name).stem or "uploaded_svg"
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", stem).strip("._")
    return safe or "uploaded_svg"


def _label_from_upload_name(original_name: str) -> str:
    stem = Path(original_name).stem or "uploaded_svg"
    label = re.sub(r"[^A-Za-z0-9]+", " ", stem).strip().upper()
    return label or "UPLOADED SVG"
