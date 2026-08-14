"""Pen calibration sheet: one print that answers every tuning question at once.

This emits G-code directly rather than an SVG because an SVG cannot encode per-stroke
feed or Z. Varying one parameter per row inside a single print is the whole point --
otherwise tuning three parameters means a separate sheet per candidate value.

Four blocks, each varying exactly one thing with everything else held at the profile's
current value:

    feed ladder    which draw_rate starts to thin or skip
    Z ladder       which z_down_mm inks fully without splaying the nib
    dwell ladder   how long the ink needs before the stroke starts
    geometry       true line width, minimum circle, corner sharpness

Read the best rung off each ladder, type the numbers into CALIBRATION, save the profile.
RUNBOOK.md has the loop.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path

from ...shared.config import PlotterSettings, ensure_dir
from ...shared.gui_settings import GuiSettings
from ..text import shx
from .svg_gcode import _dwell_command, _pen_down_command, _pen_up_command, _xy_acceleration_comment

Polylines = list[list[tuple[float, float]]]

LABEL_FONT_FALLBACK = "zzsimplex"
LABEL_HEIGHT_MM = 3.5
LABEL_COLUMN_MM = 26.0
ROW_PITCH_MM = 9.0
BLOCK_GAP_MM = 10.0
# The geometry shapes stack internally from y=0 to y=34; one row covers all of them.
GEOMETRY_HEIGHT_MM = 58.0
# The geometry row's label is wider than the label column, so its shapes start below it.
GEOMETRY_LABEL_CLEARANCE_MM = 7.0
LINE_LENGTH_MM = 90.0

# The Z ladder is the one block that can wreck a nib, so its rungs are a bounded offset
# around the profile's current pen-down depth, never an absolute sweep.
Z_LADDER_SPAN_MM = 1.0
# Hard floor regardless of what is asked for. Deeper than this and the carriage is
# pressing the pen into the bed rather than the paper.
Z_ABSOLUTE_FLOOR_MM = -30.0


@dataclass(frozen=True)
class PenCalRanges:
    """Rungs for each ladder. Defaults bracket the shipped profile values."""

    draw_rates: tuple[float, ...] = (800.0, 1400.0, 2000.0, 2800.0, 3600.0, 4800.0)
    dwell_ms: tuple[float, ...] = (0.0, 60.0, 120.0, 250.0)
    z_steps: int = 5
    # Half-width of the Z ladder around the current depth. The default matches the old
    # hard-coded span; widen it after a mechanics change, when the profile value is a guess.
    z_span_mm: float = Z_LADDER_SPAN_MM


@dataclass
class _Block:
    """One ladder: rows that each carry their own feed/Z/dwell override."""

    title: str
    rows: list[tuple[str, Polylines, dict[str, float]]] = field(default_factory=list)


def _label(text: str, x_mm: float, y_mm: float, font: str) -> Polylines:
    try:
        return shx.text_polylines(text, font=font, cap_height_mm=LABEL_HEIGHT_MM, origin=(x_mm, y_mm))
    except (ValueError, OSError):
        # A missing font must not cost the operator the whole sheet; the ladder still
        # reads top-to-bottom in the documented order.
        return []


def _label_font() -> str:
    fonts = shx.list_fonts()
    if LABEL_FONT_FALLBACK in fonts:
        return LABEL_FONT_FALLBACK
    return fonts[0] if fonts else ""


def _dash_row(x_mm: float, y_mm: float, count: int = 8, dash_mm: float = 6.0, gap_mm: float = 4.0) -> Polylines:
    """Separate short strokes: one pen-down per dash, which is what a dwell test needs."""
    return [
        [(x_mm + i * (dash_mm + gap_mm), y_mm), (x_mm + i * (dash_mm + gap_mm) + dash_mm, y_mm)] for i in range(count)
    ]


def _solid_row(x_mm: float, y_mm: float, length_mm: float = LINE_LENGTH_MM) -> Polylines:
    return [[(x_mm, y_mm), (x_mm + length_mm, y_mm)]]


def _geometry_rows(x_mm: float, y_mm: float) -> Polylines:
    """Fixed-setting shapes that expose what the pen can actually resolve.

    Returned as one row: each shape carries its own vertical offset inside
    GEOMETRY_HEIGHT_MM, so stacking them on separate row pitches would triple-count the
    height and push the sheet off the bed. The offsets below are chosen so the three
    shape groups do not overlap -- the 16mm circle is tall enough to reach the pairs.
    """
    rows: Polylines = []

    # Line pairs at shrinking separation: the finest pair that still reads as two lines
    # is the real pen width.
    pairs: Polylines = []
    cursor = x_mm
    for gap in (2.0, 1.5, 1.2, 1.0, 0.8, 0.6, 0.5, 0.4, 0.3):
        pairs.append([(cursor, y_mm), (cursor, y_mm + 6.0)])
        pairs.append([(cursor + gap, y_mm), (cursor + gap, y_mm + 6.0)])
        cursor += gap + 6.0
    rows.extend(pairs)

    # Circles down to the size where the pen stops making a closed round shape.
    circles: Polylines = []
    cursor = x_mm
    for diameter in (16.0, 10.0, 6.0, 4.0, 2.5, 1.5, 1.0):
        radius = diameter / 2.0
        centre_x = cursor + radius
        centre_y = y_mm + 20.0
        steps = max(16, int(diameter * 8))
        circles.append(
            [
                (
                    centre_x + radius * math.cos(2 * math.pi * i / steps),
                    centre_y + radius * math.sin(2 * math.pi * i / steps),
                )
                for i in range(steps + 1)
            ]
        )
        cursor += diameter + 4.0
    rows.extend(circles)

    # Sharp corners: overshoot and rounding show up here before anywhere else.
    zig: list[tuple[float, float]] = []
    for i in range(9):
        zig.append((x_mm + i * 10.0, y_mm + 38.0 + (0.0 if i % 2 else 8.0)))
    rows.append(zig)

    return rows


def _build_blocks(settings: GuiSettings, ranges: PenCalRanges) -> list[_Block]:
    left = LABEL_COLUMN_MM
    blocks: list[_Block] = []

    feed = _Block("feed mm/min")
    for rate in ranges.draw_rates:
        feed.rows.append((f"{rate:.0f}", _solid_row(left, 0.0), {"draw_rate": rate}))
    blocks.append(feed)

    # Bounded sweep around the current depth, then clamped to the absolute floor.
    z_block = _Block("pen-down Z mm")
    base_z = float(settings.z_down_mm)
    steps = max(2, ranges.z_steps)
    for index in range(steps):
        offset = -ranges.z_span_mm + (2 * ranges.z_span_mm) * index / (steps - 1)
        depth = max(Z_ABSOLUTE_FLOOR_MM, base_z + offset)
        z_block.rows.append((f"{depth:.2f}", _solid_row(left, 0.0), {"z_down_mm": depth}))
    blocks.append(z_block)

    dwell = _Block("dwell ms")
    for value in ranges.dwell_ms:
        # Dashes, not one long line: dwell only shows at stroke starts, so the row needs
        # many of them.
        dwell.rows.append((f"{value:.0f}", _dash_row(left, 0.0), {"pen_down_dwell_ms": value}))
    blocks.append(dwell)

    geometry = _Block("geometry")
    # Shapes start below GEOMETRY_LABEL_CLEARANCE_MM: the row label is wider than the
    # label column and would otherwise be drawn straight through the line pairs.
    geometry.rows.append(("pairs / circles / corners", _geometry_rows(left, GEOMETRY_LABEL_CLEARANCE_MM), {}))
    blocks.append(geometry)

    return blocks


def _offset(polylines: Polylines, dy_mm: float) -> Polylines:
    return [[(x, y + dy_mm) for x, y in polyline] for polyline in polylines]


def build_pen_cal_gcode(
    settings: GuiSettings,
    *,
    ranges: PenCalRanges | None = None,
    origin_x_mm: float | None = None,
    origin_y_mm: float | None = None,
) -> tuple[str, dict[str, object]]:
    """Return (gcode, manifest). Raises ValueError if the sheet will not fit the bed."""
    ranges = ranges or PenCalRanges()
    plotter = PlotterSettings()
    font = _label_font()
    origin_x = settings.direct_svg_origin_x_mm if origin_x_mm is None else origin_x_mm
    origin_y = settings.direct_svg_origin_y_mm if origin_y_mm is None else origin_y_mm

    pen_up = _pen_up_command(plotter.pen_up_command, use_z_servo=plotter.use_z_servo, z_up_mm=settings.z_up_mm)
    lines = [
        "; Neje Oracle pen calibration",
        f"; profile {settings.pen_profile or '(unsaved)'}",
        "; each block varies ONE parameter; everything else is at the profile's value",
        _xy_acceleration_comment(settings.xy_acceleration_mm_s2),
        "G21",
        "G90",
        f"G0 F{settings.travel_rate:.2f}",
        pen_up,
    ]

    drawn: list[tuple[float, float]] = []
    used: list[dict[str, object]] = []
    cursor_y = 0.0

    for block in _build_blocks(settings, ranges):
        lines.append(f"; --- {block.title} ---")
        header = _label(block.title, 0.0, cursor_y, font) if font else []
        for polyline in header:
            drawn.extend(polyline)
        _emit(lines, header, settings, plotter, {}, origin_x, origin_y, pen_up)
        cursor_y += ROW_PITCH_MM * 0.8

        for label_text, polylines, overrides in block.rows:
            placed = _offset(polylines, cursor_y)
            tag = _label(label_text, 0.0, cursor_y, font) if font else []
            lines.append(f"; {block.title} = {label_text}")
            _emit(lines, tag, settings, plotter, {}, origin_x, origin_y, pen_up)
            _emit(lines, placed, settings, plotter, overrides, origin_x, origin_y, pen_up)
            for polyline in placed + tag:
                drawn.extend(polyline)
            used.append({"block": block.title, "value": label_text, **overrides})
            cursor_y += GEOMETRY_HEIGHT_MM if block.title == "geometry" else ROW_PITCH_MM

        cursor_y += BLOCK_GAP_MM

    lines.append(pen_up)
    lines.append("G0 X0 Y0")

    if not drawn:
        raise ValueError("pen calibration sheet produced no geometry")
    max_x = max(x for x, _ in drawn) + origin_x
    max_y = max(y for _, y in drawn) + origin_y
    if max_x > settings.sheet_width_mm or max_y > settings.sheet_height_mm:
        raise ValueError(
            f"pen calibration sheet needs {max_x:.0f}x{max_y:.0f}mm which exceeds the "
            f"{settings.sheet_width_mm:.0f}x{settings.sheet_height_mm:.0f}mm sheet"
        )

    manifest: dict[str, object] = {
        "profile": settings.pen_profile,
        "base": {
            "draw_rate": settings.draw_rate,
            "travel_rate": settings.travel_rate,
            "z_down_mm": settings.z_down_mm,
            "z_up_mm": settings.z_up_mm,
            "z_feed_mm_min": settings.z_feed_mm_min,
            "pen_down_dwell_ms": settings.pen_down_dwell_ms,
            "pen_width_mm": settings.pen_width_mm,
        },
        "rows": used,
        "extent_mm": [round(max_x, 2), round(max_y, 2)],
        "origin_mm": [origin_x, origin_y],
        "z_floor_mm": Z_ABSOLUTE_FLOOR_MM,
    }
    return "\n".join(lines) + "\n", manifest


def _emit(
    lines: list[str],
    polylines: Polylines,
    settings: GuiSettings,
    plotter: PlotterSettings,
    overrides: dict[str, float],
    origin_x: float,
    origin_y: float,
    pen_up: str,
) -> None:
    """Emit one row, applying its per-row parameter override."""
    if not polylines:
        return
    draw_rate = overrides.get("draw_rate", settings.draw_rate)
    # Clamped here rather than only where the ladder is built: the geometry block has no
    # Z override and would otherwise emit the raw setting, so a mis-set z_down_mm would
    # drive the pen into the bed on every block except the one guarded ladder.
    z_down = max(Z_ABSOLUTE_FLOOR_MM, overrides.get("z_down_mm", settings.z_down_mm))
    dwell_ms = overrides.get("pen_down_dwell_ms", settings.pen_down_dwell_ms)
    pen_down = _pen_down_command(
        plotter.pen_down_command,
        use_z_servo=plotter.use_z_servo,
        z_down_mm=z_down,
        z_feed_mm_min=settings.z_feed_mm_min,
    )
    dwell = _dwell_command(dwell_ms)

    lines.append(f"G1 F{draw_rate:.2f}")
    for polyline in polylines:
        start_x, start_y = polyline[0]
        lines.append(f"G0 X{start_x + origin_x:.3f} Y{start_y + origin_y:.3f}")
        lines.append(pen_down)
        if dwell is not None:
            lines.append(dwell)
        for x, y in polyline[1:]:
            lines.append(f"G1 X{x + origin_x:.3f} Y{y + origin_y:.3f}")
        lines.append(pen_up)


def build_z_range_gcode(
    settings: GuiSettings,
    *,
    depth_start_mm: float = 0.0,
    depth_stop_mm: float = -12.0,
    depth_step_mm: float = 0.5,
    clearance_heights_mm: tuple[float, ...] = (-8.0, -6.0, -4.0, -2.0, 0.0),
    origin_x_mm: float | None = None,
    origin_y_mm: float | None = None,
) -> tuple[str, dict[str, object]]:
    """Full-range Z discovery sheet, for after a mechanics change.

    Unlike the pen-cal ladder (a bounded sweep around a trusted profile depth), this
    sweeps depth absolutely from depth_start_mm down to depth_stop_mm: the first rung
    that marks is the touch depth, the rung where the line stops widening is full ink,
    and anything deeper is the servo stalling against the physical stop. A second block
    sweeps pen-UP heights, deepest first: the shallowest rung whose gap stays clean is
    the new z_up_mm. Both are clamped to Z_ABSOLUTE_FLOOR_MM regardless of arguments.
    """
    if depth_step_mm <= 0:
        raise ValueError("depth_step_mm must be positive")
    plotter = PlotterSettings()
    font = _label_font()
    origin_x = settings.direct_svg_origin_x_mm if origin_x_mm is None else origin_x_mm
    origin_y = settings.direct_svg_origin_y_mm if origin_y_mm is None else origin_y_mm
    default_pen_up = _pen_up_command(plotter.pen_up_command, use_z_servo=plotter.use_z_servo, z_up_mm=settings.z_up_mm)

    lines = [
        "; Neje Oracle Z range calibration",
        "; block 1: absolute pen-down depths -- first mark = touch, stable width = full ink",
        "; block 2: pen-up heights, deepest first -- shallowest clean gap = new z_up",
        _xy_acceleration_comment(settings.xy_acceleration_mm_s2),
        "G21",
        "G90",
        f"G0 F{settings.travel_rate:.2f}",
        default_pen_up,
    ]
    drawn: list[tuple[float, float]] = []
    used: list[dict[str, object]] = []
    cursor_y = 0.0
    left = LABEL_COLUMN_MM
    row_pitch = 6.0  # shallower rows than pen-cal: many rungs, each a short line
    # Labels must not trust the profile's z_down: after a mechanics change it can sit far
    # past the new physical stop (the reason this sheet exists). The deepest swept rung is
    # the deepest Z this sheet ever commands, labels included.
    label_overrides = {"z_down_mm": max(Z_ABSOLUTE_FLOOR_MM, depth_stop_mm)}

    def _block_header(title: str) -> None:
        nonlocal cursor_y
        lines.append(f"; --- {title} ---")
        header = _label(title, 0.0, cursor_y, font) if font else []
        for polyline in header:
            drawn.extend(polyline)
        _emit(lines, header, settings, plotter, label_overrides, origin_x, origin_y, default_pen_up)
        cursor_y += ROW_PITCH_MM * 0.8

    _block_header("pen-down Z mm (absolute)")
    depth = depth_start_mm
    while depth >= depth_stop_mm - 1e-9:
        clamped = max(Z_ABSOLUTE_FLOOR_MM, depth)
        row = _offset(_solid_row(left, 0.0, length_mm=40.0), cursor_y)
        tag = _label(f"{clamped:.1f}", 0.0, cursor_y, font) if font else []
        lines.append(f"; depth = {clamped:.1f}")
        _emit(lines, tag, settings, plotter, label_overrides, origin_x, origin_y, default_pen_up)
        _emit(lines, row, settings, plotter, {"z_down_mm": clamped}, origin_x, origin_y, default_pen_up)
        for polyline in row + tag:
            drawn.extend(polyline)
        used.append({"block": "depth", "z_down_mm": clamped})
        cursor_y += row_pitch
        depth -= depth_step_mm
    cursor_y += BLOCK_GAP_MM

    _block_header("pen-up clearance Z mm")
    # z_down for this block: the deepest depth that was swept above, so drag (if any)
    # happens against real ink pressure, not a barely-touching nib.
    clearance_down = max(Z_ABSOLUTE_FLOOR_MM, depth_stop_mm)
    for height in sorted(clearance_heights_mm):  # deepest first
        clamped_up = max(Z_ABSOLUTE_FLOOR_MM, min(0.0, height))
        row_pen_up = _pen_up_command(plotter.pen_up_command, use_z_servo=plotter.use_z_servo, z_up_mm=clamped_up)
        # Two strokes with a 20 mm travel between them at this pen-up height: a drag
        # mark in the gap disqualifies the rung.
        strokes = _offset(
            [[(left, 0.0), (left + 25.0, 0.0)], [(left + 45.0, 0.0), (left + 70.0, 0.0)]],
            cursor_y,
        )
        tag = _label(f"{clamped_up:.1f}", 0.0, cursor_y, font) if font else []
        lines.append(f"; clearance = {clamped_up:.1f}")
        _emit(lines, tag, settings, plotter, label_overrides, origin_x, origin_y, default_pen_up)
        _emit(lines, strokes, settings, plotter, {"z_down_mm": clearance_down}, origin_x, origin_y, row_pen_up)
        for polyline in strokes + tag:
            drawn.extend(polyline)
        used.append({"block": "clearance", "z_up_mm": clamped_up})
        cursor_y += row_pitch
    lines.append(default_pen_up)
    lines.append("G0 X0 Y0")

    max_x = max(x for x, _ in drawn) + origin_x
    max_y = max(y for _, y in drawn) + origin_y
    if max_x > settings.sheet_width_mm or max_y > settings.sheet_height_mm:
        raise ValueError(
            f"z range sheet needs {max_x:.0f}x{max_y:.0f}mm which exceeds the "
            f"{settings.sheet_width_mm:.0f}x{settings.sheet_height_mm:.0f}mm sheet"
        )

    manifest: dict[str, object] = {
        "profile": settings.pen_profile,
        "rows": used,
        "extent_mm": [round(max_x, 2), round(max_y, 2)],
        "origin_mm": [origin_x, origin_y],
        "z_floor_mm": Z_ABSOLUTE_FLOOR_MM,
    }
    return "\n".join(lines) + "\n", manifest


def generate_z_range_sheet(
    settings: GuiSettings,
    *,
    spool_root: Path | None = None,
    **kwargs: float,
) -> dict[str, Path]:
    """Write the Z range sheet into the spool, next to the pen-cal sheets."""
    gcode, manifest = build_z_range_gcode(settings, **kwargs)
    output_root = spool_root or PlotterSettings().spool_root
    ensure_dir(output_root)
    gcode_path = output_root / "z_range_cal.gcode"
    manifest_path = output_root / "z_range_cal.json"
    gcode_path.write_text(gcode, encoding="utf-8")
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return {"gcode": gcode_path, "manifest": manifest_path}


def generate_pen_cal_sheet(
    settings: GuiSettings,
    *,
    ranges: PenCalRanges | None = None,
    spool_root: Path | None = None,
) -> dict[str, Path]:
    """Write the sheet and its manifest into the spool, like generate_dry_run_sheet."""
    gcode, manifest = build_pen_cal_gcode(settings, ranges=ranges)
    output_root = spool_root or PlotterSettings().spool_root
    ensure_dir(output_root)
    sheet_id = f"pen_cal_{settings.pen_profile or 'unsaved'}"
    gcode_path = output_root / f"{sheet_id}.gcode"
    manifest_path = output_root / f"{sheet_id}.json"
    gcode_path.write_text(gcode, encoding="utf-8")
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return {"gcode": gcode_path, "manifest": manifest_path}
