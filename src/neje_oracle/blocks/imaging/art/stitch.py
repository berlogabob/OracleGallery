"""Cross-stitch embroidery: a grid of aida cells, each holding an X of two crossing strokes.

Tone decides whether a cell is stitched at all (a gate, like every other tone mode here) and
how heavy its stitch is: nothing where light, one X where mid, a retraced (bolder) X where
darkest. Nothing is free-form -- every stroke endpoint is a cell corner, which is what reads
as "counted" needlework rather than a sketch.

The embroiderer's own trick for a row of stitches is what keeps this cheap to plot: work every
cell's "/" half in one pass along the row (thread travels under the fabric between cells, which
here becomes a short connector along the shared cell edge, not a pen lift), then the "\" half on
the way back. A run of N stitched cells in a row is therefore 2 polylines, not 2N -- see
`_forward_chain` / `_return_chain` for the corner arithmetic that makes each pass one unbroken
zigzag: cell c's far corner is exactly cell c+1's near corner, by construction of a shared grid
line, so listing corners in cell order needs no explicit "connect these" step at all.
"""

from __future__ import annotations

import math

from ..modes import Polylines, ToneGrid, _clip_point, _stitch, cell_darkness

HELP = "Cross-stitch embroidery: an X per grid cell, none where light, doubled where darkest. detail = cell size in mm."

MAX_STITCHES_DEFAULT = 100_000
# Endpoints are computed identically by every cell that shares a corner (same stitch_mm, same
# col/row arithmetic), so the only slack a join needs is float rounding -- the same reasoning
# truchet's _JOIN_TOLERANCE_MM documents.
_JOIN_TOLERANCE_MM = 1e-6
# A retraced X is invisible in a flat polyline render -- two passes over the exact same two
# points draw the exact same line, which is what a first render of this mode showed: the whole
# gated area came out as one uniform density of Xs, tone unreadable, exactly the failure mode
# the task brief calls "cancelling". A bold cell instead nests a SECOND, slightly inset X inside
# the first (tier k inset by k * _BOLD_INSET_FRACTION * stitch_mm), which is what an eye actually
# reads as "more thread here": two close concentric Xs read as a bolder cross the way a doubled
# strand does in real cross-stitch, and it survives being flattened to thin lines. 0.12 keeps
# even a 3-tier ladder's innermost X comfortably short of crossing itself (margin < stitch_mm/2).
_BOLD_INSET_FRACTION = 0.12


def stitch(
    tone: ToneGrid,
    *,
    stitch_mm: float = 3.0,
    min_darkness: float = 0.12,
    max_weight: int = 2,
    max_stitches: int = MAX_STITCHES_DEFAULT,
) -> Polylines:
    """Lay a grid of X stitches, retraced up to max_weight times where the cell is dark.

    Weight. Each cell's mean darkness (`cell_darkness`, area-averaged over its own footprint,
    not a point sample) is gated at min_darkness, then the PASSING cells' own min..max is
    stretched onto [0, 1] before mapping to a weight in [1, max_weight] -- the same contrast
    fix `ascii._char_grid` and `matrix.matrix` apply, and for the same reason: an area-averaged
    photo rarely reaches the true darkness extremes, so mapping raw darkness straight onto the
    weight ramp would render most of a real image at a single middle weight. min_darkness
    defaults to 0.12 (well above `hatch`'s usual 0.05) so a near-white background stays
    unstitched cloth rather than a faint wash of pale Xs.

    Weight beyond 1 nests a smaller, inset X inside the previous one rather than retracing the
    same two points -- see `_BOLD_INSET_FRACTION` for why. Every base X still lands exactly on
    the cell's own corners; only the extra nested passes sit a small, fixed fraction of stitch_mm
    inside them, which is the "within a tolerance" the grid test below allows for.

    Row batching. For each row and each weight tier, the cells that clear that tier are split
    into maximal runs of consecutive columns; each run becomes exactly 2 polylines (the "/"
    pass forward, the "\\" pass back -- see the module docstring), not 2 strokes per cell. A
    final `_stitch` pass joins whatever these chains still share an endpoint with (row to row,
    tier to tier), which is silent wherever they do not.

    max_stitches guards the one place this mode can explode: a small stitch_mm on a big sheet is
    a cols*rows blow-up worth catching before a single corner is computed.
    """
    if stitch_mm <= 0:
        raise ValueError("stitch_mm must be positive")
    if not 0.0 <= min_darkness <= 1.0:
        raise ValueError("min_darkness must be between 0 and 1")
    if max_weight < 1:
        raise ValueError("max_weight must be at least 1")
    if max_stitches < 1:
        raise ValueError("max_stitches must be at least 1")

    cols = max(1, int(tone.width_mm / stitch_mm))
    rows = max(1, int(tone.height_mm / stitch_mm))
    if rows * cols > max_stitches:
        raise ValueError(
            f"stitch would need {rows * cols} cells, exceeding max_stitches={max_stitches}; "
            "increase stitch_mm or reduce the drawing size"
        )

    weight = _weight_grid(tone, cols, rows, stitch_mm, min_darkness, max_weight)

    chains: Polylines = []
    for row in range(rows):
        for tier in range(max_weight):
            margin_mm = tier * _BOLD_INSET_FRACTION * stitch_mm
            run_cols = [col for col in range(cols) if weight[row][col] > tier]
            for run in _runs(run_cols):
                chains.append(_forward_chain(run, row, stitch_mm, margin_mm))
                chains.append(_return_chain(run, row, stitch_mm, margin_mm))

    joined = _stitch(chains, _JOIN_TOLERANCE_MM)
    return [[_clip_point(point, tone.width_mm, tone.height_mm) for point in polyline] for polyline in joined]


# A 4x4 ordered-dither matrix, thresholds spread over (0, 1). Ordered rather than random so
# the unstitched cells fall in a regular pattern -- counted needlework is regular, and random
# holes read as mistakes.
_BAYER = tuple(
    tuple((value + 0.5) / 16.0 for value in row)
    for row in ((0, 8, 2, 10), (12, 4, 14, 6), (3, 11, 1, 9), (15, 7, 13, 5))
)


def _weight_grid(
    tone: ToneGrid, cols: int, rows: int, stitch_mm: float, min_darkness: float, max_weight: int
) -> list[list[int]]:
    """0 (unstitched) or a stretched-and-quantised 1..max_weight per cell."""
    raw = [
        [
            cell_darkness(
                tone.darkness,
                col * stitch_mm,
                row * stitch_mm,
                (col + 1) * stitch_mm,
                (row + 1) * stitch_mm,
                tone.width_mm,
                tone.height_mm,
            )
            for col in range(cols)
        ]
        for row in range(rows)
    ]
    passing = [value for line in raw for value in line if value >= min_darkness]
    low, high = (min(passing), max(passing)) if passing else (0.0, 0.0)
    spread = high - low

    def normalized(value: float) -> float:
        return (value - low) / spread if spread > 1e-9 else value

    # Weight alone cannot carry tone here: a cell is either stitched or not, and a stitched
    # cell at weight 1 lays nearly as much thread as one at weight 2, so an unfiltered grid
    # comes out as solid cross-stitch everywhere above the gate (measured: a 1.9:1 slope
    # across the whole tonal range, which reads as binary). An ordered dither decides WHETHER
    # a cell is worked at all, the way a sampler leaves cloth bare to shade a motif, and that
    # is what puts real gradation between the gate and full coverage.
    return [
        [
            0
            if value < min_darkness or normalized(value) < _BAYER[row % 4][col % 4]
            else max(1, min(max_weight, math.ceil(normalized(value) * max_weight)))
            for col, value in enumerate(line)
        ]
        for row, line in enumerate(raw)
    ]


def _runs(columns: list[int]) -> list[list[int]]:
    """Split a sorted column list into maximal runs of consecutive integers."""
    runs: list[list[int]] = []
    for col in columns:
        if runs and col == runs[-1][-1] + 1:
            runs[-1].append(col)
        else:
            runs.append([col])
    return runs


def _forward_chain(run: list[int], row: int, stitch_mm: float, margin_mm: float = 0.0) -> list[tuple[float, float]]:
    """The "/" pass across a run: bottom-left to top-right of each cell, left to right.

    At margin_mm=0, cell c's top-right corner is ((c+1)*stitch_mm, row*stitch_mm) and cell c+1's
    bottom-left corner is ((c+1)*stitch_mm, (row+1)*stitch_mm) -- same x, the shared boundary
    between the two cells -- so appending each cell's (bottom-left, top-right) pair in column
    order draws one continuous zigzag with no separate "connect these" step: the connector IS
    the segment between one cell's pair and the next. margin_mm > 0 (a bold tier's nested X)
    pulls every point the same distance inward, which keeps the run chained -- just no longer
    on the exact shared boundary -- see _BOLD_INSET_FRACTION.
    """
    points: list[tuple[float, float]] = []
    for col in run:
        points.append((col * stitch_mm + margin_mm, (row + 1) * stitch_mm - margin_mm))
        points.append(((col + 1) * stitch_mm - margin_mm, row * stitch_mm + margin_mm))
    return points


def _return_chain(run: list[int], row: int, stitch_mm: float, margin_mm: float = 0.0) -> list[tuple[float, float]]:
    """The "\\" pass across the same run, walked back right to left -- the embroiderer's return leg.

    Built the same way as `_forward_chain` (top-left to bottom-right of each cell, left to
    right, chaining on the shared boundary the same way), then reversed so the stroke actually
    runs backward across the row -- ending the pass near where the row started rather than
    where it finished.
    """
    points: list[tuple[float, float]] = []
    for col in run:
        points.append((col * stitch_mm + margin_mm, row * stitch_mm + margin_mm))
        points.append(((col + 1) * stitch_mm - margin_mm, (row + 1) * stitch_mm - margin_mm))
    points.reverse()
    return points


def quality_params(spacing_mm: float) -> dict[str, float]:
    """Map the shared quality fader onto stitch_mm, truchet's own move and for the same reason.

    1.2x tracks the fader from a 3.0 mm cell at draft (spacing 2.5) down to 1.2 mm at max
    (spacing 1.0). The floor at 1.2 mm is the "a few nib widths" line: at the 0.3 mm default
    pen width (PEN_WIDTH_MM_DEFAULT in modes.py) a stitch diagonal is stitch_mm * sqrt(2) long,
    so 1.2 mm still draws a ~1.7 mm X -- well clear of a blot -- while every finer fader step
    still shrinks stitch_mm, so still adds detail, exactly as the fader promises.
    """
    if spacing_mm <= 0:
        raise ValueError("spacing_mm must be positive")
    return {"stitch_mm": max(1.2, spacing_mm * 1.2)}
