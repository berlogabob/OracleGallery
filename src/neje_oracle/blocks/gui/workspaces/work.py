"""Diagnostics: the peripherals and the log tail.

What remains of the old WORK tab. Its run half (system run, system check, queue) lives on
the PRINT screen where the run is watched; these cards are what you open when something is
wrong, behind the Diagnostics expansion in SETUP.
"""

from __future__ import annotations

from nicegui import ui

from ..context import GuiContext
from ..ui import helper_text, log_viewer, primary_action_button, safe_action_button


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
    """Diagnostics only. The run half lives on the PRINT screen (screens.build_print)."""
    with ui.column().classes("w-full gap-2"):
        build_diagnostics(ctx)
