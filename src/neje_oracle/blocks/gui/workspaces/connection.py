"""Connection workspace: FluidNC connectivity, recovery, and manual motion.

One column, one builder. All handlers live on `ctx` (shared with Calibration).
"""

from __future__ import annotations

from nicegui import ui

from ..context import GuiContext
from ..ui import client_timer, helper_text, mini_metric, primary_action_button, safe_action_button
from .motion import render_motion_panel


def build(ctx: GuiContext) -> None:
    with ui.column().classes("workspace-scroll gap-2"):
        # FluidNC connection
        with ui.card().classes("oracle-card compact-card w-full"):
            ui.label("FluidNC Connection").classes("text-sm font-bold")
            helper_text("Network/controller checks only. No motion except emergency, unlock, resume and reset.")
            with ui.row().classes("gap-2"):
                primary_action_button("CONNECT", lambda: ctx.check_fluidnc(scan=False))
                safe_action_button("SCAN LAN", ctx.scan_fluidnc)
            with ui.grid(columns=2).classes("w-full gap-1"):
                for key, label in (
                    ("webui", "WebUI"),
                    ("telnet", "Telnet"),
                    ("state", "State"),
                    ("mpos", "MPos"),
                    ("pins", "Inputs"),
                    ("modal", "Modal"),
                ):
                    ctx.fluidnc_labels[key] = mini_metric(label)
            ctx.fluidnc_labels["message"] = ui.label("Not connected").classes("path-label text-xs font-bold")
            ctx.fluidnc_labels["target"] = ui.label("-").classes("path-label text-[10px] text-[#8f4f2b]")

        # Controller recovery
        with ui.card().classes("oracle-card compact-card w-full"):
            ui.label("Controller Recovery").classes("text-sm font-bold")
            with ui.row().classes("gap-2"):
                ui.button("UNLOCK", on_click=ctx.unlock_alarm).props("dense color=warning")
                safe_action_button("Resume", ctx.resume_after_hold)
                ui.button("RESET / ABORT", on_click=ctx.soft_reset).props("dense color=negative")

        # Manual motion (shared card)
        render_motion_panel(ctx)

        # Notes
        with ui.card().classes("oracle-card compact-card w-full"):
            ui.label("Connection checklist").classes("text-sm font-bold")
            helper_text("1. Join the plotter Wi-Fi or hotspot.")
            helper_text("2. Press CONNECT and verify WebUI, Telnet, and Idle.")
            helper_text("3. Use recovery only for a known alarm or hold state.")

        # Defer the initial async probe until the page event loop is running.
        client_timer(0.1, lambda: ctx.check_fluidnc(scan=False), once=True)
