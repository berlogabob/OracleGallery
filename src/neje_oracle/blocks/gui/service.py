from __future__ import annotations

import os
import sys
from pathlib import Path

from nicegui import ui

from ...shared.origin_markers import (
    ALL_ORIGINS,
    ORIGIN_LABELS,
    ORIGIN_MARKER_POSITIONS,
    ORIGIN_PREVIEW_COLORS,
)
from . import tokens
from .context import GuiContext
from .ui import helper_text, mini_metric, warning_banner
from .workspaces import calibration, connection, exhibition, generative, image, tests, work

PAGE_STYLE = """
<style>
__TOKENS_PLACEHOLDER__
  body { background: var(--cream); color: var(--ink); overflow: auto; }
  .q-field__control { min-height: 40px !important; }
  .q-field__label { font-size: 12px; }
  .oracle-shell { min-height: 100vh; overflow: visible; }
  .oracle-card {
    width: 100%;
    padding: var(--space-md) 12px;
    background: rgba(255, 252, 245, 0.94);
    border: 1px solid var(--rule);
    border-radius: 14px;
    box-shadow: 0 8px 22px rgba(31, 26, 23, 0.07);
  }
  .oracle-title { letter-spacing: 0.16em; color: var(--rust); }
  .compact-card { padding: 10px 12px !important; }
  .live-strip {
    display: grid;
    grid-template-columns: repeat(6, minmax(110px, 1fr));
    gap: 6px;
    align-items: stretch;
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
  .workspace-tabs {
    background: rgba(255, 252, 245, 0.84);
    border: 1px solid var(--rule);
    border-radius: 14px;
    min-height: 44px;
    flex: 1 1 auto;
  }
  .workspace-tabs .q-tab { min-height: 42px; padding: 0 12px; letter-spacing: 0.08em; font-weight: 700; }
  .workspace-tabs .q-tab--active { color: var(--rust); }
  .workspace-panel { min-height: calc(100vh - 104px); }
  .workspace-scroll {
    max-height: calc(100vh - 120px);
    overflow-y: auto;
    overflow-x: hidden;
    padding-right: 8px;
    box-sizing: border-box;
  }
  .preview-frame { max-height: calc(100vh - 210px); overflow: auto; width: 100%; }
  .preview-frame svg { display: block; width: auto; height: auto; max-width: none; max-height: none; }
  .path-label { max-width: 340px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .tight-slider .q-slider { min-height: 28px; }
  .warning-banner { background: var(--warn-wash); border: 1px solid var(--gold); border-radius: 10px; color: var(--rust); padding: 6px 8px; font-size: 12px; }
  .log-viewer textarea { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 11px; line-height: 1.35; }
  .q-btn { min-height: 30px; }
  .mini-metric { border: 1px solid var(--rule); border-radius: 10px; padding: 5px 7px; background: rgba(255,255,255,0.45); }
  .mini-metric .label { font-size: 9px; letter-spacing: 0.16em; color: var(--rust); text-transform: uppercase; }
  .mini-metric .value { font-size: 12px; font-weight: 700; color: var(--ink); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .jog-pad .q-btn { width: 54px; }
  .preview-legend { border-top: 1px solid var(--rule); padding-top: 6px; }
  .legend-chip { display: flex; align-items: center; gap: 5px; font-size: 10px; color: var(--ink); white-space: nowrap; }
  .legend-dot { width: 9px; height: 9px; border-radius: 999px; border: 1px solid var(--ink); display: inline-block; flex: 0 0 auto; }
  .legend-ring { width: 15px; height: 15px; border-radius: 999px; border: 1.5px solid var(--ink); display: inline-block; flex: 0 0 auto; }
  .legend-double-ring { box-shadow: inset 0 0 0 3px var(--paper), inset 0 0 0 4.4px var(--ink); }
  @media (min-width: 1200px) {
    body { overflow: hidden; }
    .oracle-shell { height: 100vh; max-height: 100vh; overflow: hidden; }
    .workspace-panel { height: calc(100vh - 104px); overflow: hidden; }
  }
  @media (max-width: 1199px) {
    .workspace-grid { grid-template-columns: 1fr !important; height: auto !important; overflow: visible !important; }
    .workspace-scroll { max-height: none; overflow: visible; padding-right: 0; }
    .preview-frame { max-height: 70vh; }
    .path-label { max-width: 100%; white-space: normal; }
    .live-strip { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  }
  @media (max-width: 760px) {
    .oracle-shell { min-width: 560px; }
    .mobile-operator-warning { display: block; }
    .workspace-tabs { overflow-x: auto; }
  }
  /* --- components (blocks/gui/ui.py emits these; nothing else styles) --- */
  .oracle-workspace { display: flex; flex-direction: column; gap: var(--space-sm); }
  .oracle-card-title { font-size: 13px; font-weight: 700; color: var(--ink); }
  .oracle-helper { font-size: 12px; color: var(--rust); }
  .oracle-toolbar { display: flex; align-items: center; gap: var(--space-sm); }
  .oracle-toolbar-wide { width: 100%; }
  .oracle-field { min-width: 7rem; }
  .oracle-btn { border-radius: var(--radius-sm); letter-spacing: 0.04em; }
  .oracle-btn-primary { background: var(--rust) !important; color: var(--paper) !important; }
  .oracle-btn-safe { color: var(--ink-mid) !important; }
  .oracle-btn-danger { background: var(--danger) !important; color: var(--paper) !important; }
</style>
"""


def _live_metric(ctx: GuiContext, key: str, label: str, *, important: bool = False) -> None:
    ctx.live_labels[key] = mini_metric(label, extra_classes="next-action" if important else "")


def _preview_legend() -> None:
    with ui.column().classes("preview-legend w-full gap-1"):
        with ui.row().classes("items-center gap-3 flex-wrap"):
            with ui.element("div").classes("legend-chip"):
                ui.element("span").classes("legend-ring")
                ui.label("outer ring: real/user cell").classes("text-[10px]")
            with ui.element("div").classes("legend-chip"):
                ui.element("span").classes("legend-ring legend-double-ring")
                ui.label("double ring: filler/local cell").classes("text-[10px]")
            with ui.element("div").classes("legend-chip"):
                ui.element("span").classes("legend-dot").style(
                    "background:var(--ink-muted); border-color:var(--ink-muted); opacity:0.45;"
                )
                ui.label("gray: next in line").classes("text-[10px]")
        with ui.row().classes("items-center gap-3 flex-wrap"):
            for origin in ALL_ORIGINS:
                position = ORIGIN_MARKER_POSITIONS.get(origin, "right").replace("-", " ")
                color = ORIGIN_PREVIEW_COLORS.get(origin, tokens.INK_MUTED)
                with ui.element("div").classes("legend-chip"):
                    ui.element("span").classes("legend-dot").style(f"background:{color}; border-color:{color};")
                    ui.label(f"{ORIGIN_LABELS[origin]} dot: {position}").classes("text-[10px]")


def build_page() -> None:
    ctx = GuiContext()

    # Quasar theme, from the same tokens as the CSS -- these used to be a fourth
    # palette that nothing referenced by name.
    ui.colors(primary=tokens.INK, secondary=tokens.RUST, accent=tokens.GOLD)
    ui.add_head_html(PAGE_STYLE.replace("__TOKENS_PLACEHOLDER__", tokens.css_root_block()))

    with ui.column().classes("oracle-shell w-full gap-2 p-3"):
        # Header + tabs + emergency stop
        with ui.row().classes("w-full items-center gap-3"):
            ui.label("THE ORACLE OPERATOR").classes("oracle-title text-lg")
            with ui.tabs(on_change=lambda event: ctx.workspace_changed(event.value)).classes(
                "workspace-tabs"
            ) as workspace_tabs:
                connection_tab = ui.tab("connection", label="1 CONNECTION")
                calibration_tab = ui.tab("calibration", label="2 CALIBRATION")
                tests_tab = ui.tab("tests", label="3 TESTS")
                work_tab = ui.tab("work", label="4 WORK")
                exhibition_tab = ui.tab("exhibition", label="5 EXHIBITION")
                generative_tab = ui.tab("generative", label="6 GENERATIVE")
                image_tab = ui.tab("image", label="7 IMAGE")
            workspace_tabs.value = ctx.active_workspace["value"]
            ctx.workspace_tabs = workspace_tabs
            ui.button("STOP PRINT", on_click=ctx.stop_print).props("dense color=warning")
            ui.button("EMERGENCY STOP", on_click=ctx.emergency_stop).props("dense color=negative")

        warning_banner("Plotter output starts only after system checks pass, work zero is set, and FluidNC is Idle.")
        ui.label(
            "Operator GUI is designed for MacBook/tablet width. Use the MacBook operator station for exhibition control."
        ).classes("mobile-operator-warning")

        # Live status strip
        with ui.element("div").classes("live-strip w-full"):
            _live_metric(ctx, "fluidnc", "Now")
            _live_metric(ctx, "zero", "Work zero")
            _live_metric(ctx, "firebase", "Firebase")
            _live_metric(ctx, "queue", "Queue")
            _live_metric(ctx, "sheet", "Sheet")
            _live_metric(ctx, "next", "Next action", important=True)
            ctx.live_labels["blockers"] = mini_metric("Blockers", style="grid-column: 1 / -1")

        # Workspace column + always-visible preview
        with ui.grid(columns="minmax(420px, 1fr) 480px").classes("w-full gap-2 min-h-0 workspace-panel workspace-grid"):
            with ui.tab_panels(workspace_tabs, value=ctx.active_workspace["value"]).classes("w-full h-full"):
                with ui.tab_panel(connection_tab).classes("p-0"):
                    connection.build(ctx)
                with ui.tab_panel(calibration_tab).classes("p-0"):
                    calibration.build(ctx)
                with ui.tab_panel(tests_tab).classes("p-0"):
                    tests.build(ctx)
                with ui.tab_panel(work_tab).classes("p-0"):
                    work.build(ctx)
                with ui.tab_panel(exhibition_tab).classes("p-0"):
                    exhibition.build(ctx)
                with ui.tab_panel(generative_tab).classes("p-0"):
                    generative.build(ctx)
                with ui.tab_panel(image_tab).classes("p-0"):
                    image.build(ctx)

            with ui.card().classes("oracle-card compact-card w-full min-h-0 h-full"):
                with ui.row().classes("w-full items-center justify-between"):
                    ui.label("Sheet Preview").classes("text-sm font-bold")
                ctx.preview_progress_label = helper_text("-")
                _preview_legend()
                ctx.preview = ui.html().classes("preview-frame w-full")

    ui.timer(2.0, ctx.refresh_status)
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

    ui.page("/")(build_page)
    host = os.getenv("NEJE_GUI_HOST", "127.0.0.1")
    port = int(os.getenv("NEJE_GUI_PORT", "8787"))
    ui.run(host=host, port=port, reload=False, title="Oracle Operator")


if __name__ == "__main__":
    main()
