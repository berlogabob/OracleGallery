"""Compare the G-code time estimate with how long real prints took.

Pairs each finished print_svg in logs/operator_events.jsonl with the G-code file the
supervisor logged for it ("Uploaded SVG printed directly: NAME -> spool/....gcode", logged
within seconds of task_ok), then prints actual vs estimated minutes. Rerun after changing
the board's acceleration or the estimator: the ratio column should stay near 1.00 for
anything longer than a few minutes. Short jobs read a few seconds high on "actual" -- that
is the wait-for-Idle and G-code generation inside duration_s.

    uv run python scripts/check_estimate_history.py [--acceleration 100]
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

from neje_oracle.blocks.gcode.estimate import MachineLimits, estimate

MARKER = "Uploaded SVG printed directly: "


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--acceleration", type=float, default=MachineLimits().xy_acceleration_mm_s2)
    parser.add_argument("--logs", type=Path, default=Path("logs"))
    args = parser.parse_args()
    limits = MachineLimits(xy_acceleration_mm_s2=args.acceleration)

    finished: list[tuple[datetime, Path]] = []
    for line in (args.logs / "oracle_supervisor.log").read_text(encoding="utf-8").splitlines():
        if MARKER in line and " -> " in line:
            finished.append((datetime.fromisoformat(line.split("\t", 1)[0]), Path(line.rsplit(" -> ", 1)[1].strip())))

    print(f"{'gcode':38} {'lines':>6} {'actual':>7} {'estimate':>8} {'ratio':>6}")
    for raw in (args.logs / "operator_events.jsonl").read_text(encoding="utf-8").splitlines():
        event = json.loads(raw)
        if event.get("kind") != "task_ok" or event.get("task") != "print_svg" or not finished:
            continue
        at = datetime.fromisoformat(event["ts"])
        logged_at, path = min(finished, key=lambda pair: abs((pair[0] - at).total_seconds()))
        if abs((logged_at - at).total_seconds()) > 10 or not path.exists():
            continue
        gcode = path.read_text(encoding="utf-8")
        estimated = sum(estimate(gcode, limits)) / 60
        actual = float(event["duration_s"]) / 60
        ratio = actual / estimated if estimated else float("nan")
        print(f"{path.name:38} {len(gcode.splitlines()):6d} {actual:7.1f} {estimated:8.1f} {ratio:6.2f}")


if __name__ == "__main__":
    main()
