"""Trace mode must follow the drawing's lines, not re-render its tone.

The tone modes answer "how dark is it here" and invent geometry to match. On line art that
puts ink where the source has none — measured on real ComfyUI output, contour invented 17%
of its strokes and halftone 31%, which is why their previews read as blobs. Trace exists
because it structurally cannot do that, and precision is the property under test.
"""

from __future__ import annotations

import io
import time

import numpy as np
import pytest
from PIL import Image, ImageDraw, ImageFilter

from neje_oracle.blocks.imaging.modes import image_to_polylines

WIDTH_MM = 100.0
TRACE_CELL_MM = 0.1  # 1000 cells across 100 mm, matching the 1000 px fixtures below


def _line_art(size: int = 1000) -> tuple[bytes, np.ndarray]:
    """A synthetic ink drawing: outlines plus hatching, all thin strokes on white.

    The hatching is drawn as short dashes with small gaps rather than solid lines. That is
    not decoration — thresholding a real anti-aliased render breaks strokes exactly this
    way, and rejoining them is what stitching is for. A fixture of unbroken lines would
    make the stitching assertion vacuous.
    """
    image = Image.new("L", (size, size), 255)
    draw = ImageDraw.Draw(image)
    draw.rectangle([150, 200, 850, 640], outline=0, width=3)
    draw.ellipse([300, 300, 700, 560], outline=0, width=3)
    draw.line([150, 780, 850, 780], fill=0, width=3)
    for x in range(200, 840, 28):  # hatching — the part despeckling destroys
        for segment in range(5):  # dashed: 16 px of ink, 4 px gap
            top = 660 + segment * 20
            draw.line([x + segment * 12, top, x + segment * 12 + 9, top + 16], fill=0, width=2)
    return _to_png(image), np.asarray(image) < 128


def _rasterise(polylines: list[list[tuple[float, float]]], shape: tuple[int, int]) -> np.ndarray:
    image = Image.new("L", (shape[1], shape[0]), 255)
    draw = ImageDraw.Draw(image)
    scale = shape[1] / WIDTH_MM
    for polyline in polylines:
        if len(polyline) > 1:
            draw.line([(x * scale, y * scale) for x, y in polyline], fill=0, width=2)
    return np.asarray(image) < 128


def _dilate(mask: np.ndarray, radius: int) -> np.ndarray:
    grown = Image.fromarray((mask * 255).astype(np.uint8)).filter(ImageFilter.MaxFilter(2 * radius + 1))
    return np.asarray(grown) > 127


def _score(mask: np.ndarray, reference: np.ndarray, tolerance: int = 3) -> tuple[float, float, float]:
    """Boundary F-score: a stroke within `tolerance` px of a source stroke counts as a hit.

    Exact pixel overlap is the wrong instrument — a plotted line half a millimetre off still
    reads as the same drawing, and a metric that says otherwise would reject good output.
    """
    precision = (mask & _dilate(reference, tolerance)).sum() / max(mask.sum(), 1)
    recall = (reference & _dilate(mask, tolerance)).sum() / max(reference.sum(), 1)
    return 2 * precision * recall / max(precision + recall, 1e-9), precision, recall


def _trace(data: bytes, **overrides: float) -> list[list[tuple[float, float]]]:
    return image_to_polylines(
        data, mode="trace", width_mm=WIDTH_MM, height_mm=WIDTH_MM, cell_mm=TRACE_CELL_MM, **overrides
    )


def test_trace_does_not_invent_ink() -> None:
    """The whole reason the mode exists: it can only draw where a stroke already is."""
    data, reference = _line_art()
    _, precision, _ = _score(_rasterise(_trace(data), reference.shape), reference)
    assert precision >= 0.95, f"trace put {(1 - precision) * 100:.0f}% of its ink on blank paper"


def test_trace_beats_contour_on_line_art() -> None:
    data, reference = _line_art()
    traced, _, _ = _score(_rasterise(_trace(data), reference.shape), reference)
    banded, _, _ = _score(
        _rasterise(
            image_to_polylines(data, mode="contour", width_mm=WIDTH_MM, height_mm=WIDTH_MM, cell_mm=1.5, bands=4),
            reference.shape,
        ),
        reference,
    )
    assert traced > banded, f"trace {traced:.3f} did not beat contour {banded:.3f} on line art"


def test_stitching_buys_pen_lifts_almost_free() -> None:
    """Joining near-touching chains is the mode's economics, and the reason it is usable.

    Every stroke is a Z round trip (~1.9 s at the shipped pen throw), so an un-stitched
    trace costs hours. Measured over one sample from each of nine real folders, going from
    stitch 0 to stitch 10 moved the F-score 0.906 -> 0.905 while collapsing 7 239 strokes
    to 181 — a 40x saving for a rounding error of fidelity.

    The tolerance here is looser than that 0.001 because stitching *can* bridge a gap that
    was really there; this fixture's deliberately dashed hatching is close to the worst
    case and loses 0.03. Past about 16 px even precision starts to go, which is why the
    default stops at 10.
    """
    data, reference = _line_art()
    loose = _trace(data, stitch_px=0.0)
    stitched = _trace(data)

    loose_f, _, _ = _score(_rasterise(loose, reference.shape), reference)
    stitched_f, _, _ = _score(_rasterise(stitched, reference.shape), reference)
    assert stitched_f >= loose_f - 0.05, f"stitching cost too much fidelity: {loose_f:.3f} -> {stitched_f:.3f}"
    assert len(stitched) < len(loose) / 4, f"stitching barely merged: {len(loose)} -> {len(stitched)}"


def test_blank_page_traces_to_nothing() -> None:
    buffer = io.BytesIO()
    Image.new("L", (256, 256), 255).save(buffer, format="PNG")
    assert _trace(buffer.getvalue()) == []


def _flat_fill_png(size: int = 1000) -> tuple[bytes, np.ndarray]:
    """An outlined shape with a solid mid-grey fill — the boats02 illustration style."""
    image = Image.new("L", (size, size), 255)
    draw = ImageDraw.Draw(image)
    draw.polygon([(150, 600), (850, 600), (740, 830), (260, 830)], fill=170, outline=0)
    draw.rectangle([300, 200, 700, 480], fill=185, outline=0)
    # The reference includes the fill, not just the outline: covering that fill is the whole
    # point of shading, so a mask of `< 128` would score every fill stroke as invented ink.
    return _to_png(image), np.asarray(image) < 200


def _to_png(image: Image.Image) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def test_shading_fills_flat_areas_but_leaves_line_art_alone() -> None:
    """The property that makes shading safe to leave switched on.

    In pen-and-ink art the mid-tones ARE hatching that trace already follows, so masking
    against the ink dilated by a pen width swallows them and almost nothing extra is drawn.
    In flat-colour art the fill is genuinely blank paper and must be hatched. If this ever
    inverts, the mask has broken and every line drawing gets scribbled over.
    """
    line_art, _ = _line_art()
    flat, _ = _flat_fill_png()

    bare_lines = len(_trace(line_art))
    shaded_lines = len(_trace(line_art, shade_spacing_mm=1.6))
    bare_flat = len(_trace(flat))
    shaded_flat = len(_trace(flat, shade_spacing_mm=1.6))

    assert shaded_lines <= bare_lines * 1.15, f"line art got scribbled on: {bare_lines} -> {shaded_lines}"
    assert shaded_flat > bare_flat * 1.5, f"flat fill was not filled: {bare_flat} -> {shaded_flat}"


def test_shading_never_lands_on_an_already_traced_line() -> None:
    """Hatching over ink the pen has already laid down wastes time and blots the paper.

    Fill is isolated by rasterising with and without shading and subtracting, rather than by
    diffing the polyline lists — weight passes make the two runs' lists differ in ways that
    have nothing to do with fill.
    """
    flat, reference = _flat_fill_png()
    outlines = np.asarray(Image.open(io.BytesIO(flat)).convert("L")) < 128

    bare = _rasterise(_trace(flat), reference.shape)
    shaded = _rasterise(_trace(flat, shade_spacing_mm=1.6), reference.shape)
    fill = shaded & ~_dilate(bare, 2)
    assert fill.sum() > 0, "no fill was produced, so this assertion would be vacuous"

    on_outline = (fill & _dilate(outlines, 1)).sum() / fill.sum()
    assert on_outline < 0.10, f"{on_outline:.0%} of the fill was laid over already-drawn linework"


def test_shading_does_not_start_inventing_ink() -> None:
    flat, reference = _flat_fill_png()
    _, precision, _ = _score(_rasterise(_trace(flat, shade_spacing_mm=1.6), reference.shape), reference)
    assert precision >= 0.95, f"shading put {(1 - precision) * 100:.0f}% of its ink on blank paper"


def test_weight_passes_follow_a_taper() -> None:
    """A stroke bold at one end and fine at the other must taper, not fill evenly.

    Before per-point widths this used one median for the whole chain, so a wedge was drawn
    at uniform weight — the thin end too heavy or the thick end too light.
    """
    size = 800
    image = Image.new("L", (size, size), 255)
    draw = ImageDraw.Draw(image)
    for step in range(60, 740):  # a wedge: 14 px wide on the left, 2 px on the right
        half = max(1, int(round(7 - 5 * (step - 60) / 680)))
        draw.line([step, 400 - half, step, 400 + half], fill=0, width=1)

    polylines = _trace(_to_png(image))
    thick_end = sum(1 for p in polylines for x, _ in p if x < WIDTH_MM * 0.3)
    thin_end = sum(1 for p in polylines for x, _ in p if x > WIDTH_MM * 0.7)
    assert thick_end > thin_end * 1.5, f"wedge did not taper: {thick_end} points thick vs {thin_end} thin"


def test_noise_is_refused_quickly_instead_of_hanging() -> None:
    """Noise thins to a skeleton with hundreds of thousands of pixels.

    The walk is a Python loop over those pixels, so without the cap this does not fail —
    it stalls the GUI. The wall-clock assertion is the point: a regression must show up as
    a failure, not as a suite that never finishes.
    """
    noise = np.random.default_rng(0).integers(0, 255, size=(1000, 1000), dtype=np.uint8)
    buffer = io.BytesIO()
    Image.fromarray(noise, mode="L").save(buffer, format="PNG")

    started = time.perf_counter()
    with pytest.raises(ValueError, match="cell_mm"):
        _trace(buffer.getvalue())
    assert time.perf_counter() - started < 10.0, "the skeleton cap did not fire before the walk started"
