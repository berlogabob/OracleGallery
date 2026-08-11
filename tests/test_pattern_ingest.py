from __future__ import annotations

from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

from neje_oracle.blocks.patterns import bank
from neje_oracle.blocks.patterns.ingest import (
    CANONICAL_MOTIF_MM,
    CropBox,
    crop_image,
    image_to_motif_polylines,
    image_to_motif_svg,
)


def _png(draw_on: Image.Image) -> bytes:
    buffer = BytesIO()
    draw_on.save(buffer, format="PNG")
    return buffer.getvalue()


def _shape_in_top_left(size: int = 400) -> bytes:
    """White field with a solid black disc in the top-left quadrant only."""
    image = Image.new("L", (size, size), 255)
    ImageDraw.Draw(image).ellipse((40, 40, 160, 160), fill=0)
    return _png(image)


def _wide_bar() -> bytes:
    """A 2:1 black bar, so a non-uniform scale shows up as a stretched motif."""
    image = Image.new("L", (400, 400), 255)
    ImageDraw.Draw(image).rectangle((40, 140, 360, 300), fill=0)
    return _png(image)


def _ink_bounds(polylines: list[list[tuple[float, float]]]) -> tuple[float, float, float, float]:
    points = [point for polyline in polylines for point in polyline]
    xs = [x for x, _ in points]
    ys = [y for _, y in points]
    return min(xs), max(xs), min(ys), max(ys)


# --- crop maths ----------------------------------------------------------------


def test_crop_resolves_percentages_to_pixels() -> None:
    assert CropBox(left=25, top=50, width=25, height=25).pixels(400, 200) == (100, 100, 200, 150)


def test_crop_clamps_to_the_image() -> None:
    # 80% wide starting at 50% would run off the right edge.
    left, top, right, bottom = CropBox(left=50, top=50, width=80, height=80).pixels(400, 400)
    assert (right, bottom) == (400, 400)
    assert (left, top) == (200, 200)


def test_crop_with_a_negative_origin_stays_inside_the_image() -> None:
    """Both edges derive from the clamped origin, so a negative left cannot skew the box.

    Unreachable from the GUI (min=0 on the inputs) but the dataclass is public API, and
    the positive-area guard cannot catch it -- left is already clamped by then.
    """
    left, top, right, bottom = CropBox(left=-40, top=-40, width=50, height=50).pixels(400, 400)
    assert (left, top) == (0, 0)
    assert 0 < right <= 400 and 0 < bottom <= 400
    # 50% of a 400px image, measured from the clamped origin, not from -40%.
    assert (right, bottom) == (200, 200)


def test_crop_rejects_zero_and_negative_area() -> None:
    for box in (CropBox(width=0), CropBox(height=0), CropBox(width=-10)):
        with pytest.raises(ValueError, match="positive"):
            box.pixels(400, 400)


def test_crop_produces_the_requested_pixel_size() -> None:
    cropped = Image.open(BytesIO(crop_image(_shape_in_top_left(), CropBox(left=0, top=0, width=50, height=25))))
    assert cropped.size == (200, 100)


# --- the crop actually selects a region ----------------------------------------


def test_crop_selects_the_right_quadrant() -> None:
    """The assertion that fails if the crop box is wired to the wrong axis.

    The disc lives only in the top-left quadrant, so tracing the bottom-right must find
    nothing while the top-left must find the disc.
    """
    data = _shape_in_top_left()

    with pytest.raises(ValueError, match="no motif found"):
        image_to_motif_polylines(data, crop=CropBox(left=55, top=55, width=40, height=40))

    found = image_to_motif_polylines(data, crop=CropBox(left=2, top=2, width=45, height=45))
    assert found, "the quadrant holding the disc must produce geometry"


def test_crop_is_not_transposed() -> None:
    """A left/top swap would still find ink in a symmetric image, so use an asymmetric one."""
    image = Image.new("L", (400, 400), 255)
    ImageDraw.Draw(image).ellipse((260, 40, 360, 140), fill=0)  # top-RIGHT only
    data = _png(image)

    assert image_to_motif_polylines(data, crop=CropBox(left=55, top=2, width=40, height=40))
    with pytest.raises(ValueError, match="no motif found"):
        image_to_motif_polylines(data, crop=CropBox(left=2, top=55, width=40, height=40))


# --- normalization contract ----------------------------------------------------


def test_motif_lands_in_the_unit_box() -> None:
    polylines = image_to_motif_polylines(_shape_in_top_left())
    min_x, max_x, min_y, max_y = _ink_bounds(polylines)
    assert max(max_x - min_x, max_y - min_y) == pytest.approx(1.0, abs=1e-6)
    assert min_x >= -0.5001 and max_x <= 0.5001
    assert min_y >= -0.5001 and max_y <= 0.5001


def test_aspect_ratio_survives_the_pipeline() -> None:
    min_x, max_x, min_y, max_y = _ink_bounds(image_to_motif_polylines(_wide_bar()))
    assert max_x - min_x == pytest.approx(1.0, abs=1e-6)
    # 320x160 of ink is 2:1; contour rides just outside the edges, so allow slack.
    assert 0.4 < (max_y - min_y) < 0.6


def test_svg_loads_back_as_a_bank_motif(tmp_path: Path) -> None:
    """The round trip that matters: what we save must be what the bank can read."""
    svg = image_to_motif_svg(_shape_in_top_left())
    (tmp_path / "disc.svg").write_text(svg, encoding="utf-8")

    reloaded = bank.motif_polylines("disc", tmp_path)
    min_x, max_x, min_y, max_y = _ink_bounds(reloaded)
    assert max(max_x - min_x, max_y - min_y) == pytest.approx(1.0, abs=1e-6)


def test_svg_is_stored_at_the_canonical_size() -> None:
    # Not functionally load-bearing (to_unit_box renormalizes), but it is what makes the
    # file sane to open in an editor.
    assert f'width="{CANONICAL_MOTIF_MM:g}mm"' in image_to_motif_svg(_shape_in_top_left())


# --- optimisation knobs --------------------------------------------------------


def test_simplify_reduces_points_without_emptying_the_motif() -> None:
    data = _shape_in_top_left()
    counts = [sum(len(p) for p in image_to_motif_polylines(data, simplify_mm=mm)) for mm in (0.0, 0.5, 2.0)]
    assert counts[0] > counts[1] > counts[2] > 0, counts


def test_simplify_rejects_negative_tolerance() -> None:
    with pytest.raises(ValueError, match="simplify_mm"):
        image_to_motif_polylines(_shape_in_top_left(), simplify_mm=-1.0)


def test_despeckle_drops_the_small_stroke_and_keeps_the_big_one() -> None:
    image = Image.new("L", (400, 400), 255)
    ImageDraw.Draw(image).ellipse((40, 40, 240, 240), fill=0)  # big
    ImageDraw.Draw(image).ellipse((330, 330, 340, 340), fill=0)  # speck
    data = _png(image)

    assert len(image_to_motif_polylines(data, despeckle_mm=0.0)) > len(image_to_motif_polylines(data, despeckle_mm=8.0))


def test_autocontrast_flag_reaches_load_tone() -> None:
    """Guard on the new image_to_polylines passthrough; without it the flag is inert.

    A low-contrast image is the only place the two differ: autocontrast stretches it back
    to full range, so turning it off must change the geometry.
    """
    image = Image.new("L", (400, 400), 200)
    ImageDraw.Draw(image).ellipse((80, 80, 320, 320), fill=150)
    data = _png(image)

    stretched = image_to_motif_polylines(data, autocontrast=True)
    flat = image_to_motif_polylines(data, autocontrast=False, gamma=0.4)
    assert stretched != flat


def test_unreadable_bytes_are_rejected_clearly() -> None:
    with pytest.raises(ValueError, match="unreadable image"):
        image_to_motif_polylines(b"not an image at all")


# --- saving --------------------------------------------------------------------


def test_save_motif_sanitizes_the_name(tmp_path: Path) -> None:
    svg = image_to_motif_svg(_shape_in_top_left())
    target = bank.save_motif("Screenshot 2026/08/05 :: tribal!", svg, bank_dir=tmp_path)
    # Path(name).stem would keep only "05-tribal": a typed label is not a path.
    assert target.stem == "Screenshot-2026-08-05-tribal"
    assert target.stem in bank.list_motifs(tmp_path)


def test_save_motif_does_not_double_the_svg_extension(tmp_path: Path) -> None:
    target = bank.save_motif("glyph.svg", image_to_motif_svg(_shape_in_top_left()), bank_dir=tmp_path)
    assert target.name == "glyph.svg"


def test_save_motif_cannot_escape_the_bank_directory(tmp_path: Path) -> None:
    target = bank.save_motif("../../etc/passwd", image_to_motif_svg(_shape_in_top_left()), bank_dir=tmp_path)
    assert target.parent == tmp_path


def test_save_motif_suffixes_instead_of_overwriting(tmp_path: Path) -> None:
    svg = image_to_motif_svg(_shape_in_top_left())
    first = bank.save_motif("glyph", svg, bank_dir=tmp_path)
    second = bank.save_motif("glyph", svg, bank_dir=tmp_path)
    third = bank.save_motif("glyph", svg, bank_dir=tmp_path)
    assert [first.stem, second.stem, third.stem] == ["glyph", "glyph-2", "glyph-3"]


def test_save_motif_creates_the_bank_directory(tmp_path: Path) -> None:
    target = bank.save_motif("glyph", image_to_motif_svg(_shape_in_top_left()), bank_dir=tmp_path / "new")
    assert target.exists()


def test_save_motif_rejects_and_removes_an_unloadable_file(tmp_path: Path) -> None:
    """load_bank swallows broken files, so an unvalidated save would fail silently."""
    with pytest.raises(ValueError, match="does not load back"):
        bank.save_motif("junk", "<svg xmlns='http://www.w3.org/2000/svg'></svg>", bank_dir=tmp_path)
    assert list(tmp_path.glob("*.svg")) == [], "the rejected file must not be left behind"
    assert bank.list_motifs(tmp_path) == []
