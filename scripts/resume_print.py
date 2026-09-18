"""Resume an interrupted sheet from where the machine actually stopped, and pause on demand.

A sheet here runs for hours, and the streamer is a laptop: on 2026-09-17 an idle sleep killed
a 5 h plot at 43%, and the next evening the operator wanted the rest finished the following
morning. Restarting from the top would have drawn the first half twice.

    uv run python scripts/resume_print.py logs/sheet_resume_point.json   # continue
    touch logs/STOP_RESUME                                               # pause at a line boundary

The sender acks one line at a time, so a stop always lands between lines: the exact line
reached is written back into the resume-point file, the pen is lifted, and the next run
starts there. Machine coordinates equal work coordinates on this setup (the G54 offset is
zero), so nothing needs re-zeroing while the board keeps its homing -- after a power cycle,
run $H first and the numbers line up again.

The resume-point file is what scripts/recover_print_point.py writes after a hard stop, and
what this script rewrites on every pause:

    {"source": "spool/<sheet>.gcode", "resume_at_sendable_line": 67746,
     "pen_was_down": true, "stopped_at_machine_position": [125.825, 141.5]}
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from neje_oracle.app.supervisor import SupervisorService
from neje_oracle.blocks.fluidnc.transport import PrintStopRequested, _should_send_line
from neje_oracle.blocks.gcode.estimate import line_times
from neje_oracle.shared.gui_settings import GuiSettings
from neje_oracle.shared.models import PlotterRuntimeState, RuntimeStatus
from neje_oracle.shared.store import PlotterStore


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("point", type=Path, help="resume-point JSON")
    parser.add_argument("--stop-file", type=Path, default=Path("logs/STOP_RESUME"))
    parser.add_argument("--label", default="", help="name for the runtime status line")
    args = parser.parse_args()

    point = json.loads(args.point.read_text(encoding="utf-8"))
    source = Path(point["source"])
    resume_at = int(point["resume_at_sendable_line"])  # 1-based sendable line, not yet executed
    label = args.label or source.stem

    settings = GuiSettings()
    commands = [line.strip() for line in source.read_text(encoding="utf-8").splitlines() if _should_send_line(line)]
    body = commands[resume_at - 1 :]
    if not body:
        print(f"{source.name} is already finished at line {resume_at}")
        return 0

    # Modal state the board no longer has: units, absolute, both feeds, and the pen. Stopped
    # mid-stroke the pen was lifted, so it travels back and lands before drawing on.
    header = [
        "G21",
        "G90",
        f"G0 F{settings.travel_rate:.2f}",
        f"G1 F{settings.draw_rate:.2f}",
        f"G0 Z{settings.z_up_mm:.3f}",
    ]
    if point.get("pen_was_down"):
        x, y = point["stopped_at_machine_position"]
        header += [f"G0 X{x:.3f} Y{y:.3f}", f"G1 Z{settings.z_down_mm:.3f} F{settings.z_feed_mm_min:.2f}"]
    gcode = f"; resume of {source.name} from sendable line {resume_at}\n" + "\n".join(header + body) + "\n"
    times = line_times(gcode)
    print(f"{len(body)} lines left, ~{times[-1] / 60:.0f} min", flush=True)

    supervisor = SupervisorService()
    store = PlotterStore(supervisor.plotter_settings.db_path)
    sheet_id = f"{source.stem}_resume"
    acked = {"lines": 0}
    args.stop_file.parent.mkdir(parents=True, exist_ok=True)
    args.stop_file.unlink(missing_ok=True)

    def progress(sent: int, total: int) -> None:
        acked["lines"] = sent
        left = times[-1] - times[min(sent, len(times) - 1)]
        # Every 200 lines, not every line: the store write is the only per-line cost here,
        # and the screen reading it refreshes far slower than the machine acks.
        if sent % 200 == 0 or sent == total:
            store.save_runtime_state(
                PlotterRuntimeState(
                    status=RuntimeStatus.PRINTING,
                    message=f"{label}: {sent}/{total} lines, ~{left / 60:.0f} min left",
                    current_sheet_id=sheet_id,
                    gcode_lines_sent=sent,
                    gcode_lines_total=total,
                    gcode_progress_percent=sent / total * 100,
                    eta_seconds=left,
                )
            )
        if sent % 2000 == 0 or sent == total:
            print(f"{time.strftime('%H:%M:%S')} {sent}/{total} ~{left / 60:.0f} min left", flush=True)

    def save_point(next_line: int, pen_down: bool, position: list[float] | None) -> None:
        point.update(
            resume_at_sendable_line=next_line,
            next_command=commands[next_line - 1] if next_line <= len(commands) else "",
            pen_was_down=pen_down,
            stopped_at_machine_position=position or point["stopped_at_machine_position"],
            stopped_at=time.strftime("%Y-%m-%dT%H:%M:%S"),
        )
        args.point.write_text(json.dumps(point, indent=2) + "\n", encoding="utf-8")

    try:
        supervisor.transport_factory(supervisor.plotter_settings).send(
            gcode=gcode,
            sheet_id=sheet_id,
            dry_run=False,
            progress_callback=progress,
            should_stop=args.stop_file.exists,
        )
    except PrintStopRequested:
        executed = max(0, acked["lines"] - len(header))  # header lines are not part of the sheet
        next_line = resume_at + executed
        pen_down = None
        for command in commands[: next_line - 1]:
            if command.startswith("G1 Z"):
                pen_down = True
            elif command.startswith("G0 Z"):
                pen_down = False
        transport = supervisor.transport_factory(supervisor.plotter_settings)
        probe = transport.probe()
        print("pen up:", transport.send_commands(["G21", "G90", f"G0 Z{settings.z_up_mm:.3f}"]).message, flush=True)
        save_point(next_line, bool(pen_down), list(probe.controller.machine_position[:2]))
        store.save_runtime_state(
            PlotterRuntimeState(
                status=RuntimeStatus.OPERATOR_PAUSED,
                message=f"{label} paused at line {next_line} of {len(commands)}",
                current_sheet_id=sheet_id,
                gcode_lines_sent=next_line,
                gcode_lines_total=len(commands),
                gcode_progress_percent=next_line / len(commands) * 100,
            )
        )
        args.stop_file.unlink(missing_ok=True)
        print("paused at sendable line", next_line, flush=True)
        return 0

    save_point(len(commands) + 1, False, None)
    store.save_runtime_state(
        PlotterRuntimeState(
            status=RuntimeStatus.OPERATOR_PAUSED,
            message=f"{label} finished",
            current_sheet_id=sheet_id,
            gcode_lines_sent=len(commands),
            gcode_lines_total=len(commands),
            gcode_progress_percent=100.0,
        )
    )
    print("DONE", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
