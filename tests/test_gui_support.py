from __future__ import annotations

import json
from pathlib import Path

from neje_oracle.config import PlotterSettings
from neje_oracle.gui_support import (
    GuiSettings,
    build_preview_svg,
    confirm_plotter_reload,
    create_idle_bank_from_gui,
    create_user_sessions_from_gui,
    generate_dry_run_sheet,
    layout_capacity,
    load_gui_settings,
    load_symbol_scales,
    read_plotter_status,
    save_gui_settings,
    save_symbol_scales,
)
from neje_oracle.models import PlotterRuntimeState, RuntimeStatus
from neje_oracle.store import PlotterStore


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
    assert settings.gap_mm == 0
    assert not hasattr(settings, "mark_diameter_mm")
    assert not hasattr(settings, "sheet_capacity")
    settings.layout_mode = "grid"
    save_gui_settings(settings, settings_path)

    reloaded = load_gui_settings(settings_path)

    assert reloaded.layout_mode == "grid"


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

    assert effective_randomness(GuiSettings(randomness=20, randomness_fine=2.5)) == 22.5
    assert effective_randomness(GuiSettings(randomness=98, randomness_fine=10)) == 100
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
    assert idle_svgs[0].read_text(encoding="utf-8").count("<circle") == 2


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
    assert not db_path.exists()


def test_confirm_reload_updates_runtime_state(tmp_path: Path) -> None:
    db_path = tmp_path / "runtime" / "plotter.sqlite3"
    store = PlotterStore(db_path)
    store.save_runtime_state(
        PlotterRuntimeState(
            status=RuntimeStatus.PAUSED,
            message="Waiting",
            pending_reload=True,
        )
    )

    confirm_plotter_reload(db_path)
    status = read_plotter_status(db_path=db_path, spool_root=tmp_path / "spool")

    assert status["status"] == RuntimeStatus.IDLE.value
    assert status["pending_reload"] is False
