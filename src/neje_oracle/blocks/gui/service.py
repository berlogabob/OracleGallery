from __future__ import annotations

import os
import sys
from pathlib import Path

from nicegui import ui

from ...shared.models import SystemMode
from . import screens, tokens
from .context import GuiContext
from .styles import page_style
from .ui import client_timer, estop_button, stop_button
from .workspaces import generative, motion, texture


def build_page() -> None:
    ctx = GuiContext()

    # Quasar theme, from the same tokens as the CSS. positive/negative/warning are
    # seeded too, so a toast or any Quasar-coloured element lands on the palette instead
    # of Quasar's defaults (the audit found stock Quasar red and gold on the safety controls).
    ui.colors(
        primary=tokens.ACCENT,
        secondary=tokens.TEXT_MID,
        accent=tokens.WARN,
        positive=tokens.OK,
        negative=tokens.DANGER,
        warning=tokens.WARN,
    )
    ui.add_head_html(page_style())

    with ui.column().classes("oracle-shell w-full gap-0 p-0"):
        # One top bar. The header row and the status bar used to stack (~84px); merged they
        # cost 40px, and everything the operator glances at -- where am I, what state, how do
        # I stop -- sits on a single line. E-STOP keeps its isolation gap (Fluidd #250).
        with ui.row().classes("top-bar w-full items-center gap-2"):
            ui.label("ORACLE").classes("oracle-title top-title")
            with ui.tabs(on_change=lambda event: ctx.workspace_changed(event.value)).classes(
                "workspace-tabs"
            ) as workspace_tabs:
                # Three phases of the job, not seven module names. Connecting, homing and
                # zeroing are on none of them -- they are in the machine rail.
                print_tab = ui.tab("print", label="PRINT")
                create_tab = ui.tab("create", label="CREATE")
                setup_tab = ui.tab("setup", label="SETUP")
            workspace_tabs.value = ctx.active_workspace["value"]
            ctx.workspace_tabs = workspace_tabs
            ctx.live_labels["fluidnc"] = ui.label("—").classes("state-chip")
            ctx.position_label = ui.label("X — · Y —").classes("position-readout")
            # The four fact tiles (zero/firebase/queue/sheet) are gone from the bar: the
            # rail's blockers line already names anything unmet, the sheet id lives on
            # PRINT where the sheet is, and context guards `if self.live_labels:` so the
            # unregistered keys are skipped, not broken.
            # TEST and EXHIBITION differed in exactly one thing: whether a run requires the
            # Firebase queue. Both drew real ink, so a mode literally named TEST was the more
            # dangerous one. The one difference is now the one control.
            ctx.run_profile_select = ui.switch(
                "Require Firebase",
                value=ctx.settings.system_mode == SystemMode.EXHIBITION.value,
                on_change=lambda event: ctx.run_profile_changed(event.value),
            ).tooltip("ON: a run must have the Firebase queue (exhibition). OFF: local-only verification prints.")
            ui.element("div").classes("status-spacer")
            stop_button("STOP PRINT", ctx.stop_print).tooltip("Pauses the current print (feed hold). The machine keeps its position.")
            ui.element("div").classes("estop-gap")
            estop_button("EMERGENCY STOP", ctx.emergency_stop).tooltip("Halts all motion NOW (software feed hold). Recover via SETUP → MACHINE.")
        ui.label(
            "Operator GUI is designed for MacBook/tablet width. Use the MacBook operator station for exhibition control."
        ).classes("mobile-operator-warning")

        # Machine rail + the screen's own area. Each screen owns everything right of the
        # rail -- canvas, context, action strip -- because "one big thing per screen" cannot
        # be built around a preview column that is pinned to all of them. The old global
        # Sheet Preview card now lives inside PRINT, where deciding-to-print happens.
        with ui.grid(columns="230px minmax(0, 1fr)").classes("w-full gap-2 min-h-0 workspace-panel workspace-grid"):
            with ui.column().classes("workspace-scroll"):
                motion.render_machine_rail(ctx)
            with ui.tab_panels(workspace_tabs, value=ctx.active_workspace["value"]).classes("w-full h-full"):
                with ui.tab_panel(print_tab).classes("p-0"):
                    screens.build_print(ctx)
                with ui.tab_panel(create_tab).classes("p-0"):
                    screens.build_create(ctx)
                with ui.tab_panel(setup_tab).classes("p-0"):
                    screens.build_setup(ctx)

    client_timer(2.0, ctx.refresh_status)
    ctx.persist_and_refresh()


def main() -> None:
    # Role-based access control: prevent GUI from running on wrong machines
    allowed_roles = os.getenv("NEJE_ALLOWED_ROLES", "gui_only").split(",")
    if "gui_only" not in allowed_roles:
        print("\n" + "=" * 70)
        print("ERROR: GUI not allowed on this machine")
        print("=" * 70)
        print()
        print("This error occurs when:")
        print("  1. You're on Mac mini (should only run: neje-uploader-agent)")
        print("  2. You set NEJE_ALLOWED_ROLES to restrict this machine")
        print()
        print("To fix:")
        print("  - On MacBook: Use launcher: start_oracle_gui.command")
        print("  - On MacBook: Or run: uv run neje-gui")
        print("  - On Mac mini: Use launcher: start_uploader_agent.command")
        print()
        print("For documentation, see: README.md 'Entry Points & Launchers' section")
        print("=" * 70 + "\n")
        sys.exit(1)

    from nicegui import app

    web_root = Path(__file__).resolve().parents[4] / "echodraw" / "generative-core" / "web"
    app.add_static_files("/generative", str(web_root))
    generative.register_routes()
    texture.register_routes()

    ui.page("/")(build_page)
    host = os.getenv("NEJE_GUI_HOST", "127.0.0.1")
    port = int(os.getenv("NEJE_GUI_PORT", "8787"))
    ui.run(host=host, port=port, reload=False, title="Oracle Operator")


if __name__ == "__main__":
    main()
