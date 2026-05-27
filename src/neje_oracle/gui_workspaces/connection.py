"""Connection workspace for the Oracle GUI.

The Connection workspace handles all device connection and status monitoring:
- FluidNC connection and health checks
- Device recovery controls (unlock, resume, reset)
- Manual motion controls (jog, homing, pen up/down)
- Real-time status display showing controller state
"""

from __future__ import annotations

import sys
from typing import Any, Callable

from nicegui import run, ui

from ..gui_ui import warning_banner
from ..models import ComponentStatus
from ..supervisor import SupervisorService


def build_connection_workspace(supervisor: SupervisorService) -> None:
    """Build the Connection workspace UI.
    
    This workspace handles device connectivity, controller communication,
    manual motion controls, and device recovery operations.
    
    Args:
        supervisor: The SupervisorService instance for system operations
    """
    # Shared state for this workspace
    fluidnc_labels: dict[str, Any] = {}
    fields: dict[str, Any] = {}
    
    # ========== Handlers ==========
    
    def update_fluidnc_labels(result: dict[str, Any]) -> None:
        """Update FluidNC status labels with probe results."""
        if "webui" in fluidnc_labels:
            fluidnc_labels["webui"].set_text("online" if result.get("http_online") else "offline")
        if "telnet" in fluidnc_labels:
            fluidnc_labels["telnet"].set_text("online" if result.get("telnet_online") else "offline")
        if "state" in fluidnc_labels:
            fluidnc_labels["state"].set_text(str(result.get("controller_state") or "Unknown"))
        if "mpos" in fluidnc_labels:
            fluidnc_labels["mpos"].set_text(_format_gui_tuple(result.get("machine_position")))
        if "pins" in fluidnc_labels:
            fluidnc_labels["pins"].set_text(str(result.get("pins") or "none"))
        if "modal" in fluidnc_labels:
            fluidnc_labels["modal"].set_text(str(result.get("modal_state") or "-").replace("\n", " | "))
        if "target" in fluidnc_labels:
            fluidnc_labels["target"].set_text(f"{result.get('http_url') or '-'} · {result.get('host')}:{result.get('port')}")
        if "message" in fluidnc_labels:
            fluidnc_labels["message"].set_text(str(result.get("message") or result.get("last_error") or "-"))
    
    def confirm_action(title: str, message: str, action: Callable) -> None:
        """Open confirmation dialog before executing action."""
        with ui.dialog() as dialog, ui.card().classes("oracle-card"):
            ui.label(title).classes("text-sm font-bold")
            ui.label(message).classes("text-xs text-[#8f4f2b]")
            
            async def confirmed() -> None:
                dialog.close()
                try:
                    result = action()
                    if hasattr(result, "__await__"):
                        await result
                except Exception as exc:  # noqa: BLE001
                    ui.notify(f"{title} failed: {exc}", color="negative")
                    return
                refresh_fluidnc_status()
            
            with ui.row().classes("gap-2"):
                ui.button("Cancel", on_click=dialog.close).props("dense flat")
                ui.button("Confirm", on_click=confirmed).props("dense color=warning")
        
        dialog.open()
    
    async def fluidnc_action(label: str, action: Callable, *, refresh_probe: bool = True) -> None:
        """Execute FluidNC action with notifications."""
        ui.notify(f"Sending {label}...", color="info")
        try:
            state = await run.io_bound(action)
        except Exception as exc:  # noqa: BLE001
            ui.notify(f"{label} failed: {exc}", color="negative")
            return
        
        color = "positive" if state.status == ComponentStatus.RUNNING else "warning"
        ui.notify(state.message, color=color)
        
        if refresh_probe:
            await check_fluidnc(scan=False)
    
    async def check_fluidnc(*, scan: bool = False) -> None:
        """Check FluidNC connectivity and update status displays."""
        ui.notify("Checking FluidNC...", color="info")
        try:
            probe = await run.io_bound(supervisor.probe_fluidnc, scan=scan)
        except Exception as exc:  # noqa: BLE001
            ui.notify(f"FluidNC check failed: {exc}", color="negative")
            return
        
        supervisor.check_fluidnc(probe)
        result = {
            **probe.to_dict(),
            "online": probe.online,
            "host": probe.telnet_host,
            "port": probe.telnet_port,
        }
        
        color = "positive" if probe.online else "negative"
        update_fluidnc_labels(result)
        ui.notify(probe.message, color=color)
    
    async def scan_fluidnc() -> None:
        """Scan LAN for FluidNC controllers."""
        await check_fluidnc(scan=True)
    
    def home_xy() -> None:
        """Show confirmation dialog for homing all axes."""
        confirm_action(
            "HOME ALL",
            "The plotter will run FluidNC homing command $H. Use this when FluidNC rejects single-axis homing.",
            lambda: fluidnc_action("home all", supervisor.home_xy_fluidnc, refresh_probe=False),
        )
    
    def home_axis(axis: str) -> None:
        """Show confirmation dialog for single-axis homing."""
        confirm_action(
            f"HOME {axis}",
            f"Single-axis homing sends $H={axis}. Use only if this FluidNC config supports it.",
            lambda: fluidnc_action(f"home {axis}", lambda: supervisor.home_fluidnc(axis), refresh_probe=False),
        )
    
    async def jog(axis: str, sign: float) -> None:
        """Jog specified axis in specified direction."""
        distance = sign * float(fields["jog_step"].value or 1)
        feed = float(fields["jog_feed"].value or 1000)
        await fluidnc_action(
            f"jog {axis}",
            lambda: supervisor.jog_fluidnc(axis, distance, feed),
            refresh_probe=False,
        )
    
    async def jog_x_negative() -> None:
        await jog("X", -1)
    
    async def jog_x_positive() -> None:
        await jog("X", 1)
    
    async def jog_y_negative() -> None:
        await jog("Y", -1)
    
    async def jog_y_positive() -> None:
        await jog("Y", 1)
    
    async def pen_up() -> None:
        """Move pen/Z axis to up position."""
        await fluidnc_action("pen up", supervisor.pen_up_fluidnc, refresh_probe=False)
    
    async def pen_down() -> None:
        """Move pen/Z axis to down position."""
        await fluidnc_action("pen down", supervisor.pen_down_fluidnc, refresh_probe=False)
    
    def unlock_alarm() -> None:
        """Show confirmation to unlock FluidNC alarm."""
        confirm_action(
            "UNLOCK ALARM",
            "This sends $X. It clears FluidNC alarm state without moving the machine.",
            lambda: fluidnc_action("unlock", supervisor.unlock_fluidnc_alarm),
        )
    
    def resume_after_hold() -> None:
        """Show confirmation to resume after hold/pause."""
        confirm_action(
            "RESUME AFTER HOLD",
            "This sends realtime cycle start ~. Confirm only if the machine is safe to resume.",
            lambda: fluidnc_action("resume", supervisor.resume_fluidnc),
        )
    
    def soft_reset() -> None:
        """Show confirmation for soft reset/abort."""
        confirm_action(
            "SOFT RESET / ABORT",
            "This sends Ctrl-X and disables print. Use only to abort/reset FluidNC.",
            lambda: fluidnc_action("soft reset", supervisor.soft_reset_fluidnc),
        )
    
    async def refresh_fluidnc_status() -> None:
        """Refresh FluidNC status without scan."""
        await check_fluidnc(scan=False)
    
    # ========== UI RENDERING ==========
    
    with ui.column().classes("workspace-scroll gap-2"):
        # FluidNC Connection Card
        with ui.card().classes("oracle-card compact-card w-full"):
            ui.label("FluidNC Connection").classes("text-sm font-bold")
            ui.label("Network/controller checks only. No motion except emergency, unlock, resume and reset.").classes("text-xs text-[#8f4f2b]")
            
            # Action buttons
            with ui.row().classes("gap-2"):
                ui.button("CONNECT", on_click=lambda: refresh_fluidnc_status()).props("dense color=positive")
                ui.button("SCAN LAN", on_click=scan_fluidnc).props("dense flat")
            
            # Status metrics grid
            with ui.grid(columns=2).classes("w-full gap-1"):
                with ui.element("div").classes("mini-metric"):
                    ui.label("WebUI").classes("label")
                    fluidnc_labels["webui"] = ui.label("-").classes("value")
                
                with ui.element("div").classes("mini-metric"):
                    ui.label("Telnet").classes("label")
                    fluidnc_labels["telnet"] = ui.label("-").classes("value")
                
                with ui.element("div").classes("mini-metric"):
                    ui.label("State").classes("label")
                    fluidnc_labels["state"] = ui.label("-").classes("value")
                
                with ui.element("div").classes("mini-metric"):
                    ui.label("MPos").classes("label")
                    fluidnc_labels["mpos"] = ui.label("-").classes("value")
                
                with ui.element("div").classes("mini-metric"):
                    ui.label("Inputs").classes("label")
                    fluidnc_labels["pins"] = ui.label("-").classes("value")
                
                with ui.element("div").classes("mini-metric"):
                    ui.label("Modal").classes("label")
                    fluidnc_labels["modal"] = ui.label("-").classes("value")
            
            # Status messages
            fluidnc_labels["message"] = ui.label("Not connected").classes("path-label text-xs font-bold")
            fluidnc_labels["target"] = ui.label("-").classes("path-label text-[10px] text-[#8f4f2b]")
        
        # Controller Recovery Card
        with ui.card().classes("oracle-card compact-card w-full"):
            ui.label("Controller Recovery").classes("text-sm font-bold")
            with ui.row().classes("gap-2"):
                ui.button("UNLOCK", on_click=unlock_alarm).props("dense color=warning")
                ui.button("Resume", on_click=resume_after_hold).props("dense flat")
                ui.button("RESET / ABORT", on_click=soft_reset).props("dense color=negative")
        
        # Manual Motion Card
        with ui.card().classes("oracle-card compact-card w-full"):
            ui.label("Manual Motion").classes("text-sm font-bold")
            ui.label("Jog and homing for setup. Manual movement is blocked while G-code streams.").classes("text-xs text-[#8f4f2b]")
            
            # Jog step and feed controls
            with ui.row().classes("gap-2 items-end"):
                fields["jog_step"] = ui.select(
                    {1.0: "1", 5.0: "5", 10.0: "10", 25.0: "25", 50.0: "50", 100.0: "100"},
                    value=1.0,
                    label="Step mm",
                ).props("dense outlined").classes("w-24")
                
                fields["jog_feed"] = ui.number("Feed", value=1000, min=1, step=100).props("dense outlined").classes("w-24")
                
                ui.button("Home all", on_click=home_xy).props("dense color=warning")
            
            # Joystick-style jog pad
            with ui.grid(columns=3).classes("w-full gap-1 jog-pad"):
                ui.label("")  # Top-left padding
                ui.button("Y+", on_click=jog_y_positive).props("dense").classes("w-12 h-12")
                ui.label("")  # Top-right padding
                
                ui.button("X-", on_click=jog_x_negative).props("dense").classes("w-12 h-12")
                ui.button("Y-", on_click=jog_y_negative).props("dense").classes("w-12 h-12")
                ui.button("X+", on_click=jog_x_positive).props("dense").classes("w-12 h-12")
            
            # Axis-specific controls
            with ui.row().classes("gap-1"):
                ui.button("Z up / Pen up", on_click=pen_up).props("dense flat")
                ui.button("Z- / Pen down", on_click=pen_down).props("dense flat")
                ui.button("Home X", on_click=lambda: home_axis("X")).props("dense flat")
                ui.button("Home Y", on_click=lambda: home_axis("Y")).props("dense flat")
        
        # Initial status check
        refresh_fluidnc_status()


def _format_gui_tuple(value: Any) -> str:
    """Format tuple/list for GUI display."""
    if isinstance(value, (list, tuple)):
        return ", ".join(f"{v:.2f}" if isinstance(v, float) else str(v) for v in value)
    return str(value) if value is not None else "-"
