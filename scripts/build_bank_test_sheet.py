#!/usr/bin/env python3
"""Build the pattern-bank evidence sheet for plotting on paper.

Writes runtime/physical_tests/09_bank.svg: the bank generator at mix 0 / 50 / 100 plus a
row of every motif in assets/patterns/, on one sheet sized to the operator's current bed.

The geometry comes from the real sketch.js generator run under Node, not a Python
re-implementation -- what gets plotted has to be what the sketch produces.

The earlier sheets in runtime/physical_tests/ were built ad hoc and cannot be regenerated
after a defaults change; this one can. runtime/ is gitignored, so the sheet is a local
artefact and only this script is tracked.

    uv run python scripts/build_bank_test_sheet.py
"""

from __future__ import annotations

import json
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
from neje_oracle.blocks.imaging.modes import travel_length_mm  # noqa: E402
from neje_oracle.blocks.patterns import bank  # noqa: E402
from neje_oracle.shared.config import PlotterSettings  # noqa: E402

BUILDER = REPO_ROOT / "echodraw" / "generative-core" / "web" / "_bank_sheet.mjs"
OUTPUT = REPO_ROOT / "runtime" / "physical_tests" / "09_bank.svg"


def main() -> int:
    node = shutil.which("node")
    if node is None:
        print("node not found; install Node to build the sheet (the sketch generator is JS)")
        return 1

    motifs = bank.load_bank()
    if not motifs:
        print(f"pattern bank is empty: put some SVGs in {bank.BANK_DIR}")
        return 1

    settings = load_gui_settings()
    width_mm, height_mm = sketch_canvas_mm(settings)
    payload = {
        "canvas": {"width_mm": width_mm, "height_mm": height_mm},
        "motifs": {
            name: [[[round(x, 4), round(y, 4)] for x, y in line] for line in polylines]
            for name, polylines in motifs.items()
        },
    }

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as handle:
        json.dump(payload, handle)
        bank_json = Path(handle.name)
    try:
        result = subprocess.run(
            [node, str(BUILDER), str(bank_json), str(OUTPUT)],
            check=True,
            capture_output=True,
            text=True,
        )
    finally:
        bank_json.unlink(missing_ok=True)

    stats = json.loads(result.stdout.strip().splitlines()[-1])

    # Re-read through the same parser the print path uses, so the reported cost is the
    # cost of the file as it will actually be plotted -- not of the shapes we just built.
    polylines = svg_to_polylines_mm(OUTPUT, 1.0)
    draw_mm, travel_mm = travel_length_mm(polylines)
    xy_minutes, pen_minutes = plot_minutes_for(
        settings,
        strokes=len(polylines),
        draw_mm=draw_mm,
        travel_mm=travel_mm,
        use_z_servo=PlotterSettings().use_z_servo,
    )

    print(f"wrote {OUTPUT.relative_to(REPO_ROOT)}")
    print(
        f"  sheet    {width_mm:.0f} x {height_mm:.0f} mm  ({settings.sheet_width_mm:.0f}"
        f" x {settings.sheet_height_mm:.0f} bed minus {settings.direct_svg_origin_x_mm:.0f}"
        f"/{settings.direct_svg_origin_y_mm:.0f} origin)"
    )
    print(f"  bands    1: mix 0   2: mix 50   3: mix 100   4: {stats['motifs']} motifs (tick marks, left edge)")
    print(f"  geometry {len(polylines)} strokes, {stats['points']} points")
    print(
        f"  cost     {draw_mm / 1000:.1f} m drawn + {travel_mm / 1000:.1f} m travel, "
        f"~{xy_minutes + pen_minutes:.0f} min at current feeds"
    )
    print("\nPrint via the GUI: TESTS tab -> upload the SVG -> START SVG PRINT.")
    print("Then walk the inspection checklist in RUNBOOK.md ('Pattern bank paper test').")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
