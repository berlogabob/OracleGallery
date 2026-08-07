from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from ezdxf.fonts import shapefile

from ...shared.config import _repo_root

FONT_DIR = _repo_root() / "assets" / "fonts" / "shx"


@dataclass(frozen=True)
class FontInfo:
    name: str
    path: Path
    loadable: bool
    reason: str = ""


def scan_fonts(font_dir: Path | None = None) -> list[FontInfo]:
    directory = font_dir or FONT_DIR
    infos: list[FontInfo] = []
    for path in sorted(directory.glob("*.[sS][hH][xX]")):
        try:
            font = shapefile.readfile(str(path))
            shapefile.GlyphCache(font)
        except shapefile.ShapeFileException as error:
            infos.append(FontInfo(path.stem, path, False, str(error)))
        else:
            infos.append(FontInfo(path.stem, path, True))
    return infos


def list_fonts(font_dir: Path | None = None) -> list[str]:
    return sorted(info.name for info in scan_fonts(font_dir) if info.loadable)


@lru_cache(maxsize=64)
def load_font(name: str, font_dir: Path | None = None) -> shapefile.GlyphCache:
    directory = font_dir or FONT_DIR
    matches = [path for path in directory.glob("*.[sS][hH][xX]") if path.stem == name]
    if not matches:
        available = list_fonts(directory)
        sample = ", ".join(available[:5])
        raise ValueError(f"unknown font {name!r}; known fonts include: {sample}")
    try:
        font = shapefile.readfile(str(matches[0]))
        return shapefile.GlyphCache(font)
    except shapefile.ShapeFileException as error:
        raise ValueError(f"font {name!r} failed to load: {error}") from error


@lru_cache(maxsize=64)
def _cap_height_factor(name: str, font_dir: Path | None = None) -> float:
    """Correction so `cap_height_mm` is the height that actually lands on paper.

    An SHX header's `above` value is headroom above the baseline, not the cap line.
    Whole font families (DIN, ISO, GENISO...) carry ~10% slack there, so asking ezdxf
    for 10mm caps draws 9mm ones. Measure a reference capital once and scale by it.
    """
    cache = load_font(name, font_dir)
    for reference in ("H", "X", "E", "A", "0"):
        paths = cache.get_text_glyph_paths(reference, 100.0, 1.0)
        ys = [v.y for path in paths for sub in path.sub_paths() for v in sub.flattening(1.0)]
        if ys and (measured := max(ys) - min(ys)) > 0.0:
            return 100.0 / measured
    return 1.0


def _flatten_glyphs(paths: list[shapefile.GlyphPath], flatten_mm: float) -> list[list[tuple[float, float]]]:
    polylines: list[list[tuple[float, float]]] = []
    for glyph_path in paths:
        for sub in glyph_path.sub_paths():
            points = [(v.x, v.y) for v in sub.flattening(flatten_mm)]
            if len(points) >= 2:
                polylines.append(points)
    return polylines


def _line_layout(
    line: str,
    cache: shapefile.GlyphCache,
    *,
    cap_height_mm: float,
    width_factor: float,
    letter_spacing_mm: float,
    flatten_mm: float,
) -> tuple[list[list[tuple[float, float]]], float]:
    if not line or letter_spacing_mm == 0.0:
        paths = cache.get_text_glyph_paths(line, cap_height_mm, width_factor)
        polylines = _flatten_glyphs(paths, flatten_mm)
        width = cache.get_text_length(line, cap_height_mm, width_factor)
        return polylines, width

    polylines = []
    x_offset = 0.0
    for character in line:
        paths = cache.get_text_glyph_paths(character, cap_height_mm, width_factor)
        char_polylines = _flatten_glyphs(paths, flatten_mm)
        for polyline in char_polylines:
            polylines.append([(x + x_offset, y) for x, y in polyline])
        char_width = cache.get_text_length(character, cap_height_mm, width_factor)
        x_offset += char_width + letter_spacing_mm
    width = max(0.0, x_offset - letter_spacing_mm)
    return polylines, width


def _layout_text(
    text: str,
    *,
    font: str,
    cap_height_mm: float,
    width_factor: float,
    letter_spacing_mm: float,
    line_spacing: float,
    flatten_mm: float,
    font_dir: Path | None,
) -> tuple[list[list[tuple[float, float]]], float, float]:
    """Return (Y-up unflipped polylines, block width, block height)."""
    cache = load_font(font, font_dir)
    # Line advance stays in requested mm; only the glyph render size is corrected.
    line_advance = cap_height_mm * line_spacing
    render_cap_mm = cap_height_mm * _cap_height_factor(font, font_dir)
    all_points: list[list[tuple[float, float]]] = []
    max_width = 0.0
    for line_index, line in enumerate(text.split("\n")):
        polylines, width = _line_layout(
            line,
            cache,
            cap_height_mm=render_cap_mm,
            width_factor=width_factor,
            letter_spacing_mm=letter_spacing_mm,
            flatten_mm=flatten_mm,
        )
        max_width = max(max_width, width)
        y_shift = -line_index * line_advance
        for polyline in polylines:
            all_points.append([(x, y + y_shift) for x, y in polyline])

    if not all_points:
        return [], 0.0, 0.0

    ys = [y for polyline in all_points for _, y in polyline]
    min_y, max_y = min(ys), max(ys)
    height = max_y - min_y
    return all_points, max_width, height


def text_polylines(
    text: str,
    *,
    font: str,
    cap_height_mm: float = 10.0,
    width_factor: float = 1.0,
    letter_spacing_mm: float = 0.0,
    line_spacing: float = 1.6,
    origin: tuple[float, float] = (0.0, 0.0),
    flatten_mm: float = 0.15,
    font_dir: Path | None = None,
) -> list[list[tuple[float, float]]]:
    all_points, _, _ = _layout_text(
        text,
        font=font,
        cap_height_mm=cap_height_mm,
        width_factor=width_factor,
        letter_spacing_mm=letter_spacing_mm,
        line_spacing=line_spacing,
        flatten_mm=flatten_mm,
        font_dir=font_dir,
    )
    if not all_points:
        return []

    xs = [x for polyline in all_points for x, _ in polyline]
    ys = [y for polyline in all_points for _, y in polyline]
    min_x = min(xs)
    max_y = max(ys)
    origin_x, origin_y = origin

    result: list[list[tuple[float, float]]] = []
    for polyline in all_points:
        flipped = [(origin_x + (x - min_x), origin_y + (max_y - y)) for x, y in polyline]
        if len(flipped) >= 2:
            result.append(flipped)
    return result


def text_extents(
    text: str,
    *,
    font: str,
    cap_height_mm: float = 10.0,
    width_factor: float = 1.0,
    letter_spacing_mm: float = 0.0,
    line_spacing: float = 1.6,
    font_dir: Path | None = None,
) -> tuple[float, float]:
    _, width, height = _layout_text(
        text,
        font=font,
        cap_height_mm=cap_height_mm,
        width_factor=width_factor,
        letter_spacing_mm=letter_spacing_mm,
        line_spacing=line_spacing,
        flatten_mm=0.15,
        font_dir=font_dir,
    )
    return width, height


def text_svg(
    text: str,
    *,
    font: str,
    cap_height_mm: float = 10.0,
    margin_mm: float = 2.0,
    width_mm: float | None = None,
    height_mm: float | None = None,
    **kwargs: object,
) -> str:
    polylines = text_polylines(
        text,
        font=font,
        cap_height_mm=cap_height_mm,
        origin=(margin_mm, margin_mm),
        **kwargs,  # type: ignore[arg-type]
    )
    if polylines:
        xs = [x for polyline in polylines for x, _ in polyline]
        ys = [y for polyline in polylines for _, y in polyline]
        content_width = max(xs) + margin_mm
        content_height = max(ys) + margin_mm
    else:
        content_width = margin_mm * 2.0
        content_height = margin_mm * 2.0

    canvas_width = width_mm if width_mm is not None else content_width
    canvas_height = height_mm if height_mm is not None else content_height

    elements = []
    for polyline in polylines:
        points = " ".join(f"{x:.3f},{y:.3f}" for x, y in polyline)
        elements.append(f'<polyline points="{points}" fill="none" stroke="black" stroke-width="0.3"/>')
    body = "\n".join(elements)
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" '
        f'viewBox="0 0 {canvas_width:.3f} {canvas_height:.3f}" '
        f'width="{canvas_width:.3f}mm" height="{canvas_height:.3f}mm" '
        'data-neje-simplify-mm="0">\n'
        f"{body}\n"
        "</svg>\n"
    )
