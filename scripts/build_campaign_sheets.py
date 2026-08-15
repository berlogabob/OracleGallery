#!/usr/bin/env python3
"""Build the pen-campaign evidence sheets for plotting on paper (RUNBOOK section 9b).

Writes three regenerable sheets per pen profile into runtime/physical_tests/:

    10_modes_<pen>.svg      wave-H / wave-V / wave-one-line / flow / flow-dash cells
                            plus trace and hatch regression cells, all from one
                            deterministic test image, sampling floored by the nib
    11_generators_<pen>.svg ribbon / bloom / vine from the real sketch.js generator
                            (node harness, fixed seed -- the same geometry for every
                            pen, so plots are comparable across pens)
    12_liftbudget_<pen>.svg one dither render at lift budgets off / 256 / 64 / 8 / 0,
                            to judge connector acceptability and time savings

Like build_bank_test_sheet.py, the sheets are sized to the operator's live sheet
settings and the cost line is measured on the polylines as they will be plotted.

    uv run python scripts/build_campaign_sheets.py --pen fineliner
    uv run python scripts/build_campaign_sheets.py --pen all
"""

from __future__ import annotations

import argparse
import io
import json
import math
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from neje_oracle.blocks.gcode.svg_gcode import svg_to_polylines_mm  # noqa: E402
from neje_oracle.blocks.gui.support import load_gui_settings, plot_minutes_for  # noqa: E402
from neje_oracle.blocks.gui.workspaces.generative import sketch_canvas_mm  # noqa: E402
from neje_oracle.blocks.imaging.modes import (  # noqa: E402
    Polylines,
    image_to_polylines,
    polylines_to_svg,
    travel_length_mm,
)
from neje_oracle.blocks.imaging.sheet import build_frame_grid, cell_outline  # noqa: E402
from neje_oracle.blocks.text import shx  # noqa: E402
from neje_oracle.shared.config import PlotterSettings  # noqa: E402
from neje_oracle.shared.pathops import join_with_budget  # noqa: E402
from neje_oracle.shared.pen_profiles import apply_pen_profile, load_pen_profiles  # noqa: E402

HARNESS = REPO_ROOT / "echodraw" / "generative-core" / "web" / "_harness.mjs"
OUT_DIR = REPO_ROOT / "runtime" / "physical_tests"
LABEL_MM = 3.5
MARGIN_MM = 8.0
GAP_MM = 6.0
COLUMNS = 3
GENERATOR_SEED = 12345  # fixed inside _harness.mjs; recorded here for the manifest
LIFT_BUDGETS = ("off", 256, 64, 8, 0)


def _test_image() -> bytes:
    """One deterministic raster: a tone ramp, a dark disc and a hard-edged bar.

    Synthesized rather than shipped as a binary asset so it can never drift from the
    script that interprets it. The ramp shows density response (wave/flow/hatch), the
    disc gives flow a form to wrap around, the bar gives trace a clean edge.
    """
    from PIL import Image, ImageDraw

    size = 320
    image = Image.new("L", (size, size))
    image.putdata([int(255 * x / (size - 1)) for _ in range(size) for x in range(size)])
    draw = ImageDraw.Draw(image)
    draw.ellipse((size * 0.15, size * 0.15, size * 0.55, size * 0.55), fill=30)
    draw.rectangle((size * 0.62, size * 0.62, size * 0.72, size * 0.95), fill=255)
    draw.rectangle((size * 0.74, size * 0.62, size * 0.84, size * 0.95), fill=0)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _label(text: str, x_mm: float, y_mm: float, font: str) -> Polylines:
    # Same tolerance as pen_cal: a missing font must not cost the sheet.
    if not font:
        return []
    try:
        return shx.text_polylines(text, font=font, cap_height_mm=LABEL_MM, origin=(x_mm, y_mm))
    except (ValueError, OSError):
        return []


def _label_font() -> str:
    fonts = shx.list_fonts()
    return "zzsimplex" if "zzsimplex" in fonts else (fonts[0] if fonts else "")


def _fit_into_cell(polylines: Polylines, center_x: float, center_y: float, art_mm: float) -> Polylines:
    """Scale arbitrary-frame polylines to fit an art_mm square, centred, aspect kept."""
    points = [point for line in polylines for point in line]
    if not points:
        return []
    min_x, max_x = min(x for x, _ in points), max(x for x, _ in points)
    min_y, max_y = min(y for _, y in points), max(y for _, y in points)
    span = max(max_x - min_x, max_y - min_y) or 1.0
    scale = art_mm / span
    offset_x = center_x - (min_x + max_x) / 2.0 * scale
    offset_y = center_y - (min_y + max_y) / 2.0 * scale
    return [[(x * scale + offset_x, y * scale + offset_y) for x, y in line] for line in polylines]


def _grid(count: int, width_mm: float, height_mm: float) -> tuple[list[tuple[float, float]], float]:
    """Square cell centres sized so `count` cells fit the sheet, plus the cell side."""
    rows = math.ceil(count / COLUMNS)
    # The 0.1 mm shave keeps an exactly-filling side from losing a column to
    # build_frame_grid's floor-divide on float noise.
    side = (
        min(
            (width_mm - 2 * MARGIN_MM - (COLUMNS - 1) * GAP_MM) / COLUMNS,
            # Each row also carries a text label under the cell.
            (height_mm - 2 * MARGIN_MM - (rows - 1) * GAP_MM) / rows - (LABEL_MM + 2.0),
        )
        - 0.1
    )
    centers = build_frame_grid(
        count,
        sheet_width_mm=width_mm,
        sheet_height_mm=height_mm,
        margin_mm=MARGIN_MM,
        cell_width_mm=side,
        cell_height_mm=side + LABEL_MM + 2.0,
        gap_mm=GAP_MM,
    )
    if not centers:
        raise ValueError(f"sheet {width_mm:.0f}x{height_mm:.0f} mm cannot fit {count} campaign cells")
    # build_frame_grid centres include the label strip; shift art centres up by half of it.
    return [(x, y - (LABEL_MM + 2.0) / 2.0) for x, y in centers], side


def _assemble(
    cells: list[tuple[str, Polylines]],
    width_mm: float,
    height_mm: float,
    title: str,
    font: str,
) -> tuple[Polylines, dict[str, int]]:
    centers, side = _grid(len(cells), width_mm, height_mm)
    art_mm = side - 4.0
    sheet: Polylines = list(_label(title, MARGIN_MM, 1.0, font))
    counts: dict[str, int] = {}
    for (name, art), (center_x, center_y) in zip(cells, centers, strict=True):
        placed = _fit_into_cell(art, center_x, center_y, art_mm)
        counts[name] = len(placed)
        sheet.extend(cell_outline(center_x, center_y, side, side, "rect"))
        sheet.extend(placed)
        sheet.extend(_label(name, center_x - side / 2.0, center_y + side / 2.0 + 1.5, font))
    return sheet, counts


def _check_bounds(polylines: Polylines, width_mm: float, height_mm: float, name: str) -> None:
    for line in polylines:
        for x, y in line:
            if not (-0.01 <= x <= width_mm + 0.01 and -0.01 <= y <= height_mm + 0.01):
                raise ValueError(f"{name}: point ({x:.1f}, {y:.1f}) outside the {width_mm:.0f}x{height_mm:.0f} mm sheet")


def _generator_polylines(names: tuple[str, ...]) -> dict[str, Polylines]:
    """The real sketch.js generators, run once under node at the harness's fixed seed."""
    node = shutil.which("node")
    if node is None:
        raise RuntimeError("node not found; install Node to build the generator sheet (the sketch is JS)")
    with tempfile.TemporaryDirectory() as scratch:
        subprocess.run([node, str(HARNESS), scratch], check=True, capture_output=True)
        return {name: svg_to_polylines_mm(Path(scratch) / f"{name}.svg", 1.0) for name in names}


def build_sheets(pen: str, out_dir: Path | None = None, settings=None) -> dict[str, dict]:
    settings = settings or load_gui_settings()
    apply_pen_profile(settings, pen)  # in memory only; nothing is saved back
    out = out_dir or OUT_DIR
    out.mkdir(parents=True, exist_ok=True)
    width_mm, height_mm = sketch_canvas_mm(settings)
    pen_w = float(settings.pen_width_mm)
    font = _label_font()
    image = _test_image()
    # A lattice finer than the nib fills in solid (RUNBOOK section 4), so both the
    # sampling pitch and the hatch spacing scale with the fitted pen's width.
    cell_mm = max(1.0, pen_w * 2.0)
    art_kwargs = dict(cell_mm=cell_mm, autocontrast=False)

    def render(mode: str, **params) -> Polylines:
        return image_to_polylines(image, mode=mode, width_mm=50.0, height_mm=50.0, **art_kwargs, **params)

    sheets: dict[str, tuple[Polylines, dict[str, int]]] = {}

    mode_cells = [
        ("wave-H", render("wave", orientation="horizontal")),
        ("wave-V", render("wave", orientation="vertical")),
        ("wave-1line", render("wave", connect_rows=True)),
        ("flow", render("flow")),
        ("flow-dash", render("flow", dash_mm=3.0)),
        ("trace", render("trace")),
        ("hatch", render("hatch", line_spacing_mm=max(1.0, pen_w * 3.0))),
    ]
    sheets[f"10_modes_{pen}.svg"] = _assemble(mode_cells, width_mm, height_mm, f"10 MODES {pen}", font)

    generators = _generator_polylines(("ribbon", "bloom", "vine"))
    # The harness already runs every generator at density 1.0 -- for bloom that is the
    # deliberately-high density that probes the ring-crossing risk on paper.
    generator_cells = [(name, generators[name]) for name in ("ribbon", "bloom", "vine")]
    sheets[f"11_generators_{pen}.svg"] = _assemble(generator_cells, width_mm, height_mm, f"11 GENERATORS {pen}", font)

    lift_source = render("dither")
    budget_cells = [
        (f"lifts-{budget}", lift_source if budget == "off" else join_with_budget(lift_source, int(budget)))
        for budget in LIFT_BUDGETS
    ]
    sheets[f"12_liftbudget_{pen}.svg"] = _assemble(budget_cells, width_mm, height_mm, f"12 LIFT BUDGET {pen}", font)

    stats: dict[str, dict] = {}
    for filename, (polylines, counts) in sheets.items():
        _check_bounds(polylines, width_mm, height_mm, filename)
        (out / filename).write_text(polylines_to_svg(polylines, width_mm=width_mm, height_mm=height_mm, pen_width_mm=pen_w))
        draw_mm, travel_mm = travel_length_mm(polylines)
        xy_minutes, pen_minutes = plot_minutes_for(
            settings,
            strokes=len(polylines),
            draw_mm=draw_mm,
            travel_mm=travel_mm,
            use_z_servo=PlotterSettings().use_z_servo,
        )
        stats[filename] = {
            "strokes": len(polylines),
            "cells": counts,
            "minutes": round(xy_minutes + pen_minutes, 1),
            "draw_m": round(draw_mm / 1000, 2),
            "travel_m": round(travel_mm / 1000, 2),
            "seed": GENERATOR_SEED,
        }
    return stats


def main() -> int:
    profiles = sorted(load_pen_profiles())
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--pen", required=True, choices=[*profiles, "all"], help="pen profile, or 'all'")
    parser.add_argument("--out", type=Path, default=None, help=f"output dir (default {OUT_DIR})")
    args = parser.parse_args()

    for pen in profiles if args.pen == "all" else [args.pen]:
        stats = build_sheets(pen, args.out)
        for filename, sheet in stats.items():
            print(
                f"wrote {filename}: {sheet['strokes']} strokes, {sheet['draw_m']} m drawn"
                f" + {sheet['travel_m']} m travel, ~{sheet['minutes']} min"
            )
            print("  cells  " + "  ".join(f"{name}:{count}" for name, count in sheet["cells"].items()))
    print("\nPrint via the GUI: SETUP -> VERIFY -> START SVG PRINT, per sheet.")
    print("Protocol and result matrix: reports/CAMPAIGN_10_PENS_AND_MODES.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
