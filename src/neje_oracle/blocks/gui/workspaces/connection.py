"""Connection workspace: FluidNC connectivity, recovery, and manual motion.

One column, one builder. All handlers live on `ctx` (shared with Calibration).
"""

from __future__ import annotations

from nicegui import ui

from ..context import GuiContext
from ..ui import client_timer, helper_text, mini_metric, primary_action_button, safe_action_button


def build(ctx: GuiContext) -> None:
    with ui.column().classes("w-full gap-2"):
        # FluidNC connection
        with ui.card().classes("oracle-card compact-card w-full"):
            ui.label("FluidNC Connection").classes("text-sm font-bold")
            helper_text("Connect and recover the controller. Jog and homing are in the left rail.")
            with ui.row().classes("gap-2"):
                primary_action_button("CONNECT", lambda: ctx.check_fluidnc(scan=False))
                safe_action_button("SCAN LAN", ctx.scan_fluidnc)
            with ui.grid(columns=4).classes("w-full gap-1"):
                for key, label in (
                    ("webui", "WebUI"),
                    ("telnet", "Telnet"),
                    ("pins", "Inputs"),
                    ("modal", "Modal"),
                ):
                    ctx.fluidnc_labels[key] = mini_metric(label)
            # The status bar owns the machine state chip and position readout; these keys
            # survive invisibly for context.update_fluidnc_labels and the workspace test.
            for key in ("state", "mpos"):
                stub = ui.label("")
                stub.set_visibility(False)
                ctx.fluidnc_labels[key] = stub
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

        # Notes
        with ui.card().classes("oracle-card compact-card w-full"):
            ui.label("Connection checklist").classes("text-sm font-bold")
            helper_text("1. Join the plotter Wi-Fi or hotspot.")
            helper_text("2. Press CONNECT and verify WebUI, Telnet, and Idle.")
            helper_text("3. Use recovery only for a known alarm or hold state.")

        # Defer the initial async probe until the page event loop is running.
        client_timer(0.1, lambda: ctx.check_fluidnc(scan=False), once=True)
