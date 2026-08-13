"""The cards that used to be the WORK tab, split by what the operator is doing.

"Work" was never something anyone does. The tab held the run controls, a remote uploader, a
receipt printer, a queue readout and a log tail -- four unrelated subsystems sharing a name
that predicted none of them, which is why it read as a junk drawer.

The run half belongs on the screen you watch while the machine draws. The rest is diagnostics
you open when something is wrong, and it now sits behind an expansion in SETUP rather than
occupying a top-level tab. build() still renders both, so anything that wants the old whole
still gets it.
"""

from __future__ import annotations

from nicegui import ui

from ..context import GuiContext
from ..ui import danger_action_button, helper_text, log_viewer, mini_metric, primary_action_button, safe_action_button


def build_run(ctx: GuiContext) -> None:
    """Start/stop the run, and the two readouts that say whether it is going well."""
    with ui.card().classes("oracle-card compact-card w-full"):
        ui.label("System run").classes("text-sm font-bold")
        helper_text(
            "Start the supervised local services, reset the Firebase baseline for this run, "
            "or stop safely before the next sheet."
        )
        with ui.row().classes("gap-2"):
            primary_action_button("START SYSTEM", ctx.start_system)
            safe_action_button("NEW RUN", ctx.reset_baseline)
            danger_action_button("STOP SYSTEM", ctx.stop_system)

    with ui.card().classes("oracle-card compact-card w-full"):
        # SET WORK ZERO and its readiness line moved to the machine rail, next to the jog
        # controls used to reach the origin in the first place.
        ui.label("System check").classes("text-sm font-bold")
        ctx.system_check_label = ui.label("System check runs automatically when print starts.").classes(
            "text-xs text-[#8f4f2b]"
        )

    with ui.card().classes("oracle-card compact-card w-full"):
        ui.label("Queue").classes("text-sm font-bold")
        with ui.grid(columns=3).classes("w-full gap-1"):
            for key, label in (
                ("pending", "Pending"),
                ("active", "Active"),
                ("failed", "Fail/Skip"),
            ):
                ctx.queue_labels[key] = mini_metric(label)
        # Queue online/offline is the status bar's fact; the key survives invisibly for
        # the refresh writer and the workspace test.
        state_stub = ui.label("")
        state_stub.set_visibility(False)
        ctx.queue_labels["state"] = state_stub
        ctx.queue_labels["message"] = ui.label("-").classes("path-label text-[10px]")


def build_diagnostics(ctx: GuiContext) -> None:
    """The peripherals and the log tail: opened when something is wrong, not during a run."""
    fields = ctx.fields

    with ui.card().classes("oracle-card compact-card w-full"):
        ui.label("Mac mini uploader").classes("text-sm font-bold")
        with ui.row().classes("gap-2"):
            safe_action_button("START", ctx.start_macmini)
            ui.button("STOP", on_click=ctx.stop_macmini).props("dense color=warning")
            safe_action_button("SCAN", ctx.scan_macmini)
            safe_action_button("RESTART", ctx.restart_macmini)
        helper_text("Controlled through NEJE_MACMINI_AGENT_URL")

    with ui.card().classes("oracle-card compact-card w-full"):
        ui.label("Thermal printer").classes("text-sm font-bold")
        saved_printer = ctx.supervisor.runtime_store.load_json("thermal_printer", {"url": "http://10.28.8.56"})
        fields["thermal_printer_url"] = (
            ui.input("ESP32 URL", value=str(saved_printer.get("url") or "http://10.28.8.56"))
            .props("dense outlined")
            .classes("w-full")
        )
        fields["thermal_session_dir"] = (
            ui.input("Session folder", value=str(ctx.latest_receipt_session_dir() or ""))
            .props("dense outlined")
            .classes("w-full")
        )
        with ui.row().classes("gap-2 flex-wrap"):
            safe_action_button("STATUS", ctx.thermal_printer_status)
            safe_action_button("CONNECT", ctx.thermal_printer_connect)
            primary_action_button("PRINT LATEST", ctx.thermal_printer_print_latest)
            safe_action_button("PRINT SELECTED", ctx.thermal_printer_print_selected)
            safe_action_button("TEST RECEIPT", ctx.thermal_printer_test_receipt)
        ctx.thermal_printer_labels["message"] = ui.label(
            "Printer offline is a warning only; plotter and upload workflow continue."
        ).classes("path-label text-xs")

    with ui.card().classes("oracle-card compact-card w-full"):
        ui.label("Logs").classes("text-sm font-bold")
        fields["log_filter"] = (
            ui.select(
                {
                    "all": "all",
                    "errors": "errors",
                    "system": "system",
                    "plotter": "plotter",
                    "uploader": "uploader",
                    "checks": "checks",
                },
                value="all",
                label="Filter",
            )
            .props("dense outlined")
            .classes("w-full")
            .on_value_change(ctx.refresh_logs)
        )
        with ui.row().classes("gap-2"):
            safe_action_button("Refresh", ctx.refresh_logs)
            safe_action_button("Open logs", ctx.open_logs)
        ctx.logs_view = log_viewer([])


def build(ctx: GuiContext) -> None:
    """Both halves, for callers that still want the whole of the old tab."""
    with ui.column().classes("w-full gap-2"):
        build_run(ctx)
        build_diagnostics(ctx)
