from __future__ import annotations

import json
import random
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

from svgpathtools import svg2paths2

SVG_NS = "http://www.w3.org/2000/svg"
ET.register_namespace("", SVG_NS)

CANONICAL_CANVAS_SIZE = 1000.0
CANONICAL_CENTER = CANONICAL_CANVAS_SIZE / 2.0
CANONICAL_BASE_DIAMETER = 720.0
CANONICAL_IDLE_INNER_DIAMETER = 676.0
MIN_SCALE = 0.3
MAX_SCALE = 5.0
DEFAULT_CENTER_Y_OFFSETS = {
    "test_the_kind_soul_220047_plotter.svg": -72.0,
}
DEFAULT_SINGLE_STROKE_SYMBOLS = {
    "20260421_223735_plotter.svg",
    "test_the_kind_soul_220047_plotter.svg",
}
DEFAULT_SIMPLIFY_TOLERANCE_MM = {
    "20260421_223735_plotter.svg": 0.04,
    "test_the_kind_soul_220047_plotter.svg": 0.02,
}

MARK_NAMES = [
    "THE KIND SOUL",
    "THE PITIFUL STORY",
    "THE SHRIEK",
    "THE THORNS",
    "THE SKY EYE",
    "THE BITTER ROOT",
    "THE STILL BLADE",
    "THE HOLLOW SUN",
]


@dataclass(frozen=True)
class NormalizedSvgMetadata:
    normalized: bool
    scale: float
    base_diameter: float
    canvas_size: float
    center_y_offset: float = 0.0


def normalize_svg_file(
    source_svg: Path,
    *,
    marker_kind: str = "user",
    scale: float = 1.0,
    include_rings: bool = False,
    rng: random.Random | None = None,
    jitter_px: float = 0.0,
) -> str:
    tree = ET.parse(source_svg)
    root = tree.getroot()
    if rng is not None:
        _jitter_drawables(root, rng, jitter_px)
    bbox = _drawable_bbox_from_tree(root, fallback_path=source_svg)
    center_y_offset = DEFAULT_CENTER_Y_OFFSETS.get(source_svg.name, 0.0)
    single_stroke = source_svg.name in DEFAULT_SINGLE_STROKE_SYMBOLS
    simplify_tolerance_mm = DEFAULT_SIMPLIFY_TOLERANCE_MM.get(source_svg.name, 0.0)
    return normalize_svg_root(
        root,
        bbox=bbox,
        marker_kind=marker_kind,
        scale=scale,
        include_rings=include_rings,
        center_y_offset=center_y_offset,
        single_stroke=single_stroke,
        simplify_tolerance_mm=simplify_tolerance_mm,
    )


def normalize_svg_root(
    root: ET.Element,
    *,
    bbox: tuple[float, float, float, float],
    marker_kind: str = "user",
    scale: float = 1.0,
    include_rings: bool = False,
    center_y_offset: float = 0.0,
    single_stroke: bool = False,
    simplify_tolerance_mm: float = 0.0,
) -> str:
    if marker_kind not in {"idle", "user"}:
        raise ValueError(f"Unsupported marker kind: {marker_kind}")

    bounded_scale = _bounded_scale(scale)
    min_x, min_y, max_x, max_y = bbox
    width = max(max_x - min_x, 1.0)
    height = max(max_y - min_y, 1.0)
    source_mid_x = (min_x + max_x) / 2.0
    source_mid_y = (min_y + max_y) / 2.0
    target_diameter = CANONICAL_BASE_DIAMETER * bounded_scale
    transform_scale = target_diameter / max(width, height)
    _force_stroke_only(root)
    children = "\n".join(ET.tostring(child, encoding="unicode") for child in list(root))

    rings: list[str] = []
    if include_rings:
        rings.append(_circle(CANONICAL_BASE_DIAMETER / 2.0))
        if marker_kind == "idle":
            rings.append(_circle(CANONICAL_IDLE_INNER_DIAMETER / 2.0))

    return (
        f'<svg xmlns="{SVG_NS}" width="{int(CANONICAL_CANVAS_SIZE)}" height="{int(CANONICAL_CANVAS_SIZE)}" '
        f'viewBox="0 0 {int(CANONICAL_CANVAS_SIZE)} {int(CANONICAL_CANVAS_SIZE)}" overflow="visible" '
        'style="overflow:visible" '
        'data-neje-normalized="true" '
        f'data-neje-single-stroke="{str(single_stroke).lower()}" '
        f'data-neje-simplify-mm="{max(0.0, simplify_tolerance_mm):.6g}" '
        f'data-neje-scale="{bounded_scale:.6g}" '
        f'data-neje-center-y-offset="{center_y_offset:.6g}" '
        f'data-neje-base-diameter="{CANONICAL_BASE_DIAMETER:.6g}" '
        f'data-neje-canvas-size="{CANONICAL_CANVAS_SIZE:.6g}">\n'
        '<g fill="none" stroke="black" stroke-width="2.0" stroke-linecap="round" stroke-linejoin="round">\n'
        + "\n".join(rings)
        + "\n"
        f'<g data-neje-layer="mark" transform="translate({CANONICAL_CENTER:.3f} {CANONICAL_CENTER + center_y_offset:.3f}) '
        f'scale({transform_scale:.8f}) translate({-source_mid_x:.3f} {-source_mid_y:.3f})">\n'
        f"{children}\n"
        "</g>\n"
        "</g>\n"
        "</svg>\n"
    )


def read_normalized_svg_metadata(svg_path: Path) -> NormalizedSvgMetadata:
    root = ET.parse(svg_path).getroot()
    return NormalizedSvgMetadata(
        normalized=root.get("data-neje-normalized") == "true",
        scale=_read_float_attr(root, "data-neje-scale", 1.0),
        base_diameter=_read_float_attr(root, "data-neje-base-diameter", CANONICAL_BASE_DIAMETER),
        canvas_size=_read_float_attr(root, "data-neje-canvas-size", CANONICAL_CANVAS_SIZE),
        center_y_offset=_read_float_attr(root, "data-neje-center-y-offset", 0.0),
    )


def is_normalized_svg(svg_path: Path) -> bool:
    try:
        return read_normalized_svg_metadata(svg_path).normalized
    except ET.ParseError:
        return False


def load_mark_scales(symbol_root: Path, scale_config: Path) -> dict[str, float]:
    symbols = sorted(path for path in symbol_root.glob("*.svg") if path.is_file())
    payload: dict[str, float] = {}
    if scale_config.exists():
        raw = json.loads(scale_config.read_text(encoding="utf-8"))
        payload = {str(key): float(value) for key, value in raw.items()}
    result: dict[str, float] = {}
    for index, symbol in enumerate(symbols):
        result[MARK_NAMES[index % len(MARK_NAMES)]] = float(payload.get(symbol.name, 1.0))
    return result


def scale_for_mark_name(mark_name: str, symbol_root: Path, scale_config: Path) -> float:
    normalized_name = mark_name.strip().upper()
    if not normalized_name:
        return 1.0
    return load_mark_scales(symbol_root, scale_config).get(normalized_name, 1.0)


def _drawable_bbox_from_tree(root: ET.Element, *, fallback_path: Path) -> tuple[float, float, float, float]:
    paths_bbox = _drawable_bbox_from_svgpathtools(fallback_path)
    if paths_bbox is not None:
        return paths_bbox

    xs: list[float] = []
    ys: list[float] = []
    for element in root.iter():
        tag = _local_name(element.tag)
        if tag in {"polyline", "polygon"}:
            for x, y in _parse_points(element.get("points", "")):
                xs.append(x)
                ys.append(y)
        elif tag == "line":
            for x_key, y_key in (("x1", "y1"), ("x2", "y2")):
                point = _read_point(element, x_key, y_key)
                if point:
                    xs.append(point[0])
                    ys.append(point[1])
        elif tag == "circle":
            cx = _read_float(element, "cx")
            cy = _read_float(element, "cy")
            radius = _read_float(element, "r")
            if cx is not None and cy is not None and radius is not None:
                xs.extend([cx - radius, cx + radius])
                ys.extend([cy - radius, cy + radius])
        elif tag == "ellipse":
            cx = _read_float(element, "cx")
            cy = _read_float(element, "cy")
            rx = _read_float(element, "rx")
            ry = _read_float(element, "ry")
            if cx is not None and cy is not None and rx is not None and ry is not None:
                xs.extend([cx - rx, cx + rx])
                ys.extend([cy - ry, cy + ry])
    if not xs or not ys:
        return (0.0, 0.0, CANONICAL_CANVAS_SIZE, CANONICAL_CANVAS_SIZE)
    return (min(xs), min(ys), max(xs), max(ys))


def _drawable_bbox_from_svgpathtools(svg_path: Path) -> tuple[float, float, float, float] | None:
    try:
        paths, _, _ = svg2paths2(str(svg_path))
    except Exception:  # noqa: BLE001
        return None
    non_empty_paths = [path for path in paths if path.length(error=1e-4) > 0]
    if not non_empty_paths:
        return None
    return (
        min(path.bbox()[0] for path in non_empty_paths),
        min(path.bbox()[2] for path in non_empty_paths),
        max(path.bbox()[1] for path in non_empty_paths),
        max(path.bbox()[3] for path in non_empty_paths),
    )


def _jitter_drawables(root: ET.Element, rng: random.Random, jitter_px: float) -> None:
    if jitter_px <= 0:
        return
    for element in root.iter():
        tag = _local_name(element.tag)
        if tag in {"polyline", "polygon"} and element.get("points"):
            element.set("points", _jitter_points_attribute(element.get("points", ""), rng, jitter_px))
        elif tag == "line":
            for key in ("x1", "y1", "x2", "y2"):
                _jitter_numeric_attr(element, key, rng, jitter_px)
        elif tag in {"circle", "ellipse"}:
            for key in ("cx", "cy"):
                _jitter_numeric_attr(element, key, rng, jitter_px)


def _jitter_points_attribute(points: str, rng: random.Random, jitter_px: float) -> str:
    pairs: list[str] = []
    for pair in points.replace("\n", " ").split():
        if "," not in pair:
            continue
        raw_x, raw_y = pair.split(",", 1)
        try:
            x = float(raw_x) + rng.gauss(0.0, jitter_px)
            y = float(raw_y) + rng.gauss(0.0, jitter_px)
        except ValueError:
            continue
        pairs.append(f"{x:.1f},{y:.1f}")
    return " ".join(pairs)


def _jitter_numeric_attr(element: ET.Element, key: str, rng: random.Random, jitter_px: float) -> None:
    raw_value = element.get(key)
    if raw_value is None:
        return
    try:
        element.set(key, f"{float(raw_value) + rng.gauss(0.0, jitter_px):.1f}")
    except ValueError:
        return


def _parse_points(points: str) -> list[tuple[float, float]]:
    parsed: list[tuple[float, float]] = []
    for pair in points.replace("\n", " ").split():
        if "," not in pair:
            continue
        raw_x, raw_y = pair.split(",", 1)
        try:
            parsed.append((float(raw_x), float(raw_y)))
        except ValueError:
            continue
    return parsed


def _read_point(element: ET.Element, x_key: str, y_key: str) -> tuple[float, float] | None:
    x = _read_float(element, x_key)
    y = _read_float(element, y_key)
    if x is None or y is None:
        return None
    return (x, y)


def _read_float(element: ET.Element, key: str) -> float | None:
    raw_value = element.get(key)
    if raw_value is None:
        return None
    try:
        return float(raw_value)
    except ValueError:
        return None


def _read_float_attr(element: ET.Element, key: str, default: float) -> float:
    raw_value = element.get(key)
    if raw_value is None:
        return default
    try:
        return float(raw_value)
    except ValueError:
        return default


def _bounded_scale(scale: float) -> float:
    return max(MIN_SCALE, min(float(scale), MAX_SCALE))


def _circle(radius: float) -> str:
    return f'<circle cx="{CANONICAL_CENTER:.1f}" cy="{CANONICAL_CENTER:.1f}" r="{radius:.1f}" />'


def _force_stroke_only(root: ET.Element) -> None:
    for element in root.iter():
        for attribute in ("stroke", "stroke-width", "fill"):
            element.attrib.pop(attribute, None)
        style = element.get("style")
        if style:
            kept_styles = [
                part.strip()
                for part in style.split(";")
                if part.strip() and not part.strip().lower().startswith(("stroke:", "stroke-width:", "fill:"))
            ]
            if kept_styles:
                element.set("style", ";".join(kept_styles))
            else:
                element.attrib.pop("style", None)


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]
