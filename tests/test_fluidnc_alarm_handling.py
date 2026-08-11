"""Guards for the gaps between what the software believed and what the machine did.

Every string asserted here was taken from logs/oracle_supervisor.log or the 2026-08-10
panic transcript -- not invented. See planning/GRAPH_DEBT_TRACKER.md.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from neje_oracle.app.supervisor import FLUIDNC_ERROR_HELP, _enrich_fluidnc_error
from neje_oracle.blocks.fluidnc.transport import is_failure_response
from neje_oracle.shared.models import (
    FluidNCCommandResult,
    FluidNCState,
    PlotStatus,
    PlotterRuntimeConfig,
)
from neje_oracle.shared.store import PlotterStore

# --- the response classifier ---------------------------------------------------


def test_msg_err_is_a_failure_not_chatter() -> None:
    """The bug that made the software believe the pen was up when it was not.

    FluidNC answers a command it will not run while in Alarm with this line and *then*
    sends `ok`. Matching only `error`/`alarm` let the trailing `ok` win, and
    logs/oracle_supervisor.log:736 recorded `Z up servo G0 Z0.000: [MSG:ERR: Reset to
    continue]` at INFO -- a pen-up reported as done while the nib stayed on the paper.
    """
    assert is_failure_response("[MSG:ERR: Reset to continue]")


def test_classifier_still_catches_what_it_always_did() -> None:
    # Exact strings from the log.
    assert is_failure_response("error:9")
    assert is_failure_response("error:152")
    assert is_failure_response("[MSG:INFO: ALARM: Soft Limit]")
    assert is_failure_response("ALARM:2")


def test_normal_traffic_is_not_a_failure() -> None:
    for line in ("ok", "[MSG:Homed:XY]", "[MSG:INFO: Caution: Unlocked]", "<Idle|MPos:0.000,0.000,0.000>"):
        assert not is_failure_response(line), line


def test_ss_panic_banner_is_an_accepted_false_positive() -> None:
    """`$SS` reports this informationally, and it classifies as a failure.

    Documented rather than special-cased: no code path sends `$SS`, and narrowing the
    match to exclude it would risk letting a real `[MSG:ERR:` through.
    """
    assert is_failure_response("[MSG:ERR: Showing startup log from previous panic]")


# --- the error code table ------------------------------------------------------


@pytest.mark.parametrize(
    "raw",
    [
        "error:5",
        "error:9",
        "error:19",
        "error:152",
        "error:162",
        "ALARM:2",
        "[MSG:INFO: ALARM: Soft Limit]",
        "[MSG:INFO: ALARM: Homing Fail Approach]",
        "[MSG:INFO: ALARM: Abort Cycle]",
        "[MSG:ERR: Reset to continue]",
    ],
)
def test_every_observed_code_gets_plain_english(raw: str) -> None:
    """Each of these fired on this machine. None should reach the operator raw."""
    enriched = _enrich_fluidnc_error(FluidNCCommandResult(ok=False, command="x", response_lines=[raw], error=raw))
    assert enriched.message != raw, f"{raw} is still a bare GRBL string"
    assert len(enriched.message) > len(raw)


def test_enrichment_is_idempotent() -> None:
    """home_fluidnc enriches, then _record_fluidnc_command enriches the same result again."""
    once = _enrich_fluidnc_error(
        FluidNCCommandResult(ok=False, command="$H", response_lines=["error:5"], error="error:5")
    )
    twice = _enrich_fluidnc_error(once)
    assert twice.message == once.message


def test_unknown_code_is_left_alone() -> None:
    result = FluidNCCommandResult(ok=False, command="x", response_lines=["error:77"], error="error:77")
    assert _enrich_fluidnc_error(result).message == "error:77"


def test_help_table_is_ordered_longest_key_first() -> None:
    """`error:15` must not shadow `error:152`."""
    codes = [code for code, _ in FLUIDNC_ERROR_HELP]
    for index, code in enumerate(codes):
        for later in codes[index + 1 :]:
            assert not later.startswith(code), f"{code} shadows {later}; put the longer key first"


# --- controller states ---------------------------------------------------------


def test_home_and_check_are_real_states() -> None:
    """probe.ok requires state != UNKNOWN, so a probe landing mid-$H read as offline."""
    assert FluidNCState("Home") is FluidNCState.HOME
    assert FluidNCState("Check") is FluidNCState.CHECK


def test_home_does_not_collide_with_hold() -> None:
    """_parse_state prefix-matches, so a new value that prefixes an old one would break it."""
    values = [state.value for state in FluidNCState]
    for value in values:
        others = [other for other in values if other != value and other.startswith(value)]
        assert not others, f"{value} is a prefix of {others}"


# --- abort recovery ------------------------------------------------------------


@dataclass
class _FakeTransport:
    """Records what the abort path sent. `send_commands` result is configurable."""

    pen_up_ok: bool = True
    pen_up_message: str = "ok"
    soft_reset_raises: bool = False
    calls: list[str] | None = None

    def __post_init__(self) -> None:
        self.calls = []

    def soft_reset(self) -> FluidNCCommandResult:
        assert self.calls is not None
        self.calls.append("soft_reset")
        if self.soft_reset_raises:
            raise OSError("connection closed")
        return FluidNCCommandResult(ok=True, command="0x18", response_lines=["ok"])

    def send_commands(self, commands: list[str], **_: Any) -> FluidNCCommandResult:
        assert self.calls is not None
        self.calls.append(" ".join(commands))
        if self.pen_up_ok:
            return FluidNCCommandResult(ok=True, command=commands[-1], response_lines=["ok"])
        return FluidNCCommandResult(
            ok=False, command=commands[-1], response_lines=[self.pen_up_message], error=self.pen_up_message
        )


def _daemon_with(transport: _FakeTransport) -> Any:
    from neje_oracle.blocks.plotter.daemon import PlotterDaemon

    daemon = PlotterDaemon.__new__(PlotterDaemon)  # no DB/spool setup needed for this helper
    daemon.transport = transport
    return daemon


def test_abort_stops_the_machine_then_lifts_the_pen() -> None:
    """Order matters: the soft reset is what flushes the planner and stops the motion.

    transport.send() closes its socket on the way out while FluidNC still holds queued
    moves, so without this the machine kept drawing after the abort.
    """
    transport = _FakeTransport()
    message = _daemon_with(transport)._abort_recovery(PlotterRuntimeConfig(z_up_mm=0.0), "boom")

    assert transport.calls is not None
    assert transport.calls[0] == "soft_reset"
    assert "G0 Z0.000" in transport.calls[1]
    assert "boom" in message
    assert "pen lifted" in message


def test_abort_warns_when_the_pen_lift_is_refused() -> None:
    """After a soft reset the controller is in Alarm and refuses the Z move.

    Not worked around -- unlocking would clear the alarm and discard the position
    reference. The operator has to be told the nib may still be down.
    """
    transport = _FakeTransport(pen_up_ok=False, pen_up_message="[MSG:ERR: Reset to continue]")
    message = _daemon_with(transport)._abort_recovery(PlotterRuntimeConfig(), "boom")

    assert "pen may still be down" in message
    assert "boom" in message


def test_abort_never_raises_out_of_the_handler() -> None:
    """It runs inside an `except` block; raising there would mask the original failure."""
    transport = _FakeTransport(soft_reset_raises=True)
    message = _daemon_with(transport)._abort_recovery(PlotterRuntimeConfig(), "boom")

    assert "pen may still be down" in message
    assert "boom" in message


def test_abort_never_unlocks_or_homes() -> None:
    """$X clears the alarm and silently discards the position reference."""
    transport = _FakeTransport()
    _daemon_with(transport)._abort_recovery(PlotterRuntimeConfig(), "boom")

    assert transport.calls is not None
    sent = " ".join(transport.calls)
    assert "$X" not in sent
    assert "$H" not in sent


# --- durable failure history ---------------------------------------------------


def test_a_recorded_failure_survives_a_later_status_write(tmp_path: Any) -> None:
    """Callers default error="" when reporting progress, which used to wipe the reason.

    Every row in the real plotter.sqlite3 has an empty error column because of this --
    including the sheet the 2026-08-10 panic killed at cell 15/16.
    """
    store = PlotterStore(tmp_path / "plotter.sqlite3")
    store.record_job_status("s1", PlotStatus.FAILED, sheet_id="sheet_1", error="ALARM: Soft Limit")
    store.record_job_status("s1", PlotStatus.PLOTTING, sheet_id="sheet_1")

    row = store._fetchone("SELECT status, error FROM plot_jobs WHERE session_id = ?", ("s1",))
    assert row is not None
    assert row["status"] == PlotStatus.PLOTTING.value
    assert row["error"] == "ALARM: Soft Limit"


def test_a_new_error_still_replaces_the_old_one(tmp_path: Any) -> None:
    store = PlotterStore(tmp_path / "plotter.sqlite3")
    store.record_job_status("s1", PlotStatus.FAILED, sheet_id="sheet_1", error="first")
    store.record_job_status("s1", PlotStatus.FAILED, sheet_id="sheet_1", error="second")

    row = store._fetchone("SELECT error FROM plot_jobs WHERE session_id = ?", ("s1",))
    assert row is not None
    assert row["error"] == "second"
