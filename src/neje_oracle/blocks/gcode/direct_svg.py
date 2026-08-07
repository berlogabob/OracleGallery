from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from ...shared.config import PlotterSettings, ensure_dir
from ...shared.gui_settings import GuiSettings, gui_settings_to_plotter_config
from .sampling import compute_effective_sample_step
from .svg_gcode import generate_absolute_svg_gcode


@dataclass(frozen=True)
class DirectSvgPrintJob:
    sheet_id: str
    svg_path: Path
    original_name: str
    label: str
    gcode: str
    effective_sample_step_mm: float


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

    config = gui_settings_to_plotter_config(settings)
    effective_step = compute_effective_sample_step(
        sample_step_mm=config.sample_step_mm,
        cell_diameter_mm=config.cell_diameter_mm,
        sample_reference_cell_mm=config.sample_reference_cell_mm,
        sample_density_exponent=config.sample_density_exponent,
        sample_min_step_mm=config.sample_min_step_mm,
        sample_max_step_mm=config.sample_max_step_mm,
    )
    gcode = generate_absolute_svg_gcode(
        svg_file,
        sample_step_mm=effective_step,
        travel_rate=config.travel_rate,
        draw_rate=config.draw_rate,
        xy_acceleration_mm_s2=config.xy_acceleration_mm_s2,
        pen_up_command=resolved_plotter_settings.pen_up_command,
        pen_down_command=resolved_plotter_settings.pen_down_command,
        title=f"direct SVG {label}",
        return_home=True,
        use_z_servo=resolved_plotter_settings.use_z_servo,
        z_down_mm=config.z_down_mm,
        z_up_mm=config.z_up_mm,
        z_feed_mm_min=config.z_feed_mm_min,
        origin_x_mm=settings.direct_svg_origin_x_mm,
        origin_y_mm=settings.direct_svg_origin_y_mm,
        keep_non_negative=True,
        # Bound against the operator's configured sheet, not the PlotterSettings default.
        # These used to read resolved_plotter_settings, so a 200x200 sheet was validated
        # against 250x440 and oversized art was accepted.
        max_x_mm=config.sheet_width_mm,
        max_y_mm=config.sheet_height_mm,
    )
    return DirectSvgPrintJob(
        sheet_id=sheet_id,
        svg_path=svg_file,
        original_name=original_name,
        label=label,
        gcode=gcode,
        effective_sample_step_mm=effective_step,
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
