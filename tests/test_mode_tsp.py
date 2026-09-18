import io
import math

from mode_contract import check_mode_contract
from PIL import Image, ImageDraw

from neje_oracle.blocks.imaging.art.tsp import quality_params, tsp
from neje_oracle.blocks.imaging.modes import load_tone


def _tone_from_image(image: Image.Image, width_mm: float, height_mm: float, cell_mm: float):
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return load_tone(buffer.getvalue(), width_mm=width_mm, height_mm=height_mm, cell_mm=cell_mm)


def test_tsp_contract():
    report = check_mode_contract(tsp, quality_params)
    print(report)


def test_solid_disc_is_a_few_long_strokes():
    """A solid dark disc on white paper should tour almost end-to-end: a handful of
    polylines, none of them jumping farther than max_jump_mm between consecutive points."""
    image = Image.new("L", (200, 200), 255)
    draw = ImageDraw.Draw(image)
    draw.ellipse([20, 20, 180, 180], fill=0)
    tone = _tone_from_image(image, 60.0, 60.0, 0.5)

    max_jump_mm = 3.0  # 3x the default point_spacing_mm of 1.0
    polylines = tsp(tone, point_spacing_mm=1.0, seed=1)

    assert len(polylines) >= 1
    assert len(polylines) <= 3, f"expected a near-continuous tour, got {len(polylines)} polylines"

    total_points = sum(len(polyline) for polyline in polylines)
    assert total_points > 50, "a 60mm solid disc should place well over a handful of points"

    for polyline in polylines:
        for start, end in zip(polyline, polyline[1:], strict=False):
            gap = math.dist(start, end)
            assert gap <= max_jump_mm + 1e-6, f"segment {gap} mm exceeds max_jump_mm={max_jump_mm}"


def test_smaller_spacing_places_more_points_and_ink():
    """A black square drawn at a tighter point_spacing_mm should place more points and
    more total ink than the same square at a looser spacing."""
    image = Image.new("L", (100, 100), 0)
    tone = _tone_from_image(image, 40.0, 40.0, 0.5)

    coarse = tsp(tone, point_spacing_mm=2.0, seed=2)
    fine = tsp(tone, point_spacing_mm=0.8, seed=2)

    coarse_points = sum(len(polyline) for polyline in coarse)
    fine_points = sum(len(polyline) for polyline in fine)
    assert fine_points > coarse_points, (fine_points, coarse_points)

    coarse_ink = sum(math.dist(a, b) for p in coarse for a, b in zip(p, p[1:], strict=False))
    fine_ink = sum(math.dist(a, b) for p in fine for a, b in zip(p, p[1:], strict=False))
    assert fine_ink > coarse_ink, (fine_ink, coarse_ink)


def test_rejects_runaway_point_count():
    tone = _tone_from_image(Image.new("L", (10, 10), 0), 300.0, 300.0, 1.0)
    try:
        tsp(tone, point_spacing_mm=0.2, max_points=1000)
    except ValueError as error:
        assert "max_points" in str(error)
    else:
        raise AssertionError("expected a ValueError for a runaway point count")
