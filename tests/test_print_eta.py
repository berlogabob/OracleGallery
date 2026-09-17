"""Live "time left" while printing: a pure remaining-seconds helper, the status-text
suffix the GUI appends, and back-compat loading of PlotterRuntimeState rows saved before
eta_seconds/print_started_at existed.
"""

from __future__ import annotations

from neje_oracle.blocks.gui.context import _format_eta_suffix
from neje_oracle.blocks.plotter.daemon import gcode_stream_eta_seconds, remaining_seconds, sendable_line_indices
from neje_oracle.shared.models import PlotterRuntimeState, RuntimeStatus


def test_remaining_seconds_at_zero_sent_is_the_total() -> None:
    times = [1.0, 3.0, 6.0, 10.0]
    assert remaining_seconds(times, 0) == 10.0


def test_remaining_seconds_at_all_sent_is_zero() -> None:
    times = [1.0, 3.0, 6.0, 10.0]
    assert remaining_seconds(times, len(times)) == 0.0


def test_remaining_seconds_is_monotonic_non_increasing() -> None:
    times = [1.0, 3.0, 6.0, 10.0, 10.0, 15.0]
    values = [remaining_seconds(times, sent) for sent in range(len(times) + 1)]
    assert all(values[i] >= values[i + 1] for i in range(len(values) - 1))


def test_remaining_seconds_empty_times_is_zero() -> None:
    assert remaining_seconds([], 0) == 0.0


def test_remaining_seconds_clamps_out_of_range_counts() -> None:
    times = [1.0, 3.0, 6.0]
    # More "sent" than there are timed items (e.g. a dry run's unfiltered line count):
    # clamp to "done", never index past the end or go negative.
    assert remaining_seconds(times, 99) == 0.0
    assert remaining_seconds(times, -5) == 6.0


def test_sendable_line_indices_skips_blank_and_comment_lines() -> None:
    gcode = "; header\nG21\n\nG1 X10 ; inline comment stays sendable\n   \n; trailer\nG1 Y10\n"
    # Raw line indices: 0=";header" 1="G21" 2="" 3="G1 X10 ..." 4="   " 5="; trailer" 6="G1 Y10"
    assert sendable_line_indices(gcode) == [1, 3, 6]


def test_gcode_stream_eta_seconds_maps_sent_commands_to_raw_line_times() -> None:
    # Raw lines: 0 comment, 1 G21 (0s), 2 blank, 3 G1 X10 (2s), 4 G1 Y10 (5s more -> 7s total)
    gcode = "; header\nG21\nG1 X10\nG1 Y10\n"
    times = [0.0, 0.0, 2.0, 7.0]  # cumulative time at each raw line
    sent_indices = sendable_line_indices(gcode)  # [1, 2, 3]

    assert gcode_stream_eta_seconds(times, sent_indices, 0) == 7.0
    assert gcode_stream_eta_seconds(times, sent_indices, 2) == 5.0
    assert gcode_stream_eta_seconds(times, sent_indices, 3) == 0.0


def test_gcode_stream_eta_seconds_is_none_without_a_simulation() -> None:
    assert gcode_stream_eta_seconds([], [], 0) is None


def test_status_text_formats_minutes_left_when_printing_with_eta() -> None:
    suffix = _format_eta_suffix({"status": RuntimeStatus.PRINTING.value, "eta_seconds": 125.0})
    assert "~2 min left" in suffix
    assert "done ~" in suffix


def test_status_text_omits_eta_when_none() -> None:
    assert _format_eta_suffix({"status": RuntimeStatus.PRINTING.value, "eta_seconds": None}) == ""


def test_status_text_omits_eta_when_not_printing() -> None:
    # A stale estimate from the last job would otherwise be read as live.
    assert _format_eta_suffix({"status": RuntimeStatus.OPERATOR_PAUSED.value, "eta_seconds": 60.0}) == ""


def test_status_text_omits_eta_key_missing() -> None:
    assert _format_eta_suffix({"status": RuntimeStatus.PRINTING.value}) == ""


def test_runtime_state_loads_without_eta_keys() -> None:
    # A row saved before eta_seconds/print_started_at existed has neither key.
    payload = PlotterRuntimeState(status=RuntimeStatus.PRINTING, gcode_lines_sent=5, gcode_lines_total=10).to_dict()
    del payload["eta_seconds"]
    del payload["print_started_at"]

    state = PlotterRuntimeState.from_dict(payload)

    assert state.eta_seconds is None
    assert state.print_started_at == ""
    assert state.gcode_lines_sent == 5
    assert state.gcode_lines_total == 10


def test_runtime_state_round_trips_eta_fields() -> None:
    original = PlotterRuntimeState(
        status=RuntimeStatus.PRINTING, eta_seconds=42.5, print_started_at="2026-09-17T00:00:00+00:00"
    )

    restored = PlotterRuntimeState.from_dict(original.to_dict())

    assert restored.eta_seconds == 42.5
    assert restored.print_started_at == "2026-09-17T00:00:00+00:00"
