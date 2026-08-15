"""Build the Z range calibration sheet for a mechanics/kinematics change.

Sweeps absolute pen-down depths (default 0 to -12 mm in 0.5 mm rungs) and pen-up
clearance heights, so the operator can read the new touch depth, full-ink depth and
the shallowest safe lift straight off the paper. See RUNBOOK section 9.

    uv run python scripts/build_z_range_cal.py [--stop -12] [--step 0.5]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from neje_oracle.blocks.gcode.pen_cal import generate_z_range_sheet  # noqa: E402
from neje_oracle.blocks.gui.support import load_gui_settings  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stop", type=float, default=-12.0, help="deepest rung in mm (default -12)")
    parser.add_argument("--step", type=float, default=0.5, help="rung spacing in mm (default 0.5)")
    args = parser.parse_args()

    settings = load_gui_settings()
    paths = generate_z_range_sheet(settings, depth_stop_mm=args.stop, depth_step_mm=args.step)
    gcode = paths["gcode"].read_text(encoding="utf-8")
    strokes = gcode.count("G0 X")
    print(f"wrote {paths['gcode']}")
    print(f"wrote {paths['manifest']}")
    print(f"{strokes} pen-downs; plot via SETUP -> VERIFY -> START SVG PRINT is not needed --")
    print("this is raw G-code: use the plotter daemon's spool, or stream the file directly.")
    print("Read the sheet: first rung that marks = touch depth; rung where the line stops")
    print("widening = full ink (your new Pen-down Z); shallowest clean clearance gap = Pen-up Z.")


if __name__ == "__main__":
    main()
