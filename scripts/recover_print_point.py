"""Work out where a hard-stopped print really stopped, lift the pen, and record it.

scripts/resume_print.py records its own stopping point when asked to pause. This is for the
other case: the streamer died without being asked -- a laptop sleep, a crash, a kill -- and
nothing wrote the line down. It happened on 2026-09-17, when an idle sleep ended a 5 h sheet
at 43% with "Timed out waiting for ok".

The recovery works because the sender acks one line at a time, so the board was holding at
most the line it had already received: its reported position is the endpoint of the last
line it executed. Matching that position against the file pins the resume line exactly,
where the saved progress state is only accurate to its 200-line write interval -- and a
200-line replay means a couple of strokes drawn twice, in ink.

    uv run python scripts/recover_print_point.py spool/<sheet>.gcode 59348 --out logs/point.json

The line argument is where the stream began (1 for a first run, or the resume line of the
run that died), so the search window starts from the progress the store recorded.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from neje_oracle.app.supervisor import SupervisorService
from neje_oracle.blocks.fluidnc.transport import _should_send_line
from neje_oracle.shared.store import PlotterStore

# The board reports its position quantized to its step resolution (40 steps/mm on X and Y),
# so a file coordinate and the position it lands on differ by up to half a step. A tolerance
# tighter than that matches nothing; much looser starts matching a neighbouring line.
_STEP_TOLERANCE_MM = 0.013
# How far past the store's last write to look. It saves every 200 lines, so the true line is
# somewhere in the next 200; the rest is slack for a store write that never landed.
_SEARCH_AHEAD = 400


def _endpoints(commands: list[str]) -> list[tuple[float | None, float | None]]:
    """Where the head stands after each command, carrying X and Y forward across Z-only moves."""
    x: float | None = None
    y: float | None = None
    out = []
    for command in commands:
        for word in command.split():
            if word.startswith("X"):
                x = float(word[1:])
            elif word.startswith("Y"):
                y = float(word[1:])
        out.append((x, y))
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("source", type=Path, help="the G-code file that was streaming")
    parser.add_argument("started_at_line", type=int, help="sendable line the dead run began at (1 for a first run)")
    parser.add_argument("--out", type=Path, default=Path("logs/resume_point.json"))
    parser.add_argument("--no-pen-up", action="store_true", help="leave Z alone (it is already up)")
    args = parser.parse_args()

    supervisor = SupervisorService()
    probe = supervisor.probe_fluidnc(scan=False)
    if not probe.online:
        print(f"FluidNC is unreachable, so there is no position to match: {probe.message}")
        return 1
    if not probe.controller.is_idle:
        print(f"FluidNC is {probe.controller.state.value}; stop the print before recovering its point")
        return 1
    position = probe.controller.machine_position
    x, y = float(position[0]), float(position[1])
    print(f"board: {probe.message}")

    commands = [
        line.strip() for line in args.source.read_text(encoding="utf-8").splitlines() if _should_send_line(line)
    ]
    body_start = max(0, args.started_at_line - 1)
    sent = int(PlotterStore(supervisor.plotter_settings.db_path).load_runtime_state().gcode_lines_sent)
    window_start = max(body_start, body_start + sent - 5)
    window_end = min(len(commands), window_start + _SEARCH_AHEAD)
    ends = _endpoints(commands)

    matches = [
        index
        for index in range(window_start, window_end)
        if ends[index][0] is not None
        and abs(ends[index][0] - x) < _STEP_TOLERANCE_MM
        and abs(ends[index][1] - y) < _STEP_TOLERANCE_MM
    ]
    if not matches:
        print(f"no line between {window_start + 1} and {window_end} ends at X{x} Y{y}; widen the window or re-home")
        return 1
    # The last match: a path can cross its own endpoint, and everything after the true stop
    # has not run, so the furthest candidate the machine could be standing on is the one.
    stopped_after = matches[-1] + 1
    resume_at = stopped_after + 1

    pen_down = None
    for command in commands[:stopped_after]:
        if command.startswith("G1 Z"):
            pen_down = True
        elif command.startswith("G0 Z"):
            pen_down = False

    if not args.no_pen_up:
        transport = supervisor.transport_factory(supervisor.plotter_settings)
        print("pen up:", transport.send_commands(["G21", "G90", "G0 Z0.000"]).message)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(
            {
                "source": str(args.source),
                "resume_at_sendable_line": resume_at,
                "next_command": commands[resume_at - 1] if resume_at <= len(commands) else "",
                "stopped_after_command": commands[stopped_after - 1],
                "pen_was_down": bool(pen_down),
                "stopped_at_machine_position": [x, y],
                "stopped_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"resume at sendable line {resume_at} of {len(commands)} -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
