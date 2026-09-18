"""Pencil-sketch outlines: strokes along brightness changes, not tone bands.

contour() answers "how dark is it here" and draws threshold-band boundaries; trace()
follows dark strokes that already exist in the source and fails on a photograph, which has
none. This mode answers a third question -- "where does the brightness change" -- with a
small from-scratch Canny: blur, Sobel gradient, non-maximum suppression, hysteresis
threshold. The result is a 1px edge mask, which is exactly the shape trace()'s machinery
already knows how to turn into strokes (_thin, _walk_skeleton, _stitch, simplify_polyline),
so it is reused rather than re-implemented here.
"""

from __future__ import annotations

import math

import numpy as np
from PIL import Image, ImageFilter

from ..modes import (
    Polylines,
    ToneGrid,
    _clip_point,
    _smoothed_darkness,
    _stitch,
    _thin,
    _walk_skeleton,
    simplify_polyline,
)

HELP = "Outlines where brightness changes, like a pencil sketch. Best on photos; flat colour gives it nothing, and line art traces both sides of every stroke."

# Mirrors trace()'s MAX_SKELETON_PX_DEFAULT for the same reason: _walk_skeleton is a
# pure-Python loop over every surviving pixel, and the segment cap in tone_to_polylines only
# runs after this function returns.
MAX_EDGE_PX_DEFAULT = 150_000

# Hysteresis growth is bounded rather than looped to a fixed point: each pass is a whole-image
# PIL MaxFilter, and letting weak pixels bridge more than a handful of cells at a time is
# bridging real gaps, not connecting one broken edge. 12 passes reaches any weak pixel within
# 12 cells of a strong one, several times stitch_px's own default reach.
_HYSTERESIS_PASSES = 12


def edges(
    tone: ToneGrid,
    *,
    blur_px: float = 1.2,
    high_threshold: float = 0.12,
    low_threshold: float = 0.05,
    bold_threshold: float = 0.0,
    pen_width_mm: float = 0.3,
    stitch_px: float = 2.0,
    simplify_px: float = 0.9,
    min_length_mm: float = 0.9,
    min_darkness: float = 0.05,
    max_edge_px: int = MAX_EDGE_PX_DEFAULT,
) -> Polylines:
    """Blur, Sobel, non-max suppression, hysteresis -- then trace the surviving 1px ridge.

    blur_px matters for the same reason it does in hatch(): a resampled source jitters
    darkness cell to cell, and an un-smoothed gradient turns that jitter into a fence of
    1-cell edge crumbs instead of the drawing's real outlines. Sobel gives a gradient
    magnitude and direction at every cell; non-maximum suppression keeps only the ridge
    pixel along that direction, which is what makes the mask thin enough to skeletonize
    cleanly instead of leaving a blob for _thin to chew through. Hysteresis then keeps every
    pixel over high_threshold and any pixel over low_threshold connected to one, the same
    two-threshold trick Canny uses to keep a wavering strong edge from fraying into dashes
    wherever it dips just under a single threshold.

    high_threshold and low_threshold are gradient magnitude in the same 0..1 darkness units
    as min_darkness elsewhere in this file: the Sobel response is normalised by 4 (one side
    of the kernel's weight), so a full white-to-black step spanning one cell reads as 1.0.

    bold_threshold repeats a stroke offset by one pen width when its mean edge strength
    clears that bar, so a hard silhouette prints heavier than a soft one -- the same idea as
    trace()'s weight_passes, done as a single flat offset instead of a width-proportional
    fill, because there is no source stroke width here to measure.

    stitch_px stays small (trace's own default is 10) because this mode's NMS ridge is not
    perfectly 1px on every curve -- a tightly curved contour can throw a spurious junction
    where the local gradient direction turns faster than one cell, which _walk_skeleton reads
    as two chains meeting at that exact pixel. stitch_px only needs to be big enough to rejoin
    chains that already share an endpoint; measured on a real photo, 10 was big enough to also
    reach genuinely unrelated fragments across the frame and stitch them into one crossing,
    zigzagging stroke, while 2 rejoins the junction breaks and nothing else.

    A field with no internal gradient anywhere (uniform paper, a flat wash) has nothing for
    Sobel to find, and min_darkness keeps that silent rather than noisy. The one exception is
    a field that is both flat AND at or above the ink floor -- a solid dark card has no edge
    to trace inside it but is still visibly there, so it falls back to a single stroke around
    the sheet instead of leaving the page blank. That fallback never fires on a real photo,
    which always has some texture; it exists only for the perfectly uniform case.
    """
    if blur_px < 0:
        raise ValueError("blur_px must be non-negative")
    if not (0.0 < low_threshold < high_threshold):
        raise ValueError("thresholds must satisfy 0 < low_threshold < high_threshold")
    if bold_threshold < 0:
        raise ValueError("bold_threshold must be non-negative")
    if pen_width_mm <= 0:
        raise ValueError("pen_width_mm must be positive")
    if stitch_px < 0 or simplify_px < 0:
        raise ValueError("stitch_px and simplify_px must be non-negative")
    if min_length_mm < 0:
        raise ValueError("min_length_mm must be non-negative")
    if min_darkness < 0:
        raise ValueError("min_darkness must be non-negative")
    if max_edge_px <= 0:
        raise ValueError("max_edge_px must be positive")

    smoothed = _smoothed_darkness(tone.darkness, blur_px)

    if float(np.ptp(smoothed)) < 1e-9:
        # A uniform field has no edge to draw, whatever its darkness.
        return []

    magnitude, edge_mask = _canny_mask(smoothed, high_threshold, low_threshold, min_darkness)
    if not edge_mask.any():
        return []

    skeleton = _thin(edge_mask)
    edge_px = int(skeleton.sum())
    if edge_px > max_edge_px:
        raise ValueError(
            f"edges found {edge_px} edge pixels, exceeding max_edge_px={max_edge_px}; "
            "increase cell_mm, or raise high_threshold/low_threshold"
        )
    if not edge_px:
        return []

    chains = _walk_skeleton(skeleton)
    chains = _stitch(chains, stitch_px)

    rows, cols = smoothed.shape
    polylines: Polylines = []
    for chain in chains:
        simplified = simplify_polyline(chain, simplify_px)
        if len(simplified) < 2:
            continue
        points_mm = [
            _clip_point(((x + 0.5) * tone.cell_mm, (y + 0.5) * tone.cell_mm), tone.width_mm, tone.height_mm)
            for y, x in simplified
        ]
        if _length_mm(points_mm) < min_length_mm:
            continue
        polylines.append(points_mm)

        if bold_threshold <= 0:
            continue
        strengths = [
            float(magnitude[min(rows - 1, max(0, round(y))), min(cols - 1, max(0, round(x)))]) for y, x in simplified
        ]
        if sum(strengths) / len(strengths) < bold_threshold:
            continue
        offset = [
            _clip_point(point, tone.width_mm, tone.height_mm) for point in _offset_polyline(points_mm, pen_width_mm)
        ]
        if _length_mm(offset) >= min_length_mm:
            polylines.append(offset)

    return polylines


def quality_params(spacing_mm: float) -> dict[str, float | int]:
    """Finer quality lowers the thresholds and the blur together, within the segment caps.

    The quality fader's coarser steps also pick a LARGER cell_mm (see TONE_CELL_MM in
    gui/workspaces/image.py), and resampling onto a coarser grid is itself a low-pass filter:
    measured on the dense test drawing, the achievable gradient magnitude at cell 1.5mm tops
    out around 0.17-0.23 versus 0.5-0.6 at cell 0.4mm. Scaling blur_px and the thresholds up
    steeply for draft the way a naive "coarser == blurrier and choosier" reading suggests
    compounds with that resampling and erases the signal entirely -- draft measured zero
    strokes on the dense drawing before this was tuned down. The ranges below stay inside the
    headroom actually available at each cell size, so draft still draws the boldest outlines
    and only max reaches for the faint ones -- factor 0 at spacing_mm 1.0 (max) up to 1 at
    spacing_mm 2.5 (draft); spacing_mm 1.6 (balanced, factor 0.4) reproduces this module's own
    defaults.
    """
    factor = (spacing_mm - 1.0) / 1.5
    high = 0.09 + 0.07 * factor
    return {
        "blur_px": round(1.0 + 0.4 * factor, 3),
        "high_threshold": round(high, 4),
        "low_threshold": round(high * 0.4, 4),
        "simplify_px": round(0.6 + 0.8 * factor, 3),
        "min_length_mm": round(0.6 + 0.8 * factor, 3),
    }


def _canny_mask(
    smoothed: np.ndarray,
    high_threshold: float,
    low_threshold: float,
    min_darkness: float,
) -> tuple[np.ndarray, np.ndarray]:
    """Sobel magnitude/direction, non-maximum suppression, then hysteresis -- no scipy.

    The Sobel pass pads by replicating the border. A constant-0 pad treated the world past
    the picture as blank paper, so every picture whose edge is not white -- most photos, every
    cropped grid cell -- got a rectangle drawn around it that is not in the picture. The NMS pass pads
    the *magnitude* array by replication instead, purely so the 8-neighbour comparison does
    not wrap a pixel on one edge of the grid around to compare against the opposite edge --
    replication makes a border pixel compare against a copy of itself and pass on a tie,
    which is what "no information past the edge" should mean for a max test.
    """
    rows, cols = smoothed.shape
    padded = np.pad(smoothed, 1, mode="edge")

    def neighbours(source: np.ndarray) -> dict[str, np.ndarray]:
        return {
            "nw": source[0:rows, 0:cols],
            "n": source[0:rows, 1 : cols + 1],
            "ne": source[0:rows, 2 : cols + 2],
            "w": source[1 : rows + 1, 0:cols],
            "e": source[1 : rows + 1, 2 : cols + 2],
            "sw": source[2 : rows + 2, 0:cols],
            "s": source[2 : rows + 2, 1 : cols + 1],
            "se": source[2 : rows + 2, 2 : cols + 2],
        }

    tone_nb = neighbours(padded)
    gx = (tone_nb["ne"] + 2 * tone_nb["e"] + tone_nb["se"]) - (tone_nb["nw"] + 2 * tone_nb["w"] + tone_nb["sw"])
    gy = (tone_nb["sw"] + 2 * tone_nb["s"] + tone_nb["se"]) - (tone_nb["nw"] + 2 * tone_nb["n"] + tone_nb["ne"])
    raw_magnitude = np.hypot(gx, gy)
    # Normalise by the one-sided kernel weight (1+2+1=4): a full white-to-black step spanning
    # one cell then reads as magnitude 1.0, the same darkness units the thresholds use.
    magnitude = raw_magnitude / 4.0

    # Snapping the gradient direction to 4 fixed buckets (0/45/90/135) before comparing to the
    # nearest pixel in that bucket looked like the standard textbook NMS, but measured on both
    # a clean synthetic 30-degree edge and a real photo, it left 29-50% of the surviving ridge
    # at degree >= 3 -- not corners, just ordinary straight diagonal edges, because a curve's
    # angle drifts across a bucket boundary and the two neighbouring pixels then get compared
    # against DIFFERENT neighbour pairs, occasionally letting both survive side by side. That
    # 2px-wide ridge reads to _thin() as real structure, throws a junction at every such spot,
    # and shatters what should be one long contour into thousands of ~2px fragments -- which
    # _stitch then reconnects across the whole image into the crossing zigzags this mode
    # originally rendered. Comparing against the exact gradient direction instead, via
    # bilinear interpolation between the four pixels straddling it, removes the quantisation
    # rather than papering over it, and is the standard fix (this is what Canny actually
    # specifies; the 4-bucket version is a common simplification, not the original).
    safe_raw_magnitude = np.where(raw_magnitude > 1e-9, raw_magnitude, 1.0)
    row_index, col_index = np.indices(magnitude.shape)
    step_y, step_x = gy / safe_raw_magnitude, gx / safe_raw_magnitude
    forward = _bilinear_sample(magnitude, row_index + step_y, col_index + step_x)
    backward = _bilinear_sample(magnitude, row_index - step_y, col_index - step_x)
    is_max = (magnitude > 1e-9) & (magnitude >= forward) & (magnitude >= backward)
    thinned = np.where(is_max, magnitude, 0.0)

    dark_enough = smoothed >= min_darkness
    strong = (thinned >= high_threshold) & dark_enough
    weak = (thinned >= low_threshold) & dark_enough & ~strong

    edge_mask = strong.copy()
    for _ in range(_HYSTERESIS_PASSES):
        grown = _dilate(edge_mask) & weak & ~edge_mask
        if not grown.any():
            break
        edge_mask |= grown

    return magnitude, edge_mask


def _bilinear_sample(field: np.ndarray, rows: np.ndarray, cols: np.ndarray) -> np.ndarray:
    """field[rows, cols] at fractional coordinates, clamped to the array like edge-pad would be.

    Plain numpy fancy indexing, not scipy.ndimage.map_coordinates: the two points NMS needs
    per pixel land at a different fractional offset every time (they follow that pixel's own
    gradient direction), so this is a gather, not a convolution -- there is no fixed kernel to
    slide, which is why _smoothed_darkness's PIL blur and the Sobel neighbour slicing above
    cannot do this step.
    """
    row_max, col_max = field.shape[0] - 1, field.shape[1] - 1
    rows = np.clip(rows, 0, row_max)
    cols = np.clip(cols, 0, col_max)
    row0 = np.floor(rows).astype(np.int64)
    col0 = np.floor(cols).astype(np.int64)
    row1 = np.minimum(row0 + 1, row_max)
    col1 = np.minimum(col0 + 1, col_max)
    row_weight = rows - row0
    col_weight = cols - col0
    top = field[row0, col0] * (1 - col_weight) + field[row0, col1] * col_weight
    bottom = field[row1, col0] * (1 - col_weight) + field[row1, col1] * col_weight
    return top * (1 - row_weight) + bottom * row_weight


def _dilate(mask: np.ndarray) -> np.ndarray:
    """One pixel of 8-connected growth, via PIL's MaxFilter -- the same trick _shade_fill uses."""
    return np.asarray(Image.fromarray((mask * 255).astype(np.uint8)).filter(ImageFilter.MaxFilter(3))) > 127


def _length_mm(points: list[tuple[float, float]]) -> float:
    return sum(math.dist(points[index], points[index + 1]) for index in range(len(points) - 1))


def _offset_polyline(points: list[tuple[float, float]], offset_mm: float) -> list[tuple[float, float]]:
    """Shift a stroke sideways by a constant offset, perpendicular to its local tangent.

    A flat single-width offset rather than trace()'s per-point taper: there is no source
    stroke width to reproduce here, only an edge that is either bold or is not, so one extra
    parallel pass is the whole story.
    """
    count = len(points)
    shifted: list[tuple[float, float]] = []
    for index in range(count):
        x, y = points[index]
        ahead_x, ahead_y = points[min(index + 1, count - 1)]
        behind_x, behind_y = points[max(index - 1, 0)]
        dx, dy = ahead_x - behind_x, ahead_y - behind_y
        length = math.hypot(dx, dy) or 1.0
        shifted.append((x - offset_mm * (dy / length), y + offset_mm * (dx / length)))
    return shifted
