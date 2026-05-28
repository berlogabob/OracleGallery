"""Work workspace for the Oracle GUI."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from nicegui import ui

from ..ui import danger_action_button, log_viewer, safe_action_button
from ....app.supervisor import SupervisorService


def build_work_workspace(
    supervisor: SupervisorService,
    fields: dict[str, Any],
    ready_labels: dict[str, Any],
    thermal_printer_labels: dict[str, Any],
    *,
    start_system: Callable[..., Any],
    reset_baseline: Callable[..., Any],
    stop_system: Callable[..., Any],
    start_macmini: Callable[..., Any],
    stop_macmini: Callable[..., Any],
    scan_macmini: Callable[..., Any],
    restart_macmini: Callable[..., Any],
    latest_receipt_session_dir: Callable[[], Path | None],
    thermal_printer_status: Callable[..., Any],
    thermal_printer_connect: Callable[..., Any],
    thermal_printer_print_latest: Callable[..., Any],
    thermal_printer_print_selected: Callable[..., Any],
    thermal_printer_test_receipt: Callable[..., Any],
    set_work_zero: Callable[..., Any],
) -> Any:
    """Build the production operations controls.

    Returns the system-check label that print callbacks refresh.
    """
    with ui.column().classes("workspace-scroll gap-2"):
        with ui.card().classes("oracle-card compact-card w-full"):
            ui.label("System run").classes("text-sm font-bold")
            ui.label("Start the supervised local services, reset the Firebase baseline for this run, or stop safely before the next sheet.").classes("text-xs text-[#8f4f2b]")
            with ui.row().classes("gap-2"):
                ui.button("START SYSTEM", on_click=start_system).props("dense color=positive")
                safe_action_button("NEW RUN", reset_baseline)
                danger_action_button("STOP SYSTEM", stop_system)

        with ui.card().classes("oracle-card compact-card w-full"):
            ui.label("Mac mini uploader").classes("text-sm font-bold")
            with ui.row().classes("gap-2"):
                ui.button("START", on_click=start_macmini).props("dense")
                ui.button("STOP", on_click=stop_macmini).props("dense color=warning")
                ui.button("SCAN", on_click=scan_macmini).props("dense flat")
                ui.button("RESTART", on_click=restart_macmini).props("dense")
            ui.label("Controlled through NEJE_MACMINI_AGENT_URL").classes("text-xs text-[#8f4f2b]")

        with ui.card().classes("oracle-card compact-card w-full"):
            ui.label("Thermal printer").classes("text-sm font-bold")
            saved_printer = supervisor.runtime_store.load_json("thermal_printer", {"url": "http://10.28.8.56"})
            fields["thermal_printer_url"] = ui.input(
                "ESP32 URL",
                value=str(saved_printer.get("url") or "http://10.28.8.56"),
            ).props("dense outlined").classes("w-full")
            fields["thermal_session_dir"] = ui.input(
                "Session folder",
                value=str(latest_receipt_session_dir() or ""),
            ).props("dense outlined").classes("w-full")
            with ui.row().classes("gap-2 flex-wrap"):
                ui.button("STATUS", on_click=thermal_printer_status).props("dense")
                ui.button("CONNECT", on_click=thermal_printer_connect).props("dense")
                ui.button("PRINT LATEST", on_click=thermal_printer_print_latest).props("dense color=positive")
                ui.button("PRINT SELECTED", on_click=thermal_printer_print_selected).props("dense")
                ui.button("TEST RECEIPT", on_click=thermal_printer_test_receipt).props("dense flat")
            thermal_printer_labels["message"] = ui.label("Printer offline is a warning only; plotter and upload workflow continue.").classes("path-label text-xs")

        with ui.card().classes("oracle-card compact-card w-full"):
            ui.label("Work zero").classes("text-sm font-bold")
            ui.label("Before Set Zero: fix paper, jog to upper-left work origin, lower Z manually, set pen pressure/contact, then confirm. Software cannot verify pen pressure.").classes("text-xs text-[#8f4f2b]")
            with ui.row().classes("gap-2"):
                ui.button("SET WORK ZERO", on_click=set_work_zero).props("dense color=warning")
            with ui.grid(columns=1).classes("w-full gap-1"):
                with ui.element("div").classes("mini-metric"):
                    ui.label("Zero").classes("label")
                    ready_labels["zero"] = ui.label("-").classes("value")
            ready_labels["message"] = ui.label("-").classes("path-label text-xs")
            ui.separator()
            return ui.label("System check runs automatically when print starts.").classes("text-xs text-[#8f4f2b]")


def build_work_status_workspace(
    queue_labels: dict[str, Any],
    fields: dict[str, Any],
    *,
    refresh_logs: Callable[..., Any],
    open_logs: Callable[..., Any],
) -> Any:
    """Build queue and log controls for the right column."""
    with ui.column().classes("workspace-scroll gap-2"):
        with ui.card().classes("oracle-card compact-card w-full"):
            ui.label("Queue").classes("text-sm font-bold")
            with ui.grid(columns=4).classes("w-full gap-1"):
                with ui.element("div").classes("mini-metric"):
                    ui.label("Queue").classes("label")
                    queue_labels["state"] = ui.label("-").classes("value")
                with ui.element("div").classes("mini-metric"):
                    ui.label("Pending").classes("label")
                    queue_labels["pending"] = ui.label("-").classes("value")
                with ui.element("div").classes("mini-metric"):
                    ui.label("Active").classes("label")
                    queue_labels["active"] = ui.label("-").classes("value")
                with ui.element("div").classes("mini-metric"):
                    ui.label("Fail/Skip").classes("label")
                    queue_labels["failed"] = ui.label("-").classes("value")
            queue_labels["message"] = ui.label("-").classes("path-label text-[10px]")

        with ui.card().classes("oracle-card compact-card w-full"):
            ui.label("Logs").classes("text-sm font-bold")
            fields["log_filter"] = ui.select(
                {"all": "all", "errors": "errors", "system": "system", "plotter": "plotter", "uploader": "uploader", "checks": "checks"},
                value="all",
                label="Filter",
            ).props("dense outlined").classes("w-full").on_value_change(refresh_logs)
            with ui.row().classes("gap-2"):
                safe_action_button("Refresh", refresh_logs)
                safe_action_button("Open logs", open_logs)
            return log_viewer([])
