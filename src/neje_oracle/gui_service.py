from __future__ import annotations

import os
import subprocess
from typing import Any

from nicegui import ui

from .config import PlotterSettings
from .gui_support import (
    build_preview_svg,
    build_symbol_preview_svg,
    confirm_plotter_reload,
    create_idle_bank_from_gui,
    create_user_sessions_from_gui,
    default_idle_root,
    default_scale_config_path,
    effective_randomness,
    generate_dry_run_sheet,
    layout_capacity,
    list_base_symbols,
    load_gui_settings,
    load_symbol_scales,
    read_plotter_status,
    save_gui_settings,
    save_symbol_scales,
    set_plotter_control,
)


def build_page() -> None:
    settings = load_gui_settings()
    scales = load_symbol_scales()
    symbols = list_base_symbols()

    fields: dict[str, Any] = {}
    status_labels: dict[str, Any] = {}
    symbol_previews: dict[str, Any] = {}
    control_labels: dict[str, Any] = {}
    cycle_state = {"index": 0}

    ui.colors(primary="#1f1a17", secondary="#9a5b24", accent="#c7a45a")
    ui.add_head_html(
        """
        <style>
          body { background: #f7f1e7; color: #1f1a17; overflow: hidden; }
          .q-field__control { min-height: 40px !important; }
          .q-field__label { font-size: 12px; }
          .oracle-shell { height: 100vh; max-height: 100vh; overflow: hidden; }
          .oracle-card {
            background: rgba(255, 252, 245, 0.94);
            border: 1px solid #dac9ad;
            border-radius: 14px;
            box-shadow: 0 8px 22px rgba(31, 26, 23, 0.07);
          }
          .oracle-title { letter-spacing: 0.16em; color: #8f4f2b; }
          .compact-card { padding: 10px 12px !important; }
          .preview-frame svg { width: 100%; height: auto; max-height: 64vh; }
          .symbol-preview svg { width: 58px; height: 58px; }
          .path-label { max-width: 340px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
        </style>
        """
    )

    def pull_settings_from_fields() -> None:
        settings.run_mode = str(fields["run_mode"].value)
        settings.dry_run = str(fields["transport_mode"].value) == "dry_run"
        settings.layout_mode = str(fields["layout_mode"].value)
        settings.cell_diameter_mm = float(fields["cell_diameter_mm"].value or 1)
        settings.gap_mm = float(fields["gap_mm"].value or 0)
        settings.randomness = float(fields["randomness"].value or 0)
        settings.randomness_fine = float(fields["randomness_fine"].value or 0)
        settings.user_count = int(fields["user_count"].value or 1)
        settings.live_interval_seconds = float(fields["live_interval_seconds"].value or 1)
        settings.selected_symbol = str(fields["selected_symbol"].value)
        settings.idle_variations_per_symbol = int(fields["idle_variations_per_symbol"].value or 1)
        settings.idle_count = max(len(symbols) * settings.idle_variations_per_symbol, 1)
        settings.include_rings = bool(fields["include_rings"].value)
        settings.sheet_width_mm = float(fields["sheet_width_mm"].value or 1)
        settings.sheet_height_mm = float(fields["sheet_height_mm"].value or 1)
        settings.sheet_margin_mm = float(fields["sheet_margin_mm"].value or 0)
        settings.global_scale = float(fields["global_scale"].value or 1)

    def persist_and_refresh() -> None:
        pull_settings_from_fields()
        save_gui_settings(settings)
        preview.content = build_preview_svg(settings)
        preview.update()
        capacity_label.set_text(f"{layout_capacity(settings)} cells")
        mode_label.set_text(settings.run_mode.upper())
        transport_label.set_text("DRY RUN" if settings.dry_run else "REAL FLUIDNC")
        test_panel.visible = settings.run_mode == "test"
        test_panel.update()
        live_timer.interval = max(settings.live_interval_seconds, 1.0)
        refresh_symbol_previews()
        refresh_status()

    def refresh_symbol_previews() -> None:
        for symbol in symbols:
            scale = scales.get(symbol.name, 1.0) * settings.global_scale
            symbol_previews[symbol.name].content = build_symbol_preview_svg(
                symbol,
                marker_kind="user",
                scale=scale,
                include_rings=settings.include_rings,
                randomness=effective_randomness(settings),
            )
            symbol_previews[symbol.name].update()

    def save_scales_from_fields() -> None:
        pull_settings_from_fields()
        for symbol in symbols:
            scales[symbol.name] = float(fields[f"scale:{symbol.name}"].value or 1.0)
        save_symbol_scales(scales)
        refresh_symbol_previews()
        ui.notify("Symbol scales saved", color="positive")

    def generate_user_sessions() -> None:
        pull_settings_from_fields()
        paths = create_user_sessions_from_gui(settings, start_index=cycle_state["index"])
        cycle_state["index"] += len(paths)
        save_gui_settings(settings)
        ui.notify(f"Generated {len(paths)} user session(s)", color="positive")
        last_user_output.set_text(str(paths[-1]) if paths else "-")

    def generate_all_user_symbols() -> None:
        pull_settings_from_fields()
        original_count = settings.user_count
        original_symbol = settings.selected_symbol
        settings.user_count = len(symbols)
        settings.selected_symbol = "__cycle__"
        paths = create_user_sessions_from_gui(settings, start_index=0)
        settings.user_count = original_count
        settings.selected_symbol = original_symbol
        cycle_state["index"] = len(symbols)
        save_gui_settings(settings)
        ui.notify(f"Generated all {len(paths)} base symbols", color="positive")
        last_user_output.set_text(str(paths[-1]) if paths else "-")

    def generate_idle_bank() -> None:
        pull_settings_from_fields()
        paths = create_idle_bank_from_gui(settings)
        save_gui_settings(settings)
        ui.notify(f"Generated {len(paths)} idle variation(s)", color="positive")
        idle_output.set_text(f"{len(paths)} files -> {default_idle_root()}")

    def generate_dry_run() -> None:
        pull_settings_from_fields()
        try:
            output = generate_dry_run_sheet(settings)
        except Exception as exc:  # noqa: BLE001
            ui.notify(f"Dry-run failed: {exc}", color="negative")
            return
        ui.notify(f"Dry-run G-code: {output['gcode']}", color="positive")
        refresh_status()

    def refresh_status() -> None:
        status = read_plotter_status()
        for key, label in status_labels.items():
            label.set_text(str(status.get(key, "-") or "-"))
        for key, label in control_labels.items():
            label.set_text(str(status.get(key, "-") or "-"))
        total = int(status.get("processed_symbols", 0) or 0)
        progress.value = min(total / max(layout_capacity(settings), 1), 1.0)
        if status.get("pending_reload"):
            reload_button.enable()
        else:
            reload_button.disable()

    def confirm_reload() -> None:
        if confirm_plotter_reload():
            ui.notify("Reload confirmed", color="positive")
        else:
            ui.notify("No reload confirmation is pending")
        refresh_status()

    def start_print() -> None:
        pull_settings_from_fields()
        control = set_plotter_control(print_enabled=True, run_mode=settings.run_mode, dry_run=settings.dry_run)
        ui.notify(f"Print enabled ({control.run_mode}, {'dry-run' if control.dry_run else 'real FluidNC'})", color="positive")
        refresh_status()

    def stop_print() -> None:
        set_plotter_control(print_enabled=False)
        ui.notify("Print will stop before the next sheet", color="warning")
        refresh_status()

    def update_control_mode() -> None:
        pull_settings_from_fields()
        save_gui_settings(settings)
        set_plotter_control(run_mode=settings.run_mode, dry_run=settings.dry_run)
        if not settings.dry_run:
            ui.notify("REAL FLUIDNC selected. START PRINT will send the next sheet to the plotter.", color="warning")
        persist_and_refresh()

    def open_spool() -> None:
        subprocess.run(["open", str(PlotterSettings().spool_root)], check=False)

    def toggle_live() -> None:
        pull_settings_from_fields()
        live_timer.interval = max(settings.live_interval_seconds, 1.0)
        if live_toggle.value:
            live_timer.activate()
            ui.notify(f"Live generation every {live_timer.interval:g}s", color="positive")
        else:
            live_timer.deactivate()
            ui.notify("Live generation stopped")

    def live_interval_changed() -> None:
        pull_settings_from_fields()
        live_timer.interval = max(settings.live_interval_seconds, 1.0)
        save_gui_settings(settings)

    with ui.column().classes("oracle-shell w-full gap-2 p-3"):
        with ui.row().classes("w-full items-center justify-between"):
            ui.label("THE ORACLE OPERATOR").classes("oracle-title text-lg")
            with ui.row().classes("items-center gap-2"):
                mode_label = ui.label("-").classes("text-xs font-bold")
                transport_label = ui.label("-").classes("text-xs font-bold")
                ui.button("START PRINT", on_click=start_print).props("dense color=positive")
                ui.button("STOP AFTER SHEET", on_click=stop_print).props("dense color=warning")
                ui.label("capacity").classes("text-xs text-[#8f4f2b]")
                capacity_label = ui.label("-").classes("text-sm font-bold")

        with ui.card().classes("oracle-card compact-card w-full"):
            with ui.row().classes("w-full items-end gap-2"):
                fields["run_mode"] = ui.select(
                    {"test": "TEST MODE", "exhibition": "EXHIBITION MODE"},
                    value=settings.run_mode,
                    label="Work mode",
                ).props("dense outlined").classes("w-44").on_value_change(update_control_mode)
                fields["transport_mode"] = ui.select(
                    {"dry_run": "DRY RUN", "real": "REAL FLUIDNC"},
                    value="dry_run" if settings.dry_run else "real",
                    label="Output",
                ).props("dense outlined").classes("w-40").on_value_change(update_control_mode)
                fields["layout_mode"] = ui.select(["hex", "grid"], value=settings.layout_mode, label="Layout").props("dense outlined").classes("w-28").on_value_change(persist_and_refresh)
                fields["sheet_width_mm"] = ui.number("Field W mm", value=settings.sheet_width_mm, min=1).props("dense outlined").classes("w-28").on_value_change(persist_and_refresh)
                fields["sheet_height_mm"] = ui.number("Field H mm", value=settings.sheet_height_mm, min=1).props("dense outlined").classes("w-28").on_value_change(persist_and_refresh)
                fields["cell_diameter_mm"] = ui.number("Cell diameter mm", value=settings.cell_diameter_mm, min=1).props("dense outlined").classes("w-36").on_value_change(persist_and_refresh)
                fields["gap_mm"] = ui.number("Gap mm", value=settings.gap_mm, min=0).props("dense outlined").classes("w-24").on_value_change(persist_and_refresh)
                fields["sheet_margin_mm"] = ui.number("Margin mm", value=settings.sheet_margin_mm, min=0).props("dense outlined").classes("w-28").on_value_change(persist_and_refresh)
                fields["include_rings"] = ui.switch("Rings", value=settings.include_rings).on_value_change(persist_and_refresh)

        with ui.grid(columns="330px 1fr 330px").classes("w-full gap-2 min-h-0"):
            with ui.column().classes("gap-2 min-h-0"):
                with ui.column().classes("gap-2 w-full") as test_panel:
                    with ui.card().classes("oracle-card compact-card w-full"):
                        ui.label("Test User Queue").classes("text-sm font-bold")
                        symbol_options = {"__cycle__": "ALL 8 / cycle one-by-one"}
                        symbol_options.update({symbol.name: symbol.stem for symbol in symbols})
                        fields["selected_symbol"] = ui.select(
                            symbol_options,
                            value=settings.selected_symbol,
                            label="Base symbol mode",
                        ).props("dense outlined").classes("w-full")
                        with ui.row().classes("items-end gap-2"):
                            fields["user_count"] = ui.number("Count", value=settings.user_count, min=1, step=1).props("dense outlined").classes("w-20")
                            fields["live_interval_seconds"] = ui.number("Live sec", value=settings.live_interval_seconds, min=1).props("dense outlined").classes("w-24").on_value_change(live_interval_changed)
                        with ui.row().classes("items-center gap-2"):
                            ui.label("Randomness").classes("text-xs text-[#8f4f2b]")
                            fields["randomness"] = ui.slider(min=0, max=100, step=1, value=settings.randomness).props("label label-always").classes("w-64").on_value_change(persist_and_refresh)
                        with ui.row().classes("items-center gap-2"):
                            ui.label("Fine randomness").classes("text-xs text-[#8f4f2b]")
                            fields["randomness_fine"] = ui.slider(min=-10, max=10, step=0.1, value=settings.randomness_fine).props("label label-always dense").classes("w-48").on_value_change(persist_and_refresh)
                        ui.label("Randomness = coarse + fine; affects generated test symbols only.").classes("text-xs text-[#8f4f2b]")
                        with ui.row().classes("items-center gap-2"):
                            ui.button("Generate", on_click=generate_user_sessions).props("dense")
                            ui.button("Generate ALL 8", on_click=generate_all_user_symbols).props("dense")
                            live_toggle = ui.switch("Live", value=False, on_change=toggle_live)
                        last_user_output = ui.label("-").classes("path-label text-xs")

                    with ui.card().classes("oracle-card compact-card w-full"):
                        ui.label("Filler Bank").classes("text-sm font-bold")
                        with ui.row().classes("items-end gap-2"):
                            fields["idle_variations_per_symbol"] = ui.number(
                                "Variations/base",
                                value=settings.idle_variations_per_symbol,
                                min=1,
                                step=1,
                            ).props("dense outlined").classes("w-36")
                            ui.button("Generate filler", on_click=generate_idle_bank).props("dense")
                        idle_output = ui.label(str(default_idle_root())).classes("path-label text-xs")

                with ui.card().classes("oracle-card compact-card w-full"):
                    ui.label("Plotter").classes("text-sm font-bold")
                    for key, title in [
                        ("status", "status"),
                        ("current_sheet_id", "sheet"),
                        ("processed_symbols", "symbols"),
                        ("user_count", "user"),
                        ("idle_count", "idle"),
                        ("pending_reload", "reload"),
                    ]:
                        with ui.row().classes("w-full justify-between gap-2"):
                            ui.label(title).classes("text-xs text-[#8f4f2b]")
                            status_labels[key] = ui.label("-").classes("path-label text-xs font-bold")
                    for key, title in [
                        ("print_enabled", "print enabled"),
                        ("run_mode", "mode"),
                        ("dry_run", "dry-run"),
                    ]:
                        with ui.row().classes("w-full justify-between gap-2"):
                            ui.label(title).classes("text-xs text-[#8f4f2b]")
                            control_labels[key] = ui.label("-").classes("path-label text-xs font-bold")
                    status_labels["message"] = ui.label("-").classes("path-label text-xs")
                    status_labels["last_sheet_path"] = ui.label("-").classes("path-label text-xs")
                    status_labels["latest_manifest"] = ui.label("-").classes("hidden")
                    progress = ui.linear_progress(value=0).classes("w-full")
                    with ui.row().classes("gap-1"):
                        ui.button("Refresh", on_click=refresh_status).props("dense")
                        reload_button = ui.button("Reload OK", on_click=confirm_reload).props("dense")
                        ui.button("Dry-run", on_click=generate_dry_run).props("dense")
                        ui.button("Spool", on_click=open_spool).props("dense")

            with ui.card().classes("oracle-card compact-card w-full min-h-0"):
                with ui.row().classes("w-full items-center justify-between"):
                    ui.label("Sheet Preview").classes("text-sm font-bold")
                    ui.label("static layout only").classes("text-xs text-[#8f4f2b]")
                preview = ui.html().classes("preview-frame w-full")

            with ui.card().classes("oracle-card compact-card w-full"):
                with ui.expansion("Symbol scale correction", icon="graphic_eq", value=False).classes("w-full"):
                    fields["global_scale"] = ui.slider(min=0.3, max=1.5, step=0.01, value=settings.global_scale).props("label label-always").classes("w-full").on_value_change(persist_and_refresh)
                    ui.label(f"Config: {default_scale_config_path()}").classes("path-label text-xs")
                    with ui.grid(columns=2).classes("w-full gap-2"):
                        for symbol in symbols:
                            with ui.column().classes("gap-0"):
                                symbol_previews[symbol.name] = ui.html().classes("symbol-preview")
                                ui.label(symbol.stem[:22]).classes("text-[10px]")
                                fields[f"scale:{symbol.name}"] = ui.slider(
                                    min=0.3,
                                    max=1.5,
                                    step=0.01,
                                    value=scales.get(symbol.name, 1.0),
                                ).props("dense label label-always")
                    ui.button("Save scales", on_click=save_scales_from_fields).props("dense")
                ui.separator()
                ui.label("Scale controls are collapsed by default to keep the dashboard fitting on a 14-inch screen.").classes("text-xs text-[#8f4f2b]")

    live_timer = ui.timer(settings.live_interval_seconds, generate_user_sessions, active=False)
    ui.timer(2.0, refresh_status)
    persist_and_refresh()


def main() -> None:
    ui.page("/")(build_page)
    host = os.getenv("NEJE_GUI_HOST", "127.0.0.1")
    port = int(os.getenv("NEJE_GUI_PORT", "8787"))
    ui.run(host=host, port=port, reload=False, title="Oracle Operator")


if __name__ == "__main__":
    main()
