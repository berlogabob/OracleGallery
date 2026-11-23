"""Print the rest of a sheet the operator stopped: skip the rows already on the paper.

The daemon always starts a sheet at row 1, so START PRINT after a stop draws over the top
of the page. This runs one sheet with the same layout, beginning after the finished rows.
Finish a half-drawn row first with scripts/resume_print.py.

    uv run python scripts/continue_sheet.py 5      # rows 1-5 are done, print 6 onward

STOP PRINT in the GUI still stops it, between lines.
"""

from __future__ import annotations

import argparse

from neje_oracle.app.supervisor import SupervisorService
from neje_oracle.blocks.plotter.daemon import PlotterDaemon
from neje_oracle.shared.models import PlotterControlState
from neje_oracle.shared.store import PlotterStore


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("rows_done", type=int, help="rows already fully drawn")
    args = parser.parse_args()

    supervisor = SupervisorService()
    probe = supervisor.probe_fluidnc(scan=False)
    if not probe.online or not probe.controller.is_idle:
        print(f"FluidNC is not ready: {probe.message}")
        return 1
    store = supervisor.runtime_store
    config = store.load_plotter_config()
    daemon = PlotterDaemon(
        supervisor.plotter_settings,
        PlotterStore(supervisor.plotter_settings.db_path),
        supervisor._create_plotter_remote(config),
        supervisor.transport_factory(supervisor.plotter_settings),
        oracle_store=store,
    )
    daemon.skip_rows_once = args.rows_done
    store.save_print_control(
        PlotterControlState(print_enabled=True, operator_paused=False, run_mode=config.run_mode, dry_run=False)
    )
    try:
        daemon.run_cycle()
    finally:
        store.save_print_control(
            PlotterControlState(print_enabled=False, operator_paused=True, run_mode=config.run_mode, dry_run=False)
        )
    state = daemon.get_state()
    print(f"{state.status.value}: {state.message}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
