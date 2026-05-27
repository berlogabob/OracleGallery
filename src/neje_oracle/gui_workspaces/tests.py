"""Tests workspace for the Oracle GUI.

The Tests workspace provides test capabilities for validating the plotter setup:
- System node status monitoring (FluidNC, Mac mini, Firebase, Queue, Print)
- G-code generation and test printing
- Direct SVG file printing for quick validation
"""

from __future__ import annotations

from typing import Any, Callable

from nicegui import ui

from ..models import GUISettings
from ..supervisor import SupervisorService


def build_tests_workspace(
    supervisor: SupervisorService,
    settings: GUISettings,
    fields: dict[str, Any],
    node_pills: dict[str, Any],
    uploaded_svg: dict[str, Any],
    uploaded_svg_label: Any,
    generate_dry_run: Callable,
    start_test_print: Callable,
    handle_svg_upload: Callable,
    print_uploaded_svg: Callable,
    persist_and_refresh: Callable,
) -> None:
    """Build the Tests workspace UI.
    
    This workspace provides test controls for validating plotter setup and
    running test prints.
    
    Args:
        supervisor: The SupervisorService instance
        settings: Current plotter settings
        fields: Dict to store field references
        node_pills: Dict to store status pill UI elements
        uploaded_svg: Dict with 'name' and 'bytes' keys for SVG upload state
        uploaded_svg_label: UI label to show selected SVG filename
        generate_dry_run: Callback to generate dry-run G-code
        start_test_print: Callback to start a test print
        handle_svg_upload: Callback to handle SVG upload events
        print_uploaded_svg: Callback to print the uploaded SVG
        persist_and_refresh: Callback to save settings and refresh preview
    """
    
    with ui.column().classes("workspace-scroll gap-2"):
        # System Nodes Status Card
        with ui.card().classes("oracle-card compact-card w-full"):
            ui.label("System nodes").classes("text-sm font-bold")
            ui.label("Green = ready/running, yellow = warning, gray = offline/stopped, red = error.").classes("text-xs text-[#8f4f2b]")
            with ui.row().classes("gap-2 flex-wrap"):
                node_pills["fluidnc"] = _status_pill("Plotter")
                node_pills["macmini"] = _status_pill("Mac mini")
                node_pills["firebase"] = _status_pill("Firebase")
                node_pills["queue"] = _status_pill("Queue")
                node_pills["print"] = _status_pill("Print")
        
        # G-code Test Draw Card
        with ui.card().classes("oracle-card compact-card w-full"):
            ui.label("G-code test draw").classes("text-sm font-bold")
            ui.label("Generates a local sheet from bundled symbols or starts a test print from the current queue/settings.").classes("text-xs text-[#8f4f2b]")
            with ui.row().classes("items-center gap-2"):
                ui.button("GENERATE G-CODE", on_click=generate_dry_run).props("dense")
                ui.button("START TEST PRINT", on_click=start_test_print).props("dense color=positive")
        
        # SVG Test Draw Card
        with ui.card().classes("oracle-card compact-card w-full"):
            ui.label("SVG test draw").classes("text-sm font-bold")
            ui.label("Prints the selected Inkscape SVG directly to FluidNC. Requires passing system checks, work zero, CONNECT and Idle.").classes("text-xs text-[#8f4f2b]")
            
            # SVG upload controls
            with ui.row().classes("gap-2 w-full"):
                # Origin X
                fields["direct_svg_origin_x_mm"] = ui.number(
                    "SVG X0",
                    value=settings.direct_svg_origin_x_mm,
                    min=0,
                ).props("dense outlined").classes("w-full").on_value_change(persist_and_refresh)
                # Origin Y
                fields["direct_svg_origin_y_mm"] = ui.number(
                    "SVG Y0",
                    value=settings.direct_svg_origin_y_mm,
                    min=0,
                ).props("dense outlined").classes("w-full").on_value_change(persist_and_refresh)
            
            # File upload
            ui.upload(on_upload=handle_svg_upload).props("accept=.svg max-files=1 auto-upload").classes("w-full")
            
            # Print button and file label
            with ui.row().classes("items-center gap-2"):
                ui.button("START SVG PRINT", on_click=print_uploaded_svg).props("dense color=positive")
                # Use the passed label reference
                uploaded_svg_label



def _status_pill(label: str) -> Any:
    """Create a status pill for system node monitoring.
    
    The pill shows the node status with color coding:
    - Green: ready/running
    - Yellow: warning
    - Gray: offline/stopped
    - Red: error
    
    Args:
        label: Display label for the node
        
    Returns:
        UI element representing the status pill
    """
    with ui.element("div").classes("status-pill"):
        ui.label(label).classes("text-xs font-bold")
        return ui.label("-").classes("text-[10px]")

