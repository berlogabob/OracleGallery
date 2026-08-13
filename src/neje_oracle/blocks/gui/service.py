from __future__ import annotations

import os
import sys
from pathlib import Path

from nicegui import ui

from ...shared.models import SystemMode
from . import screens, tokens
from .context import GuiContext
from .ui import client_timer, select
from .workspaces import generative, motion, texture

PAGE_STYLE = """
<style>
__TOKENS_PLACEHOLDER__
  body { background: var(--cream); color: var(--ink); overflow: auto; }
  .q-field__control { min-height: 40px !important; }
  .q-field__label { font-size: 12px; }
  /* nicegui's own page padding is absent from every height calculation below, so the
     shell owns the viewport outright rather than racing it. */
  .nicegui-content { padding: 0 !important; }
  .oracle-shell { min-height: 100dvh; overflow: visible; box-sizing: border-box; }
  .oracle-card {
    width: 100%;
    padding: var(--space-md) 12px;
    /* nicegui puts gap:1rem between every child of .nicegui-card. The old override set
       padding only, so calibration's third card carried ~300px of invisible gap. */
    gap: var(--space-sm);
    background: rgba(255, 252, 245, 0.94);
    border: 1px solid var(--rule);
    border-radius: 14px;
    box-shadow: 0 8px 22px rgba(31, 26, 23, 0.07);
  }
  .oracle-title { letter-spacing: 0.16em; color: var(--rust); }
  .compact-card { padding: 10px 12px !important; }
  /* One 40px bar carries identity, navigation, state, position, profile and the stops.
     It replaces a 44px header row plus a ~40px status row; the reclaimed height goes to
     the canvas, which is the thing an operator actually watches. */
  .top-bar {
    height: 40px;
    flex-wrap: nowrap;
    background: rgba(255, 252, 245, 0.84);
    border-bottom: 1px solid var(--rule);
    padding: 2px 10px;
  }
  .top-title { font-size: 14px; }
  .top-bar .workspace-tabs { border: 0; background: transparent; min-height: 36px; flex: 0 1 auto; }
  .top-bar .q-tab { min-height: 34px; }
  .print-canvas { min-width: 0; overflow: hidden; }
  /* CREATE panes: one source visible at a time, canvas track + 340px knobs track.
     grid-auto-rows pins the single row to the pane height so h-full children resolve. */
  .create-pane { flex: 1 1 auto; min-height: 0; grid-auto-rows: 100%; }
  .create-pane-scroll { overflow-y: auto; }
  .create-canvas { min-width: 0; overflow: hidden; }
  .create-panel { overflow-y: auto; }
  .preview-fill { background: var(--paper); border: 1px solid var(--rule); border-radius: var(--radius-md); }
  /* Quasar's tab panel is not a flex child by default, so height:100% below it resolves
     to auto and the canvas column grows past the viewport instead of letting the
     preview scroll internally. Chain the height down explicitly. */
  .workspace-panel .q-tab-panels { height: 100%; }
  .workspace-panel .q-tab-panel { height: 100%; display: flex; flex-direction: column; padding: 0; }
  .workspace-panel .q-tab-panel > * { flex: 1 1 auto; min-height: 0; }
  /* The run band: slim rows on one flat surface, hairline-separated -- not stacked cards. */
  .run-band {
    border-left: 1px solid var(--rule);
    padding: 4px 8px;
    overflow-y: auto;
    min-height: 0;
  }
  .status-spacer { flex: 1 1 auto; }
  /* A deliberate dead zone, not decoration: the one control that must never be pressed
     by accident does not sit flush against the one next to it. */
  .estop-gap { width: var(--space-lg); flex: 0 0 auto; }
  .state-chip {
    font-size: 12px;
    font-weight: 700;
    letter-spacing: 0.12em;
    padding: 5px 10px;
    border-radius: 10px;
    border: 1px solid var(--rule);
    white-space: nowrap;
  }
  .state-ok { color: var(--ok); border-color: var(--ok); }
  .state-run { color: var(--ink); border-color: var(--ink); }
  .state-warn { color: var(--warn); border-color: var(--warn); background: var(--warn-wash); }
  .state-danger { color: var(--paper); background: var(--danger); border-color: var(--danger); }
  .state-offline { color: var(--ink-muted); border-color: var(--rule); }
  .position-readout {
    font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
    font-size: 12px;
    color: var(--ink);
    white-space: nowrap;
  }
  .live-strip {
    display: grid;
    grid-template-columns: repeat(4, minmax(104px, 1fr));
    gap: 6px;
    align-items: stretch;
    flex: 0 1 auto;
  }
  .live-strip .mini-metric { background: rgba(255, 252, 245, 0.9); }
  .live-strip .next-action { border-color: var(--rust); background: var(--paper); }
  .mobile-operator-warning {
    display: none;
    background: var(--warn-wash);
    border: 1px solid var(--gold);
    border-radius: 10px;
    color: var(--rust);
    padding: 8px 10px;
    font-size: 12px;
    font-weight: 700;
  }
  .workspace-tabs { min-height: 36px; flex: 0 1 auto; }
  .workspace-tabs .q-tab { min-height: 42px; padding: 0 12px; letter-spacing: 0.08em; font-weight: 700; }
  .workspace-tabs .q-tab--active { color: var(--rust); }
  /* These were three hand-counted constants and all three were wrong: 104px was reserved
     against 235px of real chrome, so 131px fell off the bottom -- clipped rather than
     scrolled, because the shell is overflow:hidden at >=1200px. The scroll box was also
     83px taller than the area it displayed in, putting the bottom of every workspace out
     of reach even at the end of the scroll. Flex takes whatever the header actually
     leaves, at any header height, so there is no number left to get wrong.
     width:100% is what fills the dead column: workspace roots sized to their content. */
  .workspace-panel { flex: 1 1 auto; min-height: 0; }
  .workspace-scroll {
    width: 100%;
    height: 100%;
    overflow-y: auto;
    overflow-x: hidden;
    padding-right: 8px;
    box-sizing: border-box;
  }
  .preview-frame { flex: 1 1 auto; min-height: 0; overflow: auto; width: 100%; }
  .preview-frame svg { display: block; width: auto; height: auto; max-width: none; max-height: none; }
  .path-label { max-width: 340px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .tight-slider .q-slider { min-height: 28px; }
  .warning-banner { background: var(--warn-wash); border: 1px solid var(--gold); border-radius: 10px; color: var(--rust); padding: 6px 8px; font-size: 12px; }
  .log-viewer textarea { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 11px; line-height: 1.35; }
  .q-btn { min-height: 30px; }
  .mini-metric { border: 1px solid var(--rule); border-radius: 10px; padding: 5px 7px; background: rgba(255,255,255,0.45); }
  .mini-metric .label { font-size: 9px; letter-spacing: 0.16em; color: var(--rust); text-transform: uppercase; }
  .mini-metric .value { font-size: 12px; font-weight: 700; color: var(--ink); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .preview-legend { border-top: 1px solid var(--rule); padding-top: 6px; }
  .legend-chip { display: flex; align-items: center; gap: 5px; font-size: 10px; color: var(--ink); white-space: nowrap; }
  .legend-dot { width: 9px; height: 9px; border-radius: 999px; border: 1px solid var(--ink); display: inline-block; flex: 0 0 auto; }
  .legend-ring { width: 15px; height: 15px; border-radius: 999px; border: 1.5px solid var(--ink); display: inline-block; flex: 0 0 auto; }
  .legend-double-ring { box-shadow: inset 0 0 0 3px var(--paper), inset 0 0 0 4.4px var(--ink); }
  @media (min-width: 1200px) {
    body { overflow: hidden; }
    .oracle-shell { height: 100dvh; max-height: 100dvh; overflow: hidden; }
  }
  @media (max-width: 1199px) {
    .oracle-shell { height: auto; overflow: visible; }
    .workspace-grid { grid-template-columns: 1fr !important; height: auto !important; overflow: visible !important; }
    .workspace-scroll { height: auto; max-height: none; overflow: visible; padding-right: 0; }
    .preview-frame { max-height: 70vh; }
    .path-label { max-width: 100%; white-space: normal; }
    .live-strip { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    .status-spacer { display: none; }
  }
  @media (max-width: 760px) {
    .oracle-shell { min-width: 560px; }
    .mobile-operator-warning { display: block; }
    .workspace-tabs { overflow-x: auto; }
  }
  /* The rail is fixed-width and always present, so it must not shrink with the
     workspace beside it -- a jog button that moves is a jog button you mis-hit. */
  .machine-rail { display: flex; flex-direction: column; gap: var(--space-sm); width: 100%; }
  .jog-pad { display: grid; gap: 4px; width: 100%; justify-items: center; }
  .jog-pad .q-btn { width: 100%; min-width: 0; }
  /* --- components (blocks/gui/ui.py emits these; nothing else styles) --- */
  .oracle-workspace { display: flex; flex-direction: column; gap: var(--space-sm); }
  .oracle-card-title { font-size: 13px; font-weight: 700; color: var(--ink); }
  .oracle-helper { font-size: 12px; color: var(--rust); }
  .oracle-toolbar { display: flex; align-items: center; gap: var(--space-sm); }
  .oracle-toolbar-wide { width: 100%; }
  .oracle-field { min-width: 7rem; }
  .oracle-btn { border-radius: var(--radius-sm); letter-spacing: 0.04em; }
  .oracle-btn-primary { background: var(--rust) !important; color: var(--paper) !important; }
  /* A bordered ghost, not bare text. Flat Quasar buttons render as a label with no
     chrome, which is how PEN UP / HOME X / Z UP ended up visually indistinguishable from
     static text while filled buttons sat beside them running the same class of machine
     command (audit F-006, F-007, F-023, F-024). Every clickable action gets an
     affordance. */
  .oracle-btn-safe {
    color: var(--ink-mid) !important;
    border: 1px solid var(--rule);
    background: var(--paper) !important;
  }
  .oracle-btn-safe:hover { border-color: var(--rust); color: var(--rust) !important; }
  .oracle-btn-danger { background: var(--danger) !important; color: var(--paper) !important; }
  .oracle-embed { width: 100%; border: 0; background: var(--paper); border-radius: var(--radius-md); }
  .oracle-embed-fill { flex: 1 1 auto; min-height: 0; height: 100%; }
  .oracle-metric-line { font-size: 12px; color: var(--rust); }
</style>
"""


def build_page() -> None:
    ctx = GuiContext()

    # Quasar theme, from the same tokens as the CSS -- these used to be a fourth
    # palette that nothing referenced by name.
    ui.colors(primary=tokens.INK, secondary=tokens.RUST, accent=tokens.GOLD)
    ui.add_head_html(PAGE_STYLE.replace("__TOKENS_PLACEHOLDER__", tokens.css_root_block()))

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
            # The run profile is an operator decision, not a side effect of navigation.
            ctx.run_profile_select = select(
                {SystemMode.TEST.value: "TEST", SystemMode.EXHIBITION.value: "EXHIBITION"},
                value=ctx.settings.system_mode,
                label="Run profile",
                on_change=lambda event: ctx.run_profile_changed(event.value),
            )
            ui.element("div").classes("status-spacer")
            ui.button("STOP PRINT", on_click=ctx.stop_print).props("dense color=warning")
            ui.element("div").classes("estop-gap")
            ui.button("EMERGENCY STOP", on_click=ctx.emergency_stop).props("dense color=negative")
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
