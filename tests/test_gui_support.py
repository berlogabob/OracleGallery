from __future__ import annotations

import json
from pathlib import Path

from neje_oracle.config import PlotterSettings
from neje_oracle.gui_support import (
    GUI_DEFAULTS,
    GuiSettings,
    build_preview_svg,
    build_realtime_preview_svg,
    confirm_plotter_reload,
    create_idle_bank_from_gui,
    create_filler_packages_from_gui,
    create_next_filler_upload_from_gui,
    create_user_sessions_from_gui,
    generate_dry_run_sheet,
    layout_capacity,
    load_gui_settings,
    load_symbol_scales,
    read_plotter_status,
    save_gui_settings,
    save_symbol_scales,
)
from neje_oracle.models import PlotterControlState, PlotterRuntimeState, RuntimeStatus, SystemMode
from neje_oracle.store import OracleRuntimeStore, PlotterStore


SIMPLE_SYMBOL = (
    "<svg width='800' height='800' xmlns='http://www.w3.org/2000/svg'>"
    "<g fill='none' stroke='black'>"
    "<polyline points='100,100 700,100 700,700 100,700'/>"
    "</g>"
    "</svg>"
)


def _symbol_root(tmp_path: Path) -> Path:
    root = tmp_path / "symbols"
    root.mkdir()
    for index in range(2):
        (root / f"symbol_{index}.svg").write_text(SIMPLE_SYMBOL, encoding="utf-8")
    return root


def test_gui_settings_load_save_handles_missing_file(tmp_path: Path) -> None:
    settings_path = tmp_path / "runtime" / "gui_settings.json"
    settings = load_gui_settings(settings_path, PlotterSettings(sheet_width_mm=300, sheet_height_mm=200))
    assert settings.sheet_width_mm == 300
    assert settings.system_mode == GUI_DEFAULTS["system_mode"]
    assert settings.gap_mm == 0
    assert not hasattr(settings, "mark_diameter_mm")
    assert not hasattr(settings, "sheet_capacity")
    settings.layout_mode = "grid"
    save_gui_settings(settings, settings_path)

    reloaded = load_gui_settings(settings_path)

    assert reloaded.layout_mode == "grid"


def test_gui_settings_migrates_old_run_mode_to_system_mode(tmp_path: Path) -> None:
    settings_path = tmp_path / "runtime" / "gui_settings.json"
    settings_path.parent.mkdir(parents=True)
    settings_path.write_text('{"run_mode": "exhibition", "dry_run": false}', encoding="utf-8")

    settings = load_gui_settings(settings_path)

    assert settings.system_mode == SystemMode.EXHIBITION_REAL.value
    assert settings.run_mode == "exhibition"
    assert settings.dry_run is False


def test_symbol_scales_load_save(tmp_path: Path) -> None:
    root = _symbol_root(tmp_path)
    scale_path = tmp_path / "symbol_scales.json"
    save_symbol_scales({"symbol_0.svg": 0.75, "symbol_1.svg": 1.2}, scale_path, root)

    scales = load_symbol_scales(scale_path, root)

    assert scales == {"symbol_0.svg": 0.75, "symbol_1.svg": 1.2}
    assert json.loads(scale_path.read_text(encoding="utf-8"))["symbol_1.svg"] == 1.2


def test_preview_svg_builds_hex_and_grid() -> None:
    settings = GuiSettings(sheet_width_mm=300, sheet_height_mm=220, cell_diameter_mm=80)

    hex_preview = build_preview_svg(settings)
    settings.layout_mode = "grid"
    grid_preview = build_preview_svg(settings)

    assert "<svg" in hex_preview
    assert "<svg" in grid_preview
    assert hex_preview.count("<circle") >= 4
    assert grid_preview.count("<circle") >= 4


def test_gap_changes_layout_capacity() -> None:
    tight = GuiSettings(sheet_width_mm=250, sheet_height_mm=440, cell_diameter_mm=80, gap_mm=0)
    loose = GuiSettings(sheet_width_mm=250, sheet_height_mm=440, cell_diameter_mm=80, gap_mm=20)

    assert layout_capacity(loose) < layout_capacity(tight)


def test_preview_svg_shows_mark_size_and_embedded_symbols(tmp_path: Path) -> None:
    root = _symbol_root(tmp_path)
    scale_path = tmp_path / "symbol_scales.json"
    save_symbol_scales({"symbol_0.svg": 1.0, "symbol_1.svg": 1.0}, scale_path, root)
    settings = GuiSettings(sheet_width_mm=300, sheet_height_mm=220, cell_diameter_mm=80)

    preview = build_preview_svg(settings, symbol_root=root, scale_path=scale_path)

    assert "data:image/svg+xml;base64" in preview
    assert preview.count("<image") == layout_capacity(settings)


def test_preview_rings_toggle_changes_sheet_preview() -> None:
    settings = GuiSettings(sheet_width_mm=300, sheet_height_mm=220, cell_diameter_mm=80, include_rings=True)

    with_rings = build_preview_svg(settings)
    settings.include_rings = False
    without_rings = build_preview_svg(settings)

    assert 'data-ring="outer"' in with_rings
    assert 'data-ring="inner"' in with_rings
    assert 'data-ring="outer"' not in without_rings
    assert 'data-ring="inner"' not in without_rings


def test_preview_origin_markers_toggle_and_filter() -> None:
    settings = GuiSettings(sheet_width_mm=300, sheet_height_mm=220, cell_diameter_mm=80, include_markers=True)

    with_markers = build_preview_svg(settings)
    settings.include_markers = False
    without_markers = build_preview_svg(settings)
    settings.include_markers = True
    settings.show_origins = ["test_macbook"]
    user_only = build_preview_svg(settings)

    assert 'data-origin-marker="test_macbook"' in with_markers
    assert 'data-origin-marker="filler_macbook"' in with_markers
    assert "data-origin-marker" not in without_markers
    assert 'data-origin-marker="test_macbook"' in user_only
    assert 'data-origin-marker="filler_macbook"' not in user_only


def test_realtime_preview_shows_drawn_current_and_next_from_manifest(tmp_path: Path) -> None:
    root = _symbol_root(tmp_path)
    manifest = tmp_path / "spool" / "sheet.json"
    manifest.parent.mkdir()
    manifest.write_text(
        json.dumps(
            {
                "items": [
                    {
                        "session_id": "done",
                        "source_kind": "user",
                        "origin": "real_macmini",
                        "svg_path": str(root / "symbol_0.svg"),
                        "sheet_index": 0,
                    },
                    {
                        "session_id": "drawing",
                        "source_kind": "user",
                        "origin": "real_macmini",
                        "svg_path": str(root / "symbol_1.svg"),
                        "sheet_index": 1,
                    },
                    {
                        "session_id": "next",
                        "source_kind": "placeholder",
                        "origin": "filler_macbook",
                        "svg_path": str(root / "symbol_0.svg"),
                        "sheet_index": 2,
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    settings = GuiSettings(sheet_width_mm=300, sheet_height_mm=220, cell_diameter_mm=80)
    status = {
        "latest_manifest": str(manifest),
        "status": RuntimeStatus.PRINTING.value,
        "cells_completed": 1,
        "current_cell_in_row": 2,
    }

    preview = build_realtime_preview_svg(settings, status, {"pendingAfterBaseline": 0})

    assert 'data-preview-state="drawn"' in preview
    assert 'data-preview-state="drawing"' in preview
    assert 'data-preview-state="next"' in preview
    assert preview.count("data:image/svg+xml;base64") == 3


def test_realtime_preview_uses_queue_before_filler_for_unmaterialized_next(tmp_path: Path) -> None:
    root = _symbol_root(tmp_path)
    manifest = tmp_path / "spool" / "sheet.json"
    manifest.parent.mkdir()
    manifest.write_text(
        json.dumps(
            {
                "items": [
                    {
                        "session_id": "drawing",
                        "source_kind": "user",
                        "origin": "real_macmini",
                        "svg_path": str(root / "symbol_0.svg"),
                        "sheet_index": 0,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    settings = GuiSettings(sheet_width_mm=300, sheet_height_mm=220, cell_diameter_mm=80)
    status = {
        "latest_manifest": str(manifest),
        "status": RuntimeStatus.PRINTING.value,
        "cells_completed": 0,
        "current_cell_in_row": 1,
    }

    queued_preview = build_realtime_preview_svg(settings, status, {"pendingAfterBaseline": 1})
    filler_queue_preview = build_realtime_preview_svg(
        settings,
        status,
        {"pendingAfterBaseline": 1, "pendingUserAfterBaseline": 0, "pendingFillerAfterBaseline": 1},
    )
    filler_preview = build_realtime_preview_svg(settings, status, {"pendingAfterBaseline": 0})

    assert 'data-preview-state="next"' in queued_preview
    assert 'data-origin-marker="real_macmini"' in queued_preview
    assert 'data-origin-marker="filler_macbook"' in filler_queue_preview
    assert 'data-origin-marker="filler_macbook"' in filler_preview


def test_symbol_preview_randomness_visibly_changes_svg(tmp_path: Path) -> None:
    from neje_oracle.gui_support import build_symbol_preview_svg

    root = _symbol_root(tmp_path)
    stable = build_symbol_preview_svg(
        root / "symbol_0.svg",
        marker_kind="user",
        scale=1.0,
        include_rings=False,
        randomness=0,
    )
    rough = build_symbol_preview_svg(
        root / "symbol_0.svg",
        marker_kind="user",
        scale=1.0,
        include_rings=False,
        randomness=100,
    )

    assert stable != rough
    assert "100,100 700,100 700,700 100,700" in stable
    assert "100,100 700,100 700,700 100,700" not in rough


def test_effective_randomness_combines_coarse_and_fine() -> None:
    from neje_oracle.gui_support import effective_randomness

    assert effective_randomness(GuiSettings(randomness=20, randomness_fine=2.5)) == 12.5
    assert effective_randomness(GuiSettings(randomness=98, randomness_fine=10)) == 59
    assert effective_randomness(GuiSettings(randomness=2, randomness_fine=-10)) == 0


def test_gui_user_and_idle_generation_helpers(tmp_path: Path) -> None:
    root = _symbol_root(tmp_path)
    scale_path = tmp_path / "symbol_scales.json"
    save_symbol_scales({"symbol_0.svg": 1.0, "symbol_1.svg": 1.0}, scale_path, root)
    settings = GuiSettings(
        user_count=1,
        idle_count=2,
        idle_variations_per_symbol=1,
        selected_symbol="symbol_0.svg",
        randomness=0,
    )

    user_dirs = create_user_sessions_from_gui(settings, output_root=tmp_path / "sessions", symbol_root=root, scale_path=scale_path)
    idle_svgs = create_idle_bank_from_gui(settings, output_root=tmp_path / "idle", symbol_root=root, scale_path=scale_path)

    assert (user_dirs[0] / f"{user_dirs[0].name}_plotter.svg").exists()
    assert (user_dirs[0] / "READY").exists()
    assert len(idle_svgs) == 2
    assert idle_svgs[0].read_text(encoding="utf-8").count("<circle") == 0


def test_gui_cycle_start_index_advances_selected_base_symbol(tmp_path: Path) -> None:
    root = _symbol_root(tmp_path)
    scale_path = tmp_path / "symbol_scales.json"
    save_symbol_scales({"symbol_0.svg": 1.0, "symbol_1.svg": 1.0}, scale_path, root)
    settings = GuiSettings(user_count=1, selected_symbol="__cycle__", randomness=0)

    first = create_user_sessions_from_gui(
        settings,
        output_root=tmp_path / "sessions",
        symbol_root=root,
        scale_path=scale_path,
        start_index=0,
    )[0]
    second = create_user_sessions_from_gui(
        settings,
        output_root=tmp_path / "sessions",
        symbol_root=root,
        scale_path=scale_path,
        start_index=1,
    )[0]

    assert json.loads((first / "metadata.json").read_text(encoding="utf-8"))["baseSymbol"] == "symbol_0.svg"
    assert json.loads((second / "metadata.json").read_text(encoding="utf-8"))["baseSymbol"] == "symbol_1.svg"


def test_idle_variations_per_symbol_generates_more_than_base_bank(tmp_path: Path) -> None:
    root = _symbol_root(tmp_path)
    scale_path = tmp_path / "symbol_scales.json"
    save_symbol_scales({"symbol_0.svg": 1.0, "symbol_1.svg": 1.0}, scale_path, root)
    settings = GuiSettings(idle_count=1, idle_variations_per_symbol=3, randomness=0)

    idle_svgs = create_idle_bank_from_gui(settings, output_root=tmp_path / "idle", symbol_root=root, scale_path=scale_path)

    assert len(idle_svgs) == 6
    assert [path.name for path in idle_svgs][:4] == [
        "idle_01_symbol_0.svg",
        "idle_02_symbol_1.svg",
        "idle_03_symbol_0.svg",
        "idle_04_symbol_1.svg",
    ]


def test_idle_generation_clears_stale_svg_files(tmp_path: Path) -> None:
    root = _symbol_root(tmp_path)
    output_root = tmp_path / "idle"
    output_root.mkdir()
    (output_root / "stale.svg").write_text(SIMPLE_SYMBOL, encoding="utf-8")
    settings = GuiSettings(idle_count=1, idle_variations_per_symbol=1, randomness=0)

    idle_svgs = create_idle_bank_from_gui(settings, output_root=output_root, symbol_root=root)

    assert len(idle_svgs) == 2
    assert not (output_root / "stale.svg").exists()


def test_filler_package_generation_uses_session_folder_shape(tmp_path: Path) -> None:
    root = _symbol_root(tmp_path)
    output_root = tmp_path / "filler"
    settings = GuiSettings(idle_count=1, idle_variations_per_symbol=1, randomness=0)

    filler_dirs = create_filler_packages_from_gui(settings, output_root=output_root, symbol_root=root)

    assert len(filler_dirs) == 2
    first = filler_dirs[0]
    assert first.name.startswith("filler_")
    assert (first / f"{first.name}_plotter.svg").exists()
    assert (first / f"{first.name}_receipt.txt").exists()
    assert (first / "metadata.json").exists()
    assert (first / "READY").exists()


def test_next_filler_upload_uses_uploader_session_shape_and_tags(tmp_path: Path) -> None:
    root = _symbol_root(tmp_path)
    output_root = tmp_path / "sessions"
    settings = GuiSettings(idle_count=1, idle_variations_per_symbol=1, randomness=0)

    filler_dirs = create_next_filler_upload_from_gui(settings, output_root=output_root, symbol_root=root)

    assert len(filler_dirs) == 1
    first = filler_dirs[0]
    metadata = json.loads((first / "metadata.json").read_text(encoding="utf-8"))
    assert first.parent == output_root
    assert first.name.startswith("filler_")
    assert (first / f"{first.name}_plotter.svg").exists()
    assert (first / f"{first.name}_receipt.txt").exists()
    assert (first / "READY").exists()
    assert metadata["origin"] == "filler_macbook"
    assert metadata["tags"] == ["filler", "local", "macbook"]
    assert metadata["visibleInLibrary"] is False
    assert metadata["uploadToFirebase"] is True
    assert metadata["queue"] == "filler"
    assert metadata["priority"] == "filler"


def test_dry_run_sheet_and_status_helpers(tmp_path: Path) -> None:
    root = _symbol_root(tmp_path)
    settings = GuiSettings(sheet_width_mm=300, sheet_height_mm=220, cell_diameter_mm=80)

    output = generate_dry_run_sheet(settings, spool_root=tmp_path / "spool", symbol_root=root)

    assert output["gcode"].exists()
    assert output["manifest"].exists()


def test_read_status_does_not_create_runtime_db(tmp_path: Path) -> None:
    db_path = tmp_path / "runtime" / "plotter.sqlite3"

    status = read_plotter_status(db_path=db_path, spool_root=tmp_path / "spool")

    assert status["status"] == "daemon_not_started"
    assert status["gcode_progress_percent"] == 0.0
    assert not db_path.exists()


def test_confirm_reload_updates_runtime_state(tmp_path: Path) -> None:
    db_path = tmp_path / "runtime" / "plotter.sqlite3"
    oracle_db_path = tmp_path / "runtime" / "oracle.sqlite3"
    store = PlotterStore(db_path)
    store.save_runtime_state(
        PlotterRuntimeState(
            status=RuntimeStatus.PAUSED,
            message="Waiting",
            pending_reload=True,
        )
    )

    confirm_plotter_reload(db_path, oracle_db_path=oracle_db_path)
    status = read_plotter_status(db_path=db_path, spool_root=tmp_path / "spool")

    assert status["status"] == RuntimeStatus.IDLE.value
    assert status["pending_reload"] is False


def test_confirm_reload_pauses_dry_run_to_avoid_immediate_reload_loop(tmp_path: Path) -> None:
    db_path = tmp_path / "runtime" / "plotter.sqlite3"
    oracle_db_path = tmp_path / "runtime" / "oracle.sqlite3"
    store = PlotterStore(db_path)
    oracle_store = OracleRuntimeStore(oracle_db_path)
    control = PlotterControlState(print_enabled=True, operator_paused=False, run_mode="exhibition", dry_run=True)
    store.save_control_state(control)
    oracle_store.save_print_control(control)
    store.save_runtime_state(
        PlotterRuntimeState(
            status=RuntimeStatus.PAUSED,
            message="Waiting",
            pending_reload=True,
        )
    )

    assert confirm_plotter_reload(db_path, oracle_db_path=oracle_db_path) is True

    plotter_control = store.load_control_state()
    oracle_control = oracle_store.load_print_control()
    assert plotter_control.print_enabled is False
    assert plotter_control.operator_paused is True
    assert oracle_control.print_enabled is False
    assert oracle_control.operator_paused is True


def test_confirm_reload_keeps_real_print_enabled_for_next_sheet(tmp_path: Path) -> None:
    db_path = tmp_path / "runtime" / "plotter.sqlite3"
    oracle_db_path = tmp_path / "runtime" / "oracle.sqlite3"
    store = PlotterStore(db_path)
    oracle_store = OracleRuntimeStore(oracle_db_path)
    control = PlotterControlState(print_enabled=True, operator_paused=False, run_mode="exhibition", dry_run=False)
    store.save_control_state(control)
    oracle_store.save_print_control(control)
    store.save_runtime_state(
        PlotterRuntimeState(
            status=RuntimeStatus.PAUSED,
            message="Waiting",
            pending_reload=True,
        )
    )

    assert confirm_plotter_reload(db_path, oracle_db_path=oracle_db_path) is True

    assert store.load_control_state().print_enabled is True
    assert oracle_store.load_print_control().print_enabled is True


def test_compute_effective_sample_step_defaults_to_sample_step_at_ref_diameter():
    from neje_oracle.gui_support import compute_effective_sample_step as fn
    result = fn(
        sample_step_mm=1.0,
        cell_diameter_mm=80.0,
        sample_reference_cell_mm=80.0,
        sample_density_exponent=1.0,
        sample_min_step_mm=0.25,
        sample_max_step_mm=3.0,
    )
    assert result == 1.0


def test_compute_effective_sample_step_bigger_cell_denser_gcode():
    from neje_oracle.gui_support import compute_effective_sample_step as fn
    ref_result = fn(
        sample_step_mm=1.0,
        cell_diameter_mm=80.0,
        sample_reference_cell_mm=80.0,
        sample_density_exponent=1.0,
        sample_min_step_mm=0.25,
        sample_max_step_mm=3.0,
    )
    big_result = fn(
        sample_step_mm=1.0,
        cell_diameter_mm=160.0,
        sample_reference_cell_mm=80.0,
        sample_density_exponent=1.0,
        sample_min_step_mm=0.25,
        sample_max_step_mm=3.0,
    )
    assert big_result < ref_result  # 160 mm cell → denser (smaller spacing)
    assert abs(big_result - 0.5) < 1e-9  # exactly half


def test_compute_effective_sample_step_clamps_to_min():
    from neje_oracle.gui_support import compute_effective_sample_step as fn
    result = fn(
        sample_step_mm=0.1,
        cell_diameter_mm=200.0,
        sample_reference_cell_mm=80.0,
        sample_density_exponent=1.0,
        sample_min_step_mm=0.25,
        sample_max_step_mm=3.0,
    )
    assert result == 0.25  # 0.1 * (80/200) = 0.04, clamped to 0.25


def test_compute_effective_sample_step_clamps_to_max():
    from neje_oracle.gui_support import compute_effective_sample_step as fn
    result = fn(
        sample_step_mm=5.0,
        cell_diameter_mm=20.0,
        sample_reference_cell_mm=80.0,
        sample_density_exponent=1.0,
        sample_min_step_mm=0.25,
        sample_max_step_mm=3.0,
    )
    assert result == 3.0  # 5 * (80/20) = 20, clamped to 3.0


def test_gui_optimisation_settings_persist_and_load(tmp_path: Path):
    from neje_oracle.gui_support import GuiSettings, load_gui_settings, save_gui_settings
    settings_path = tmp_path / "gui_settings.json"
    settings = GuiSettings(
        cell_diameter_mm=160.0,
        sample_step_mm=0.5,
        sample_reference_cell_mm=80.0,
        sample_density_exponent=1.5,
        sample_min_step_mm=0.1,
        sample_max_step_mm=5.0,
        streaming_mode="row",
    )
    save_gui_settings(settings, settings_path)
    loaded = load_gui_settings(settings_path)
    assert loaded.sample_step_mm == 0.5
    assert loaded.sample_reference_cell_mm == 80.0
    assert loaded.sample_density_exponent == 1.5
    assert loaded.sample_min_step_mm == 0.1
    assert loaded.sample_max_step_mm == 5.0
    assert loaded.streaming_mode == "row"


def test_gui_settings_to_plotter_config_carries_optimisation(tmp_path: Path):
    from neje_oracle.gui_support import GuiSettings, gui_settings_to_plotter_config
    from neje_oracle.models import PlotterRuntimeConfig
    settings = GuiSettings(
        cell_diameter_mm=160.0,
        sample_step_mm=0.5,
        sample_reference_cell_mm=80.0,
        sample_density_exponent=1.5,
        sample_min_step_mm=0.1,
        sample_max_step_mm=5.0,
        streaming_mode="cell",
    )
    config = gui_settings_to_plotter_config(settings)
    assert isinstance(config, PlotterRuntimeConfig)
    assert config.sample_step_mm == 0.5
    assert config.sample_reference_cell_mm == 80.0
    assert config.sample_density_exponent == 1.5
    assert config.sample_min_step_mm == 0.1
    assert config.sample_max_step_mm == 5.0
    assert config.streaming_mode == "cell"


def test_dry_run_manifest_includes_optimisation_settings(tmp_path: Path):
    from neje_oracle.gui_support import (
        GuiSettings, generate_dry_run_sheet, latest_spool_manifest,
        compute_effective_sample_step,
    )
    symbol_root = tmp_path / "symbols"
    symbol_root.mkdir()
    (symbol_root / "s.svg").write_text(
        "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'>"
        "<path d='M10,10 L90,10 L90,90 Z' stroke='black' fill='none'/></svg>",
        encoding="utf-8",
    )
    settings = GuiSettings(
        sheet_width_mm=120.0, sheet_height_mm=120.0, cell_diameter_mm=40.0,
        sample_step_mm=2.0, sample_density_exponent=2.0,
    )
    spool_root = tmp_path / "spool"
    result = generate_dry_run_sheet(settings, spool_root=spool_root, symbol_root=symbol_root)
    manifest_path = result["manifest"]
    payload = json.loads(manifest_path.read_text())
    assert "sample_step_mm" in payload
    assert payload["sample_step_mm"] == 2.0
    assert "sample_reference_cell_mm" in payload
    assert "sample_density_exponent" in payload
    assert "sample_min_step_mm" in payload
    assert "sample_max_step_mm" in payload
    assert "effective_sample_step_mm" in payload
    assert payload["streaming_mode"] == settings.streaming_mode
    # 40mm cell < 80mm ref: effective = 2 * (80/40)^2 = 8.0, clamped to max 3.0
    assert payload["effective_sample_step_mm"] > 2.0  # smaller cell → lighter = more spacing


def test_batch_generation_controls_are_not_operator_facing() -> None:
    source = Path("src/neje_oracle/gui_service.py").read_text(encoding="utf-8")
    work_panel = source.split("with ui.tab_panel(work_tab)", 1)[1].split("with ui.tab_panel(exhibition_tab)", 1)[0]
    exhibition_panel = source.split("with ui.tab_panel(exhibition_tab)", 1)[1]
    assert "Generate next filler" not in work_panel
    assert "Generate next filler" not in exhibition_panel
    assert "START GENERATOR" not in work_panel
    assert "START GENERATOR" not in exhibition_panel
