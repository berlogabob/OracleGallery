from __future__ import annotations

import re
import time
from pathlib import Path

import pytest

from neje_oracle.blocks.gcode.svg_gcode import generate_absolute_svg_gcode
from neje_oracle.blocks.text.shx import (
    list_fonts,
    load_font,
    scan_fonts,
    text_extents,
    text_polylines,
    text_svg,
)

EXPECTED_UNLOADABLE = {
    "zzextfont",
    "zzextfont2",
    "zzISO8",
    "zzISO9",
    "zzMSIMPLEX",
    "zzSCRIPTS8",
}

# Fonts confirmed to hit cap_height_mm exactly for "HXE" (flat-top, no
# descenders). Fonts like the DIN/ISOCP families intentionally render a
# fraction under cap height because their "X" glyph does not touch the cap
# line by design, so they are excluded from this tight-tolerance sample
# rather than loosening the tolerance for everyone.
# Bold-italic and handwriting faces overshoot the cap line by design; every other
# font must land within 2% of the requested millimetre height.
CAP_HEIGHT_OVERSHOOT_FONTS = {"zzCIBT____", "zzHAND"}


def _block_height(polylines: list[list[tuple[float, float]]]) -> float:
    ys = [y for polyline in polylines for _, y in polyline]
    return max(ys) - min(ys)


def test_expected_font_load_counts() -> None:
    fonts = scan_fonts()
    assert len(fonts) == 44
    loadable = [info for info in fonts if info.loadable]
    unloadable = {info.name: info for info in fonts if not info.loadable}
    assert len(loadable) == 38
    assert set(unloadable) == EXPECTED_UNLOADABLE
    for info in unloadable.values():
        assert info.reason


def test_list_fonts_only_loadable() -> None:
    fonts = list_fonts()
    assert len(fonts) == 38
    assert fonts == sorted(fonts)
    assert not (set(fonts) & EXPECTED_UNLOADABLE)


def test_cap_height_accuracy() -> None:
    """Requested mm must be delivered mm — the plotter draws what the operator typed."""
    failures = []
    for font in list_fonts():
        if font in CAP_HEIGHT_OVERSHOOT_FONTS:
            continue
        polylines = text_polylines("HXE", font=font, cap_height_mm=10.0)
        height = _block_height(polylines)
        error = abs(height - 10.0) / 10.0
        if error > 0.02:
            failures.append(f"{font}: height={height:.3f} error={error:.2%}")
    assert not failures, "cap height off by more than 2%: " + "; ".join(failures)


def test_cap_height_scales_linearly() -> None:
    small = _block_height(text_polylines("HXE", font="zzDIN", cap_height_mm=5.0))
    large = _block_height(text_polylines("HXE", font="zzDIN", cap_height_mm=20.0))
    assert abs(large / small - 4.0) < 0.02


def test_y_is_down() -> None:
    polylines = text_polylines("T", font="zzsimplex", cap_height_mm=10.0)
    assert polylines
    crossbar = min(polylines, key=lambda pl: max(y for _, y in pl) - min(y for _, y in pl))
    crossbar_y = sum(y for _, y in crossbar) / len(crossbar)
    stem_bottom_y = max(y for polyline in polylines for _, y in polyline)
    assert crossbar_y < stem_bottom_y - 1.0


def test_ascii_coverage() -> None:
    fonts = list_fonts()
    total_hits = 0
    total_chars = 0
    per_font: list[tuple[str, float]] = []
    for font in fonts:
        hits = 0
        for code in range(33, 127):
            if text_polylines(chr(code), font=font, cap_height_mm=10.0):
                hits += 1
        total_hits += hits
        total_chars += 94
        per_font.append((font, 100.0 * hits / 94))

    coverage = 100.0 * total_hits / total_chars
    low = [f"{name}={pct:.1f}%" for name, pct in per_font if pct < 95.0]
    assert coverage >= 95.0, (
        f"aggregate ascii coverage {coverage:.2f}% across {len(fonts)} fonts; "
        f"fonts below 95%: {', '.join(low) if low else 'none'}"
    )


def test_empty_and_whitespace() -> None:
    for text in ("", "   ", "\n\n"):
        assert text_polylines(text, font="zzsimplex") == []


def test_unknown_font_raises() -> None:
    with pytest.raises(ValueError):
        text_polylines("A", font="not_a_real_font")


def test_multiline_layout() -> None:
    cap_height = 10.0
    line_spacing = 1.6
    single = text_polylines("AAA", font="zzsimplex", cap_height_mm=cap_height, line_spacing=line_spacing)
    triple = text_polylines(
        "AAA\nAAA\nAAA",
        font="zzsimplex",
        cap_height_mm=cap_height,
        line_spacing=line_spacing,
    )
    single_h = _block_height(single)
    expected_extra = 2 * cap_height * line_spacing
    actual_extra = _block_height(triple) - single_h
    assert abs(actual_extra - expected_extra) <= expected_extra * 0.10

    # Each of the 3 identical "AAA" lines occupies the same y-band height
    # (single_h). Lines are stacked line_advance apart, so no two lines'
    # bands overlap in Y iff the advance is at least that band height.
    line_advance = cap_height * line_spacing
    assert line_advance >= single_h, (
        f"line advance {line_advance:.2f}mm is smaller than a single line's "
        f"rendered height {single_h:.2f}mm; stacked lines would overlap in Y"
    )


def test_zero_letter_spacing_matches_ezdxf_layout() -> None:
    font = "zzsimplex"
    cache = load_font(font)
    text = "HELLO"
    width, _ = text_extents(text, font=font, cap_height_mm=10.0, letter_spacing_mm=0.0)
    expected_width = cache.get_text_length(text, 10.0, 1.0)
    assert abs(width - expected_width) < 1e-6


def test_gcode_roundtrip_all_fonts(tmp_path: Path) -> None:
    for font in list_fonts():
        svg = text_svg("NEJE\nORACLE\n0123", font=font, cap_height_mm=8.0)
        svg_path = tmp_path / f"{font}.svg"
        svg_path.write_text(svg)

        gcode = generate_absolute_svg_gcode(
            svg_path,
            sample_step_mm=1.0,
            travel_rate=5000.0,
            draw_rate=1800.0,
            pen_up_command="M5",
            pen_down_command="M3 S15",
        )
        assert "G21" in gcode, font
        assert "G90" in gcode, font
        assert "M3 S15" in gcode, font
        assert "M5" in gcode, font
        lines = gcode.splitlines()
        assert any(line.startswith("G1 ") for line in lines), font

        size_match = re.search(r'width="([\d.]+)mm" height="([\d.]+)mm"', svg)
        assert size_match, font
        max_x = float(size_match.group(1))
        max_y = float(size_match.group(2))

        for line in lines:
            if not line.startswith(("G0 X", "G1 X")):
                continue
            x_val = y_val = None
            for part in line.split():
                if part.startswith("X"):
                    x_val = float(part[1:])
                elif part.startswith("Y"):
                    y_val = float(part[1:])
            assert x_val is not None and y_val is not None, font
            assert -0.01 <= x_val <= max_x + 0.01, font
            assert -0.01 <= y_val <= max_y + 0.01, font


def test_font_cache_is_fast() -> None:
    load_font("zzsimplex")
    start = time.perf_counter()
    for _ in range(100):
        load_font("zzsimplex")
    elapsed = time.perf_counter() - start
    assert elapsed < 0.05
