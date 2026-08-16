"""HEART numbers from the operator event log.

Reads logs/operator_events.jsonl (written by shared/telemetry.py via the GUI's
instrumented handlers) and prints, per session: task counts, success rate, median
durations, error rate, and screen switches. These are the Task-success and
Engagement rows of the audit's HEART scorecard, from real operator sessions.

    uv run python scripts/operator_report.py [path-to-events.jsonl]
"""

from __future__ import annotations

import json
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

from neje_oracle.shared.config import OracleSupervisorSettings
from neje_oracle.shared.telemetry import EVENTS_FILENAME


def main() -> None:
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else OracleSupervisorSettings().logs_root / EVENTS_FILENAME
    if not path.exists():
        sys.exit(f"no event log at {path} -- run the GUI first")

    sessions: dict[str, list[dict]] = defaultdict(list)
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            event = json.loads(line)
            sessions[event["session"]].append(event)

    for session, events in sessions.items():
        ok = [e for e in events if e["kind"] == "task_ok"]
        fail = [e for e in events if e["kind"] == "task_fail"]
        switches = sum(1 for e in events if e["kind"] == "screen_switch")
        total = len(ok) + len(fail)
        durations = [e["duration_s"] for e in ok + fail if "duration_s" in e]
        print(f"\nsession {session}  ({events[0]['ts']} .. {events[-1]['ts']})")
        print(f"  tasks: {total}  ok: {len(ok)}  fail: {len(fail)}", end="")
        print(f"  success rate: {len(ok) / total:.0%}" if total else "  success rate: n/a")
        if durations:
            print(f"  median task duration: {statistics.median(durations):.2f}s")
        print(f"  screen switches: {switches}")
        by_task = Counter(e["task"] for e in ok + fail)
        for task, count in by_task.most_common():
            failures = sum(1 for e in fail if e["task"] == task)
            print(f"    {task:24} x{count}" + (f"  ({failures} failed)" if failures else ""))


if __name__ == "__main__":
    main()
