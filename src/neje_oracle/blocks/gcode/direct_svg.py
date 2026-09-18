from __future__ import annotations

import re
import tempfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from ...shared.config import PlotterSettings, ensure_dir
from ...shared.gui_settings import GuiSettings, gui_settings_to_plotter_config
from .sampling import compute_effective_sample_step
from .svg_gcode import generate_absolute_svg_gcode, svg_to_polylines_mm


@dataclass(frozen=True)
class DirectSvgPrintJob:
    sheet_id: str
    svg_path: Path
    original_name: str
    label: str
    gcode: str
    effective_sample_step_mm: float


def effective_sample_step(settings: GuiSettings) -> float:
    """The step the print path samples an SVG at, given the operator's sampling knobs.

    Split out because the outline trace (gcode/pen_cal.outline_gcode) has to read the same
    geometry the print will send: sampled coarser, a curve's extent shrinks, and an outline
    that says the art fits would not be evidence that the print does.
    """
    config = gui_settings_to_plotter_config(settings)
    return compute_effective_sample_step(
        sample_step_mm=config.sample_step_mm,
        cell_diameter_mm=config.cell_diameter_mm,
        sample_reference_cell_mm=config.sample_reference_cell_mm,
        sample_density_exponent=config.sample_density_exponent,
        sample_min_step_mm=config.sample_min_step_mm,
        sample_max_step_mm=config.sample_max_step_mm,
    )


def build_svg_polylines(settings: GuiSettings, svg_bytes: bytes) -> list[list[tuple[float, float]]]:
    """The drawing in mm, before any origin shift, sampled as the print path samples it."""
    with tempfile.NamedTemporaryFile(suffix=".svg", delete=False) as handle:
        handle.write(svg_bytes)
        path = Path(handle.name)
    try:
        return svg_to_polylines_mm(path, effective_sample_step(settings))
    finally:
        path.unlink(missing_ok=True)


def build_svg_gcode(
    svg_path: Path,
    settings: GuiSettings,
    plotter_settings: PlotterSettings,
    *,
    title: str = "direct SVG",
) -> tuple[str, float]:
    """(gcode, effective_sample_step_mm) for `svg_path` under `settings`, as the print path builds it.

    The print job below and the GUI's plot-time estimate (ui.py) both call this, so the long
    argument list to generate_absolute_svg_gcode lives in exactly one place -- the two paths
    cannot silently drift apart on a rate, a bound, or an origin.
    """
    config = gui_settings_to_plotter_config(settings)
    effective_step = effective_sample_step(settings)
    gcode = generate_absolute_svg_gcode(
        svg_path,
        sample_step_mm=effective_step,
        travel_rate=config.travel_rate,
        draw_rate=config.draw_rate,
        xy_acceleration_mm_s2=config.xy_acceleration_mm_s2,
        pen_up_command=plotter_settings.pen_up_command,
        pen_down_command=plotter_settings.pen_down_command,
        title=title,
        return_home=True,
        use_z_servo=plotter_settings.use_z_servo,
        z_down_mm=config.z_down_mm,
        z_up_mm=config.z_up_mm,
        z_feed_mm_min=config.z_feed_mm_min,
        pen_down_dwell_ms=config.pen_down_dwell_ms,
        origin_x_mm=settings.direct_svg_origin_x_mm,
        origin_y_mm=settings.direct_svg_origin_y_mm,
        keep_non_negative=True,
        # Bound against the operator's configured sheet, not the PlotterSettings default.
        # These used to read resolved_plotter_settings, so a 200x200 sheet was validated
        # against 250x440 and oversized art was accepted.
        max_x_mm=config.sheet_width_mm,
        max_y_mm=config.sheet_height_mm,
    )
    return gcode, effective_step


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

    gcode, effective_step = build_svg_gcode(svg_file, settings, resolved_plotter_settings, title=f"direct SVG {label}")
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
