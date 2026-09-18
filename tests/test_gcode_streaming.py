"""Streaming a G-code file the machine can already run.

pen_cal writes its ladders as G-code, not SVG, because an SVG cannot carry a per-stroke feed
or Z -- which left the calibration sheets unprintable from the app, since the only print path
took SVG. print_gcode_file is the missing half, and it shares every step that matters (the
preflight, the runtime state a screen reads, the planner-simulated ETA, the plot_jobs row)
with the SVG print rather than growing a second, laxer path.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from test_supervisor import BusyTransport, DryTransport, EmptyRemote, _plotter_settings, _supervisor

from neje_oracle.app.supervisor import SupervisorService
from neje_oracle.shared.config import OracleSupervisorSettings
from neje_oracle.shared.gui_settings import GuiSettings
from neje_oracle.shared.models import ComponentStatus, PlotterReadinessState, RuntimeStatus, SystemMode
from neje_oracle.shared.store import PlotterStore

_SHEET = "\n".join(
    [
        "; pen cal",
        "G21",
        "G90",
        "G0 F5000.00",
        "G1 F1800.00",
        "G0 Z0.000",
        "G0 X10.000 Y10.000",
        "G1 Z-25.000 F10000.00",
        "G1 X90.000 Y10.000",
        "G0 Z0.000",
        "G0 X0 Y0",
    ]
)


def _settings() -> GuiSettings:
    return GuiSettings(system_mode=SystemMode.TEST.value, sheet_width_mm=200, sheet_height_mm=120, cell_diameter_mm=80)


def _ready_supervisor(tmp_path: Path) -> tuple[SupervisorService, DryTransport]:
    plotter_settings = _plotter_settings(tmp_path)
    transport = DryTransport(plotter_settings)
    supervisor = SupervisorService(
        settings=OracleSupervisorSettings(runtime_db_path=tmp_path / "oracle.sqlite3"),
        plotter_settings=plotter_settings,
        remote_factory=lambda: EmptyRemote(),  # type: ignore[arg-type]
        transport_factory=lambda resolved: transport,  # type: ignore[arg-type]
    )
    supervisor.runtime_store.save_plotter_readiness(
        PlotterReadinessState(work_zero_set=True, plotter_ready=True, message="ready")
    )
    return supervisor, transport


def _sheet_file(tmp_path: Path, text: str = _SHEET) -> Path:
    path = tmp_path / "pen_cal_gel.gcode"
    path.write_text(text + "\n", encoding="utf-8")
    return path


def test_every_line_of_the_file_reaches_the_machine(tmp_path: Path) -> None:
    """The file is sent as written. A calibration ladder means nothing if a line is dropped:
    each row carries its own feed or Z, so a missing line silently mislabels every row below it."""
    supervisor, transport = _ready_supervisor(tmp_path)

    state = supervisor.print_gcode_file(_sheet_file(tmp_path), label="pen cal gel", gui_settings=_settings())

    assert state.status == ComponentStatus.STOPPED
    sent = (transport.settings.spool_root / "pen_cal_gel.gcode").read_text(encoding="utf-8")
    assert sent.splitlines() == _SHEET.splitlines()


def test_a_sheet_reports_progress_and_a_shrinking_estimate(tmp_path: Path) -> None:
    supervisor, transport = _ready_supervisor(tmp_path)
    seen: list[float | None] = []
    started: list[str] = []
    real_send = transport.send

    def send(*, gcode: str, sheet_id: str, dry_run=None, progress_callback=None, should_stop=None):  # type: ignore[no-untyped-def]
        def spy(sent: int, total: int) -> None:
            if progress_callback:
                progress_callback(sent, total)
            live = PlotterStore(supervisor.plotter_settings.db_path).load_runtime_state()
            seen.append(live.eta_seconds)
            started.append(live.print_started_at)

        total_lines = len([line for line in gcode.splitlines() if line.strip() and not line.startswith(";")])
        for index in range(1, total_lines + 1):
            spy(index, total_lines)
        return real_send(gcode=gcode, sheet_id=sheet_id, dry_run=dry_run, should_stop=should_stop)

    transport.send = send  # type: ignore[method-assign]

    supervisor.print_gcode_file(_sheet_file(tmp_path), label="pen cal gel", gui_settings=_settings())

    assert seen and all(value is not None for value in seen)
    assert seen[-1] <= seen[0], "the estimate must fall as lines are acknowledged"
    # Stamped while streaming, not on the finished state: that one is written fresh so a
    # stale estimate from the last job cannot read as live once the sheet is done.
    assert all(started)
    assert (
        PlotterStore(supervisor.plotter_settings.db_path).load_runtime_state().status == RuntimeStatus.OPERATOR_PAUSED
    )


def test_a_failing_transport_lands_as_an_error_state(tmp_path: Path) -> None:
    supervisor, transport = _ready_supervisor(tmp_path)

    def explode(**_: object) -> None:
        raise RuntimeError("controller dropped the connection")

    transport.send = explode  # type: ignore[method-assign]

    state = supervisor.print_gcode_file(_sheet_file(tmp_path), label="pen cal gel", gui_settings=_settings())

    assert state.status == ComponentStatus.ERROR
    assert "controller dropped the connection" in state.last_error
    store = PlotterStore(supervisor.plotter_settings.db_path)
    assert store.load_runtime_state().status == RuntimeStatus.ERROR


def test_a_missing_file_is_a_state_not_a_traceback(tmp_path: Path) -> None:
    """Ordinary outcome: the sheet is generated first, and generation can fail or be pruned."""
    supervisor, _ = _ready_supervisor(tmp_path)

    state = supervisor.print_gcode_file(tmp_path / "nope.gcode", label="missing", gui_settings=_settings())

    assert state.status == ComponentStatus.ERROR
    assert "nope.gcode" in state.message


def test_a_sheet_waits_for_idle_like_every_other_print(tmp_path: Path) -> None:
    """A ladder drives the pen over the paper exactly as a drawing does, so it earns the
    same refusal rather than a quieter path around it."""
    supervisor = _supervisor(tmp_path, transport_cls=BusyTransport)
    supervisor.runtime_store.save_plotter_readiness(
        PlotterReadinessState(work_zero_set=True, plotter_ready=True, message="ready")
    )

    state = supervisor.print_gcode_file(_sheet_file(tmp_path), label="pen cal gel", gui_settings=_settings())

    assert state.status == ComponentStatus.WARNING
    assert "Idle" in state.message


def test_the_svg_print_still_goes_out_through_the_same_seam(tmp_path: Path) -> None:
    """Regression guard for the extraction: print_uploaded_svg keeps its own behaviour."""
    supervisor, transport = _ready_supervisor(tmp_path)
    svg = (
        "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'>"
        "<path d='M10,10 L90,90' stroke='black' fill='none'/>"
        "</svg>"
    )

    state = supervisor.print_uploaded_svg(_settings(), svg_bytes=svg.encode("utf-8"), original_name="label-test.svg")

    assert state.status == ComponentStatus.STOPPED
    written = list(transport.settings.spool_root.glob("testsvg_*.gcode"))
    assert len(written) == 1
    assert "direct SVG LABEL TEST" in written[0].read_text(encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
