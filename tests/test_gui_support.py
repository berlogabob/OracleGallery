from __future__ import annotations

import asyncio
import json
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

import pytest
from nicegui.elements.upload_files import SmallFileUpload

from neje_oracle.blocks.gui import support as gui_support
from neje_oracle.blocks.gui.support import (
    GUI_DEFAULTS,
    PREVIEW_PX_PER_MM,
    GuiSettings,
    _field_or_default,
    build_preview_svg,
    build_realtime_preview_svg,
    create_direct_svg_print_job_from_gui,
    generate_dry_run_sheet,
    layout_capacity,
    load_gui_settings,
    load_symbol_scales,
    read_plotter_status,
    read_upload_content_bytes,
    read_upload_event_payload,
    save_gui_settings,
    save_symbol_scales,
)
from neje_oracle.shared.config import PlotterSettings
from neje_oracle.shared.models import RuntimeStatus, SystemMode

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


def test_field_or_default_uses_gui_defaults_for_cleared_fields() -> None:
    expected_defaults = {
        "cell_diameter_mm": 80.0,
        "sheet_width_mm": 250.0,
        "sheet_height_mm": 440.0,
        "randomness": 35.0,
    }

    for key, expected in expected_defaults.items():
        assert _field_or_default({key: SimpleNamespace(value=None)}, key) == GUI_DEFAULTS[key] == expected
    assert GuiSettings().dry_run is False


def test_gui_settings_load_save_handles_missing_file(tmp_path: Path) -> None:
    settings_path = tmp_path / "runtime" / "gui_settings.json"
    settings = load_gui_settings(settings_path)
    assert settings.sheet_width_mm == GUI_DEFAULTS["sheet_width_mm"]
    assert settings.system_mode == GUI_DEFAULTS["system_mode"]
    assert settings.gap_mm == 0
    assert settings.streaming_mode == "row"
    assert not hasattr(settings, "mark_diameter_mm")
    assert not hasattr(settings, "sheet_capacity")
    settings.layout_mode = "grid"
    save_gui_settings(settings, settings_path)

    reloaded = load_gui_settings(settings_path)

    assert reloaded.layout_mode == "grid"


def test_gui_settings_preserves_saved_cell_streaming(tmp_path: Path) -> None:
    settings_path = tmp_path / "runtime" / "gui_settings.json"
    settings_path.parent.mkdir(parents=True)
    settings_path.write_text('{"streaming_mode": "cell"}', encoding="utf-8")

    settings = load_gui_settings(settings_path)

    assert settings.streaming_mode == "cell"


def test_gui_settings_migrates_old_run_mode_to_system_mode(tmp_path: Path) -> None:
    settings_path = tmp_path / "runtime" / "gui_settings.json"
    settings_path.parent.mkdir(parents=True)
    settings_path.write_text('{"run_mode": "exhibition", "dry_run": false}', encoding="utf-8")

    settings = load_gui_settings(settings_path)

    assert settings.system_mode == SystemMode.EXHIBITION.value
    assert settings.run_mode == "exhibition"
    assert settings.dry_run is False


def test_gui_settings_normalizes_legacy_exhibition_modes(tmp_path: Path) -> None:
    for legacy_mode in ("exhibition_dry", "exhibition_real"):
        settings_path = tmp_path / f"{legacy_mode}.json"
        settings_path.write_text(f'{{"system_mode": "{legacy_mode}"}}', encoding="utf-8")

        settings = load_gui_settings(settings_path)

        assert settings.system_mode == SystemMode.EXHIBITION.value
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


def test_preview_svg_keeps_large_sheet_intrinsic_size_for_scrolling() -> None:
    settings = GuiSettings(sheet_width_mm=1200, sheet_height_mm=800, cell_diameter_mm=80)

    preview = build_preview_svg(settings)

    assert 'viewBox="0 0 2400.00 1600.00"' in preview
    assert 'width="2400" height="1600"' in preview


def test_preview_symbol_scale_is_not_applied_to_image_viewport_twice(tmp_path: Path) -> None:
    root = _symbol_root(tmp_path)
    scale_path = tmp_path / "symbol_scales.json"
    save_symbol_scales({"symbol_0.svg": 2.0, "symbol_1.svg": 2.0}, scale_path, root)
    settings = GuiSettings(sheet_width_mm=90, sheet_height_mm=90, cell_diameter_mm=80)

    preview = build_preview_svg(settings, symbol_root=root, scale_path=scale_path)

    assert 'width="191.11" height="191.11"' in preview
    assert 'width="275.20" height="275.20"' not in preview


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


def test_preview_svg_can_randomize_symbol_distribution(tmp_path: Path) -> None:
    root = tmp_path / "symbols"
    root.mkdir()
    for index in range(3):
        (root / f"symbol_{index}.svg").write_text(
            f"<svg width='800' height='800' xmlns='http://www.w3.org/2000/svg'><path d='M{100 + index},100 L700,700'/></svg>",
            encoding="utf-8",
        )
    scale_path = tmp_path / "symbol_scales.json"
    save_symbol_scales({f"symbol_{index}.svg": 1.0 for index in range(3)}, scale_path, root)
    settings = GuiSettings(sheet_width_mm=300, sheet_height_mm=220, cell_diameter_mm=80)

    ordered = build_preview_svg(
        settings, user_count=layout_capacity(settings), idle_count=0, symbol_root=root, scale_path=scale_path
    )
    randomized = build_preview_svg(
        settings,
        user_count=layout_capacity(settings),
        idle_count=0,
        randomize_symbols=True,
        symbol_root=root,
        scale_path=scale_path,
    )

    assert randomized.count("<image") == layout_capacity(settings)
    assert randomized != ordered


def test_preview_svg_shows_organic_rotation_and_scale(tmp_path: Path) -> None:
    root = _symbol_root(tmp_path)
    scale_path = tmp_path / "symbol_scales.json"
    save_symbol_scales({"symbol_0.svg": 1.0, "symbol_1.svg": 1.0}, scale_path, root)
    settings = GuiSettings(
        sheet_width_mm=300,
        sheet_height_mm=220,
        cell_diameter_mm=80,
        organic_enabled=True,
        organic_cell_size_mm=18,
        organic_rotation_ramp=1,
        organic_scale_ramp=1,
        organic_seed=42,
    )

    preview = build_preview_svg(settings, symbol_root=root, scale_path=scale_path)

    assert preview.count("<image") == layout_capacity(settings)
    assert 'transform="rotate(' in preview
    assert 'data-placement-scale="' in preview


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


def test_realtime_preview_renders_only_manifest_geometry(tmp_path: Path) -> None:
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
                        "center_x_mm": 37.0,
                        "center_y_mm": 37.0,
                        "cell_diameter_mm": 42.0,
                    },
                    {
                        "session_id": "drawing",
                        "source_kind": "user",
                        "origin": "real_macmini",
                        "svg_path": str(root / "symbol_1.svg"),
                        "sheet_index": 1,
                        "center_x_mm": 82.0,
                        "center_y_mm": 37.0,
                        "cell_diameter_mm": 42.0,
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    settings = GuiSettings(
        sheet_width_mm=200,
        sheet_height_mm=200,
        cell_diameter_mm=42,
        organic_enabled=True,
        organic_cell_size_mm=18.0,
        organic_seed=1011,
    )
    status = {
        "latest_manifest": str(manifest),
        "status": RuntimeStatus.PRINTING.value,
        "cells_completed": 1,
        "current_cell_in_row": 2,
    }

    preview = build_realtime_preview_svg(settings, status, {"pendingAfterBaseline": 0})

    # Cells never materialized in the manifest must not be invented from the
    # current-settings layout: mixing frozen manifest geometry with a freshly
    # generated organic layout draws incoherent overlapping circles.
    assert 'data-preview-state="empty"' not in preview
    assert f'cx="{37.0 * PREVIEW_PX_PER_MM:.2f}" cy="{37.0 * PREVIEW_PX_PER_MM:.2f}"' in preview
    assert 'data-preview-state="drawn"' in preview
    assert 'data-preview-state="drawing"' in preview


def test_realtime_preview_frame_contains_oversized_manifest_geometry(tmp_path: Path) -> None:
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
                        # Laid out for a bigger sheet than the current settings.
                        "center_x_mm": 205.0,
                        "center_y_mm": 400.0,
                        "cell_diameter_mm": 80.0,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    settings = GuiSettings(sheet_width_mm=200, sheet_height_mm=200, cell_diameter_mm=42)
    status = {
        "latest_manifest": str(manifest),
        "status": RuntimeStatus.PRINTING.value,
        "cells_completed": 0,
        "current_cell_in_row": 1,
    }

    preview = build_realtime_preview_svg(settings, status, {"pendingAfterBaseline": 0})

    import re

    vb = re.search(r'viewBox="0 0 ([\d.]+) ([\d.]+)"', preview)
    width, height = float(vb.group(1)), float(vb.group(2))
    assert width >= (205.0 + 40.0) * PREVIEW_PX_PER_MM
    assert height >= (400.0 + 40.0) * PREVIEW_PX_PER_MM


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
    from neje_oracle.blocks.gui.support import build_symbol_preview_svg

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
    from neje_oracle.blocks.gui.support import effective_randomness

    assert effective_randomness(GuiSettings(randomness=20, randomness_fine=2.5)) == 12.5
    assert effective_randomness(GuiSettings(randomness=98, randomness_fine=10)) == 59
    assert effective_randomness(GuiSettings(randomness=2, randomness_fine=-10)) == 0


def test_direct_svg_print_job_writes_svg_and_gcode(tmp_path: Path) -> None:
    settings = GuiSettings(
        sheet_width_mm=800,
        sheet_height_mm=800,
        cell_diameter_mm=80,
        include_rings=True,
        include_markers=True,
    )
    job = create_direct_svg_print_job_from_gui(
        settings,
        svg_bytes=SIMPLE_SYMBOL.encode("utf-8"),
        original_name="label-test.svg",
        output_root=tmp_path / "uploaded_svg",
        plotter_settings=PlotterSettings(),
    )

    assert job.sheet_id.startswith("testsvg_")
    assert job.label == "LABEL TEST"
    assert job.svg_path.name.endswith("_label-test.svg")
    assert job.svg_path.read_text(encoding="utf-8") == SIMPLE_SYMBOL
    assert "direct SVG LABEL TEST" in job.gcode
    assert "absolute SVG coordinates" in job.gcode
    assert "; cell-start" not in job.gcode
    assert "G0 Z" in job.gcode
    assert "G0 X0 Y0" in job.gcode
    assert not (tmp_path / "uploaded_svg" / "READY").exists()
    assert not list((tmp_path / "uploaded_svg").glob("metadata.json"))


def test_direct_svg_bounds_use_operator_sheet_not_plotter_defaults(tmp_path: Path) -> None:
    """Art larger than the operator's configured sheet must be rejected.

    Regression: the bound was read from PlotterSettings' own sheet fields instead of the
    operator's GuiSettings sheet, so a 200x200 sheet silently accepted art that drew 25mm
    off the paper. PlotterSettings no longer carries geometry at all, which is what makes
    that class of mismatch unrepresentable rather than merely fixed.
    """
    svg = (
        "<svg xmlns='http://www.w3.org/2000/svg' width='200mm' height='200mm' viewBox='0 0 200 200'>"
        "<path d='M0,0 H200 V200 H0 Z' stroke='black' fill='none'/>"
        "</svg>"
    )
    settings = GuiSettings(
        sheet_width_mm=200,
        sheet_height_mm=200,
        direct_svg_origin_x_mm=25,
        direct_svg_origin_y_mm=25,
    )

    with pytest.raises(ValueError, match="exceeds the configured sheet"):
        create_direct_svg_print_job_from_gui(
            settings,
            svg_bytes=svg.encode("utf-8"),
            original_name="oversized.svg",
            output_root=tmp_path / "uploaded_svg",
            # Deliberately generous: this must NOT be what the bound is taken from.
            plotter_settings=PlotterSettings(),
        )


def test_direct_svg_print_offsets_reference_origin_for_negative_artwork(tmp_path: Path) -> None:
    svg = (
        "<svg xmlns='http://www.w3.org/2000/svg' width='160mm' height='200mm' viewBox='0 0 160 200'>"
        "<path d='M -6,-26 H 154 V 174 H -6 Z' stroke='black' fill='none'/>"
        "</svg>"
    )

    job = create_direct_svg_print_job_from_gui(
        GuiSettings(direct_svg_origin_x_mm=25, direct_svg_origin_y_mm=25),
        svg_bytes=svg.encode("utf-8"),
        original_name="negative-frame.svg",
        output_root=tmp_path / "uploaded_svg",
    )
    points = [
        tuple(float(axis[1:]) for axis in line.split()[1:3])
        for line in job.gcode.splitlines()
        if line.startswith(("G0 X", "G1 X"))
    ]

    assert min(x for x, _ in points) >= 0
    assert min(y for _, y in points) >= 0
    assert "; SVG reference origin maps to X25.000 Y25.000" in job.gcode


def test_upload_content_reader_rewinds_file_like_object() -> None:
    content = BytesIO(SIMPLE_SYMBOL.encode("utf-8"))
    content.read()

    assert read_upload_content_bytes(content) == SIMPLE_SYMBOL.encode("utf-8")


def test_upload_event_reader_supports_nicegui_file_payload() -> None:
    event = SimpleNamespace(file=SmallFileUpload("test_draw.svg", "image/svg+xml", SIMPLE_SYMBOL.encode("utf-8")))

    name, data = asyncio.run(read_upload_event_payload(event))

    assert name == "test_draw.svg"
    assert data == SIMPLE_SYMBOL.encode("utf-8")


def test_upload_event_reader_supports_legacy_content_payload() -> None:
    event = SimpleNamespace(name="legacy.svg", content=BytesIO(SIMPLE_SYMBOL.encode("utf-8")))

    name, data = asyncio.run(read_upload_event_payload(event))

    assert name == "legacy.svg"
    assert data == SIMPLE_SYMBOL.encode("utf-8")


def test_direct_svg_print_job_rejects_empty_file(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="empty"):
        create_direct_svg_print_job_from_gui(
            GuiSettings(),
            svg_bytes=b"",
            original_name="empty.svg",
            output_root=tmp_path / "uploaded_svg",
        )


def test_direct_svg_print_job_rejects_non_svg_xml(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="root element"):
        create_direct_svg_print_job_from_gui(
            GuiSettings(),
            svg_bytes=b"<html></html>",
            original_name="not-svg.svg",
            output_root=tmp_path / "uploaded_svg",
        )


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


def test_read_queue_status_fetches_on_cold_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = {"online": True, "total": 3}
    remote = SimpleNamespace(get_plot_job_counts=lambda *, run_started_at: payload)
    store = SimpleNamespace(load_run_started_at=lambda: None)
    from neje_oracle.blocks.firebase import queue_status

    monkeypatch.setattr(queue_status, "_QUEUE_STATUS_CACHE", None)
    monkeypatch.setattr(queue_status, "firebase_enabled", lambda: True)
    monkeypatch.setattr(queue_status, "FirebaseSettings", lambda: SimpleNamespace(enabled=True))
    monkeypatch.setattr(
        queue_status, "OracleSupervisorSettings", lambda: SimpleNamespace(runtime_db_path=Path("unused"))
    )
    monkeypatch.setattr(queue_status, "OracleRuntimeStore", lambda _: store)
    monkeypatch.setattr(queue_status, "FirebaseRemoteRepository", lambda _: remote)

    result = gui_support.read_queue_status()

    assert result == {"online": True, "total": 3, "runStartedAt": ""}


def test_compute_effective_sample_step_defaults_to_sample_step_at_ref_diameter():
    from neje_oracle.blocks.gui.support import compute_effective_sample_step as fn

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
    from neje_oracle.blocks.gui.support import compute_effective_sample_step as fn

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
    from neje_oracle.blocks.gui.support import compute_effective_sample_step as fn

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
    from neje_oracle.blocks.gui.support import compute_effective_sample_step as fn

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
    from neje_oracle.blocks.gui.support import GuiSettings, load_gui_settings, save_gui_settings

    settings_path = tmp_path / "gui_settings.json"
    settings = GuiSettings(
        cell_diameter_mm=160.0,
        organic_enabled=True,
        organic_cell_size_mm=21.0,
        organic_rotation_ramp=0.75,
        organic_scale_ramp=0.5,
        organic_seed=77,
        sample_step_mm=0.5,
        sample_reference_cell_mm=80.0,
        sample_density_exponent=1.5,
        sample_min_step_mm=0.1,
        sample_max_step_mm=5.0,
        xy_acceleration_mm_s2=1.0,
        streaming_mode="row",
    )
    save_gui_settings(settings, settings_path)
    loaded = load_gui_settings(settings_path)
    assert loaded.sample_step_mm == 0.5
    assert loaded.organic_enabled is True
    assert loaded.organic_cell_size_mm == 21.0
    assert loaded.organic_rotation_ramp == 0.75
    assert loaded.organic_scale_ramp == 0.5
    assert loaded.organic_seed == 77
    assert loaded.sample_reference_cell_mm == 80.0
    assert loaded.sample_density_exponent == 1.5
    assert loaded.sample_min_step_mm == 0.1
    assert loaded.sample_max_step_mm == 5.0
    assert loaded.xy_acceleration_mm_s2 == 1000.0
    assert loaded.streaming_mode == "row"


def test_gui_optimisation_settings_preserve_zero_xy_acceleration(tmp_path: Path):
    settings_path = tmp_path / "gui_settings.json"
    settings = GuiSettings(xy_acceleration_mm_s2=0.0)

    save_gui_settings(settings, settings_path)
    loaded = load_gui_settings(settings_path)

    assert loaded.xy_acceleration_mm_s2 == 0.0


def test_gui_settings_to_plotter_config_carries_optimisation(tmp_path: Path):
    from neje_oracle.blocks.gui.support import GuiSettings, gui_settings_to_plotter_config
    from neje_oracle.shared.models import PlotterRuntimeConfig

    settings = GuiSettings(
        cell_diameter_mm=160.0,
        organic_enabled=True,
        organic_cell_size_mm=21.0,
        organic_rotation_ramp=0.75,
        organic_scale_ramp=0.5,
        organic_seed=77,
        sample_step_mm=0.5,
        sample_reference_cell_mm=80.0,
        sample_density_exponent=1.5,
        sample_min_step_mm=0.1,
        sample_max_step_mm=5.0,
        xy_acceleration_mm_s2=1.0,
        streaming_mode="cell",
    )
    config = gui_settings_to_plotter_config(settings)
    assert isinstance(config, PlotterRuntimeConfig)
    assert config.organic_enabled is True
    assert config.organic_cell_size_mm == 21.0
    assert config.organic_rotation_ramp == 0.75
    assert config.organic_scale_ramp == 0.5
    assert config.organic_seed == 77
    assert config.sample_step_mm == 0.5
    assert config.sample_reference_cell_mm == 80.0
    assert config.sample_density_exponent == 1.5
    assert config.sample_min_step_mm == 0.1
    assert config.sample_max_step_mm == 5.0
    assert config.xy_acceleration_mm_s2 == 1000.0
    assert config.streaming_mode == "cell"


def test_dry_run_manifest_includes_optimisation_settings(tmp_path: Path):
    from neje_oracle.blocks.gui.support import (
        GuiSettings,
        generate_dry_run_sheet,
    )

    symbol_root = tmp_path / "symbols"
    symbol_root.mkdir()
    (symbol_root / "s.svg").write_text(
        "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'>"
        "<path d='M10,10 L90,10 L90,90 Z' stroke='black' fill='none'/></svg>",
        encoding="utf-8",
    )
    settings = GuiSettings(
        sheet_width_mm=120.0,
        sheet_height_mm=120.0,
        cell_diameter_mm=40.0,
        organic_enabled=True,
        organic_cell_size_mm=6.0,
        organic_rotation_ramp=1.0,
        organic_scale_ramp=0.5,
        organic_seed=55,
        sample_step_mm=2.0,
        sample_density_exponent=2.0,
        xy_acceleration_mm_s2=1.0,
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
    assert payload["xy_acceleration_mm_s2"] == 1000.0
    assert payload["organic_enabled"] is True
    assert payload["organic_cell_size_mm"] == 6.0
    assert payload["organic_rotation_ramp"] == 1.0
    assert payload["organic_scale_ramp"] == 0.5
    assert payload["organic_seed"] == 55
    assert payload["items"][0]["rotation_deg"] != 0
    assert payload["items"][0]["symbol_scale"] != 1.0
    # 40mm cell < 80mm ref: effective = 2 * (80/40)^2 = 8.0, clamped to max 3.0
    assert payload["effective_sample_step_mm"] > 2.0  # smaller cell → lighter = more spacing


def test_batch_generation_controls_are_not_operator_facing(monkeypatch: pytest.MonkeyPatch) -> None:
    """Batch generation is a developer tool; it must not surface in the operator tabs.

    This used to slice service.py's *source* on the literals "with ui.tab_panel(work_tab)"
    and "(exhibition_tab)", so any restructuring of the page shell raised IndexError
    instead of failing cleanly -- and it only ever saw text that happened to sit between
    two markers. Building the workspaces and reading the rendered elements checks the
    thing that actually matters and survives the shell being rewritten.
    """
    from nicegui import ui

    from neje_oracle.blocks.gui.context import GuiContext
    from neje_oracle.blocks.gui.workspaces import exhibition, work
    from neje_oracle.shared.gui_settings import GuiSettings

    monkeypatch.setattr("neje_oracle.blocks.gui.context.load_gui_settings", lambda *a, **k: GuiSettings())
    ctx = GuiContext()

    column = ui.column()
    with column:
        work.build(ctx)
        exhibition.build(ctx)

    rendered = {
        str(text)
        for element in column.descendants()
        for text in (getattr(element, "text", None), element._props.get("label"))
        if text
    }
    for forbidden in ("Generate next filler", "START GENERATOR"):
        offenders = [text for text in rendered if forbidden in text]
        assert not offenders, f"{forbidden!r} is operator-facing in WORK/EXHIBITION: {offenders}"


def test_blocking_helper_returns_result_and_does_not_recurse() -> None:
    """Guards the _blocking wrapper: it must call run.io_bound, not itself."""
    import asyncio
    from unittest.mock import patch

    from neje_oracle.blocks.gui.context import GuiContext

    ctx = GuiContext.__new__(GuiContext)  # no __init__: avoids touching runtime state

    async def fake_io_bound(func, *args, **kwargs):
        return func(*args, **kwargs)

    with patch("neje_oracle.blocks.gui.context.run.io_bound", fake_io_bound):
        assert asyncio.run(ctx._blocking(lambda x: x * 2, 21)) == 42


def test_blocking_helper_raises_when_task_was_cancelled() -> None:
    """run.io_bound yields None on cancellation; that must not become AttributeError."""
    import asyncio
    from unittest.mock import patch

    from neje_oracle.blocks.gui.context import GuiContext

    ctx = GuiContext.__new__(GuiContext)

    async def cancelled_io_bound(func, *args, **kwargs):
        return None

    def print_uploaded_svg() -> str:
        return "unreachable"

    with (
        patch("neje_oracle.blocks.gui.context.run.io_bound", cancelled_io_bound),
        pytest.raises(RuntimeError, match="print_uploaded_svg was cancelled"),
    ):
        asyncio.run(ctx._blocking(print_uploaded_svg))
