from __future__ import annotations

import re
from random import Random
from pathlib import Path

from neje_oracle.config import FirebaseSettings, UploaderSettings
from neje_oracle.models import PublicationResult, PublicStatus, SheetItem, SheetPlacement
from neje_oracle.session_generator import build_variant_svg, generate_idle_symbols, generate_user_sessions
from neje_oracle.session_uploader import SessionUploader
from neje_oracle.store import UploaderStore
from neje_oracle.svg_gcode import generate_sheet_gcode


SIMPLE_SYMBOL = (
    "<svg width='800' height='800' xmlns='http://www.w3.org/2000/svg'>"
    "<g fill='none' stroke='black'>"
    "<polyline points='100,100 700,100 700,700 100,700'/>"
    "<line x1='200' y1='400' x2='600' y2='400'/>"
    "</g>"
    "</svg>"
)


class FakeRemoteRepository:
    def __init__(self) -> None:
        self.published: list[str] = []

    def publish_session(self, record, public_dir: Path) -> PublicationResult:
        self.published.append(record.session_id)
        assert (public_dir / "artwork.svg").exists()
        assert (public_dir / "artwork_raw.svg").exists()
        assert (public_dir / "receipt.txt").exists()
        assert (public_dir / "qr.png").exists()
        return PublicationResult(
            public_status=PublicStatus.PUBLISHED,
            public_svg_path=f"sessions/{record.session_id}/artwork.svg",
            public_receipt_path=f"sessions/{record.session_id}/receipt.txt",
            public_qr_path=f"sessions/{record.session_id}/qr.png",
            public_manifest_path=f"sessions/{record.session_id}/manifest.json",
            public_svg_url=f"https://example.test/{record.session_id}/artwork.svg",
            public_receipt_url=f"https://example.test/{record.session_id}/receipt.txt",
            public_qr_url=f"https://example.test/{record.session_id}/qr.png",
        )


def _write_symbol_bank(tmp_path: Path) -> Path:
    source_root = tmp_path / "symbols"
    source_root.mkdir()
    (source_root / "base.svg").write_text(SIMPLE_SYMBOL, encoding="utf-8")
    return source_root


def _transform_scale(svg_text: str) -> float:
    match = re.search(r"scale\(([0-9.]+)\)", svg_text)
    assert match is not None
    return float(match.group(1))


def _viewbox(svg_text: str) -> tuple[float, float, float, float]:
    match = re.search(r'viewBox="([^"]+)"', svg_text)
    assert match is not None
    return tuple(float(value) for value in match.group(1).split())  # type: ignore[return-value]


def test_user_generator_writes_touchdesigner_like_session_folder(tmp_path: Path) -> None:
    source_root = _write_symbol_bank(tmp_path)
    output_root = tmp_path / "sessions"
    generated = generate_user_sessions(
        source_root=source_root,
        output_root=output_root,
        scale_config=tmp_path / "missing_scales.json",
        count=1,
        seed=1,
        jitter_px=0,
    )

    session = generated[0]
    assert session.session_dir.exists()
    assert session.svg_file.exists()
    assert session.receipt_file.exists()
    assert (session.session_dir / "READY").exists()
    assert (session.session_dir / "metadata.json").exists()
    assert (output_root / "session_log.csv").exists()
    assert session.svg_file.read_text(encoding="utf-8").count("<circle") == 0


def test_idle_generator_writes_mark_only_svg(tmp_path: Path) -> None:
    source_root = _write_symbol_bank(tmp_path)
    generated = generate_idle_symbols(
        source_root=source_root,
        output_root=tmp_path / "idle",
        scale_config=tmp_path / "missing_scales.json",
        count=1,
        seed=1,
        jitter_px=0,
    )

    svg_text = generated[0].read_text(encoding="utf-8")
    assert svg_text.count("<circle") == 0


def test_symbol_scale_changes_inner_mark_transform(tmp_path: Path) -> None:
    source_root = _write_symbol_bank(tmp_path)
    source_svg = source_root / "base.svg"
    small_svg = build_variant_svg(source_svg, marker_kind="user", scale=0.5, rng=Random(1), jitter_px=0)
    large_svg = build_variant_svg(source_svg, marker_kind="user", scale=1.0, rng=Random(1), jitter_px=0)

    assert _transform_scale(small_svg) < _transform_scale(large_svg)


def test_variant_svg_forces_uniform_stroke_width_and_no_fill(tmp_path: Path) -> None:
    source_root = tmp_path / "symbols"
    source_root.mkdir()
    source_svg = source_root / "base.svg"
    source_svg.write_text(
        "<svg width='800' height='800' xmlns='http://www.w3.org/2000/svg'>"
        "<g fill='red' stroke='blue' stroke-width='9' style='stroke-width:12;fill:green'>"
        "<polyline points='100,100 700,100 700,700 100,700' stroke-width='4' fill='yellow'/>"
        "</g>"
        "</svg>",
        encoding="utf-8",
    )

    svg_text = build_variant_svg(source_svg, marker_kind="user", scale=1.0, rng=Random(1), jitter_px=0)

    assert 'stroke-width="2.0"' in svg_text
    assert 'stroke-width="4"' not in svg_text
    assert "stroke-width:12" not in svg_text
    assert "fill='yellow'" not in svg_text
    assert "fill:green" not in svg_text


def test_large_symbol_scale_keeps_fixed_canonical_viewbox(tmp_path: Path) -> None:
    source_root = _write_symbol_bank(tmp_path)
    source_svg = source_root / "base.svg"

    svg_text = build_variant_svg(source_svg, marker_kind="user", scale=5.0, rng=Random(1), jitter_px=0)
    min_x, min_y, width, height = _viewbox(svg_text)

    assert (min_x, min_y, width, height) == (0.0, 0.0, 1000.0, 1000.0)
    assert 'data-neje-normalized="true"' in svg_text
    assert 'data-neje-scale="5"' in svg_text


def test_generated_svg_can_feed_existing_gcode_normalizer(tmp_path: Path) -> None:
    source_root = _write_symbol_bank(tmp_path)
    generated = generate_user_sessions(
        source_root=source_root,
        output_root=tmp_path / "sessions",
        scale_config=tmp_path / "missing_scales.json",
        count=1,
        seed=1,
        jitter_px=0,
    )[0]

    gcode = generate_sheet_gcode(
        [SheetItem(source_kind="user", session_id=generated.session_id, title="test", svg_path=generated.svg_file)],
        [SheetPlacement(index=0, center_x_mm=100, center_y_mm=100, diameter_mm=160)],
        sample_step_mm=20,
        cell_diameter_mm=40,
        travel_rate=5000,
        draw_rate=1800,
        pen_up_command="M5",
        pen_down_command="M3 S15",
    )

    assert f"; item {generated.session_id} (user)" in gcode


def test_large_scaled_generated_svg_can_print_outside_cell(tmp_path: Path) -> None:
    source_root = _write_symbol_bank(tmp_path)
    svg_path = tmp_path / "large.svg"
    svg_path.write_text(
        build_variant_svg(source_root / "base.svg", marker_kind="user", scale=5.0, rng=Random(1), jitter_px=0),
        encoding="utf-8",
    )

    gcode = generate_sheet_gcode(
        [SheetItem(source_kind="user", session_id="large", title="test", svg_path=svg_path)],
        [SheetPlacement(index=0, center_x_mm=100, center_y_mm=100, diameter_mm=160)],
        sample_step_mm=20,
        cell_diameter_mm=40,
        travel_rate=5000,
        draw_rate=1800,
        pen_up_command="M5",
        pen_down_command="M3 S15",
    )
    points = [
        tuple(float(axis[1:]) for axis in line.split()[1:3])
        for line in gcode.splitlines()
        if line.startswith(("G0 X", "G1 X"))
    ]
    points = [point for point in points if point != (0.0, 0.0)]
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]

    assert min(xs) < 80
    assert max(xs) > 120
    assert min(ys) < 80
    assert max(ys) > 120
    assert "overscale" in gcode


def test_generated_session_passes_through_uploader(tmp_path: Path) -> None:
    source_root = _write_symbol_bank(tmp_path)
    output_root = tmp_path / "sessions"
    generated = generate_user_sessions(
        source_root=source_root,
        output_root=output_root,
        scale_config=tmp_path / "missing_scales.json",
        count=1,
        seed=1,
        jitter_px=0,
    )[0]

    settings = UploaderSettings(
        session_root=output_root,
        public_root=tmp_path / "public",
        db_path=tmp_path / "runtime" / "uploader.sqlite3",
        stability_seconds=0,
    )
    remote = FakeRemoteRepository()
    uploader = SessionUploader(
        settings,
        FirebaseSettings(project_id="test", storage_bucket="test", gallery_base_url="https://example.test"),
        UploaderStore(settings.db_path),
        remote,
    )

    assert uploader.scan_once() == [generated.session_id]
    assert remote.published == [generated.session_id]
