from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from ...shared.config import SYMBOL_FIT_RATIO, PlotterSettings, ensure_dir
from ...shared.gui_settings import GuiSettings, gui_settings_to_plotter_config
from ...shared.models import SheetItem
from ...shared.origin_markers import ORIGIN_FILLER_MACBOOK, marker_position_for_origin, normalize_tags
from ...shared.symbols import list_base_symbols, load_symbol_scales
from ..symbols.svg_normalizer import normalize_svg_file
from .layout import _build_layout_for_settings, layout_capacity
from .sampling import compute_effective_sample_step
from .svg_gcode import generate_sheet_gcode


def generate_dry_run_sheet(
    settings: GuiSettings,
    *,
    spool_root: Path | None = None,
    symbol_root: Path | None = None,
) -> dict[str, Path]:
    output_root = spool_root or PlotterSettings().spool_root
    ensure_dir(output_root)
    symbols = list_base_symbols(symbol_root)
    if not symbols:
        raise FileNotFoundError("No symbols available for G-code-only sheet generation")
    scales = load_symbol_scales(symbol_root=symbol_root)
    cache_dir = output_root / "cache"
    ensure_dir(cache_dir)
    config = gui_settings_to_plotter_config(settings)
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
        sample_step_mm=config.sample_step_mm,
        cell_diameter_mm=config.cell_diameter_mm,
        sample_reference_cell_mm=config.sample_reference_cell_mm,
        sample_density_exponent=config.sample_density_exponent,
        sample_min_step_mm=config.sample_min_step_mm,
        sample_max_step_mm=config.sample_max_step_mm,
    )
    gcode = generate_sheet_gcode(
        items,
        placements,
        sample_step_mm=effective_step,
        cell_diameter_mm=config.cell_diameter_mm,
        travel_rate=config.travel_rate,
        draw_rate=config.draw_rate,
        xy_acceleration_mm_s2=config.xy_acceleration_mm_s2,
        pen_up_command=PlotterSettings().pen_up_command,
        pen_down_command=PlotterSettings().pen_down_command,
        include_rings=config.include_rings,
        include_markers=config.include_markers,
        marker_diameter_mm=config.marker_diameter_mm,
        use_z_servo=PlotterSettings().use_z_servo,
        z_down_mm=config.z_down_mm,
        z_up_mm=config.z_up_mm,
        z_feed_mm_min=config.z_feed_mm_min,
        pen_down_dwell_ms=config.pen_down_dwell_ms,
    )
    gcode_path = output_root / f"{sheet_id}.gcode"
    manifest_path = output_root / f"{sheet_id}.json"
    gcode_path.write_text(gcode, encoding="utf-8")
    manifest_path.write_text(
        json.dumps(
            {
                "sheet_id": sheet_id,
                "generated_by": "neje-gui",
                "layout_mode": config.layout_mode,
                "cell_diameter_mm": config.cell_diameter_mm,
                "gap_mm": config.gap_mm,
                "organic_enabled": config.organic_enabled,
                "organic_cell_size_mm": config.organic_cell_size_mm,
                "organic_rotation_ramp": config.organic_rotation_ramp,
                "organic_scale_ramp": config.organic_scale_ramp,
                "organic_seed": config.organic_seed,
                "symbol_fit_ratio": SYMBOL_FIT_RATIO,
                "include_markers": config.include_markers,
                "marker_diameter_mm": config.marker_diameter_mm,
                "sample_step_mm": config.sample_step_mm,
                "sample_reference_cell_mm": config.sample_reference_cell_mm,
                "sample_density_exponent": config.sample_density_exponent,
                "sample_min_step_mm": config.sample_min_step_mm,
                "sample_max_step_mm": config.sample_max_step_mm,
                "effective_sample_step_mm": effective_step,
                "streaming_mode": config.streaming_mode,
                "xy_acceleration_mm_s2": config.xy_acceleration_mm_s2,
                "items": [
                    {
                        "session_id": item.session_id,
                        "source_kind": item.source_kind,
                        "origin": item.origin,
                        "tags": item.tags,
                        "marker_position": item.marker_position,
                        "marker_diameter_mm": config.marker_diameter_mm,
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
