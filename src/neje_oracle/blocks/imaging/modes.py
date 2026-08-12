from __future__ import annotations

import io
import math
from collections import defaultdict
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from typing import Any

import numpy as np
from PIL import Image, ImageFilter, ImageOps, UnidentifiedImageError

Polylines = list[list[tuple[float, float]]]

MAX_SEGMENTS_DEFAULT = 40_000


@dataclass(frozen=True)
class ToneGrid:
    darkness: np.ndarray
    cell_mm: float
    width_mm: float
    height_mm: float


def load_tone(
    data: bytes,
    *,
    width_mm: float,
    height_mm: float,
    cell_mm: float,
    invert: bool = False,
    gamma: float = 1.0,
    levels: int | None = None,
    autocontrast: bool = True,
) -> ToneGrid:
    if width_mm <= 0 or height_mm <= 0 or cell_mm <= 0:
        raise ValueError("width_mm, height_mm, and cell_mm must be positive")
    if gamma <= 0:
        raise ValueError("gamma must be positive")
    if levels is not None and levels < 2:
        raise ValueError("levels must be at least 2")

    try:
        with Image.open(io.BytesIO(data)) as source:
            image = source.convert("L")
            if autocontrast:
                image = ImageOps.autocontrast(image)
            size = (
                max(1, round(width_mm / cell_mm)),
                max(1, round(height_mm / cell_mm)),
            )
            image = image.resize(size, Image.Resampling.LANCZOS)
            luminance = np.asarray(image, dtype=np.float64) / 255.0
    except (OSError, UnidentifiedImageError, ValueError) as error:
        raise ValueError("unable to read raster image data") from error

    darkness = np.power(1.0 - luminance, gamma)
    if levels is not None:
        darkness = np.round(darkness * (levels - 1)) / (levels - 1)
    if invert:
        darkness = 1.0 - darkness
    return ToneGrid(darkness, cell_mm, width_mm, height_mm)


def halftone(
    tone: ToneGrid,
    *,
    min_dot_mm: float = 0.0,
    max_dot_mm: float | None = None,
    angle_deg: float = 45.0,
    sides: int = 0,
    min_ink_mm: float = 0.15,
    min_darkness: float = 0.0,
    pen_width_mm: float = 0.0,
) -> Polylines:
    """Dots on a rotated lattice, radius growing with darkness.

    min_ink_mm is pen calibration, not a segment budget: half the 0.3 mm stroke width
    polylines_to_svg emits. autocontrast lifts scanner/render noise on a white background
    into faint darkness across most of the grid, and a dot smaller than the pen's own line
    is a blot, not a tone. Widen it for a fatter nib.

    min_darkness is the white point, and it is a different guard from min_ink_mm: one asks
    "is this dot too small for the nib", the other asks "is this paper". Expressed in tone,
    min_ink_mm alone gates at (min_ink_mm / (cell_mm/2))**2, which SHRINKS as the dot pitch
    grows -- at the shipped 3 mm pitch that is 1% darkness, so effectively nothing is left
    blank. Measured on the printed sheet: 63% of the frame sat below the 0.18 white point but
    only 35% below 1%, so a quarter of the paper was inked with dots that carried no image,
    and the subject read as a faint disturbance inside a printed square. Every other tone mode
    already takes this parameter.

    pen_width_mm fixes a tone inversion measured on paper. A dot is drawn as its outline, so
    once the ring is wider than about two pen widths it prints as a donut with bare paper in
    the middle, and the darkest region of an image comes out LIGHTER than its mid-tones. Given
    a pen width, dots past that size are filled with an outward spiral at pen pitch instead —
    still one stroke per dot, so the fix costs no pen lifts, only vertices. Left at 0.0 the
    old hollow ring is kept, because callers that never set it were tuned against it.
    """
    max_radius = tone.cell_mm * 0.5 if max_dot_mm is None else max_dot_mm
    if min_dot_mm < 0 or max_radius < min_dot_mm:
        raise ValueError("dot radii must be non-negative and max_dot_mm >= min_dot_mm")
    if min_ink_mm < 0 or min_darkness < 0:
        raise ValueError("min_ink_mm and min_darkness must be non-negative")
    if sides != 0 and sides < 3:
        raise ValueError("sides must be 0 or at least 3")

    center_x = tone.width_mm / 2.0
    center_y = tone.height_mm / 2.0
    angle = math.radians(angle_deg)
    cosine = math.cos(angle)
    sine = math.sin(angle)
    polylines: Polylines = []

    # Build the lattice over the field's bounding circle, not its bounding box:
    # rotating a box-sized lattice leaves the corners of the sheet bare.
    reach = math.hypot(tone.width_mm, tone.height_mm) / 2.0
    steps = int(math.ceil(reach / tone.cell_mm))
    for grid_y in range(-steps, steps + 1):
        for grid_x in range(-steps, steps + 1):
            local_x = grid_x * tone.cell_mm
            local_y = grid_y * tone.cell_mm
            dot_x = center_x + local_x * cosine - local_y * sine
            dot_y = center_y + local_x * sine + local_y * cosine
            if not (0 <= dot_x <= tone.width_mm and 0 <= dot_y <= tone.height_mm):
                continue
            darkness = _sample_darkness(tone, dot_x, dot_y)
            if darkness <= 0.0 or darkness < min_darkness:
                continue
            radius = min_dot_mm + (max_radius - min_dot_mm) * math.sqrt(darkness)
            if radius <= 0 or radius < min_ink_mm:
                continue
            # 16 sides at a 1.5 mm radius is already a 0.6 mm edge — finer than the
            # plotter resolves, so more vertices only buy G-code.
            dot_sides = sides or min(
                16,
                4 + round(12 * min(1.0, radius / max(tone.cell_mm * 0.5, 1e-12))),
            )
            if pen_width_mm > 0 and radius > pen_width_mm:
                points = _spiral_dot(dot_x, dot_y, radius, pen_width_mm, dot_sides)
            else:
                points = [
                    (
                        dot_x + radius * math.cos(math.tau * index / dot_sides),
                        dot_y + radius * math.sin(math.tau * index / dot_sides),
                    )
                    for index in range(dot_sides)
                ]
                points.append(points[0])
            polylines.append([_clip_point(point, tone.width_mm, tone.height_mm) for point in points])
    return polylines


def _spiral_dot(
    center_x: float, center_y: float, radius: float, pitch_mm: float, sides: int
) -> list[tuple[float, float]]:
    """One continuous outward spiral filling a dot, then a closing ring at full radius.

    The ring alone leaves the middle bare. Winding out at pen pitch inks the whole disc in a
    single stroke, so the dot reads as solid at the dark end without adding a pen lift.
    """
    turns = max(1, int(math.ceil(radius / max(pitch_mm, 1e-6))))
    steps = max(sides, turns * sides)
    points = [
        (
            center_x + radius * (index / steps) * math.cos(math.tau * turns * index / steps),
            center_y + radius * (index / steps) * math.sin(math.tau * turns * index / steps),
        )
        for index in range(steps + 1)
    ]
    points.extend(
        (
            center_x + radius * math.cos(math.tau * index / sides),
            center_y + radius * math.sin(math.tau * index / sides),
        )
        for index in range(sides + 1)
    )
    return points


def _smoothed_darkness(darkness: np.ndarray, blur_px: float) -> np.ndarray:
    """Gaussian-blur a darkness field. Shared by flow and hatch, which both need it."""
    if blur_px <= 0:
        return darkness
    return (
        np.asarray(
            Image.fromarray((np.clip(darkness, 0, 1) * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(blur_px)),
            dtype=np.float64,
        )
        / 255.0
    )


def hatch(
    tone: ToneGrid,
    *,
    line_spacing_mm: float = 1.0,
    angle_deg: float = 0.0,
    wavy: bool = False,
    amplitude_mm: float = 0.4,
    min_darkness: float = 0.05,
    blur_px: float = 2.0,
) -> Polylines:
    """Parallel scanlines whose density carries tone.

    blur_px smooths the field before the walk, and it is not cosmetic. A run breaks wherever a
    sample falls under that scanline's threshold, so a resampled source -- whose darkness
    jitters cell to cell -- shatters every line into crumbs. Measured on a real drawing:
    63 strokes of median length 2.1 mm became 23 strokes of median 4.2 mm for the SAME
    158 mm of ink. Strokes are pen lifts, so smoothing is faster and more legible at once,
    with nothing traded. flow already carried its own blur for the same reason.
    """
    if line_spacing_mm <= 0:
        raise ValueError("line_spacing_mm must be positive")
    if amplitude_mm < 0:
        raise ValueError("amplitude_mm must be non-negative")
    if blur_px < 0:
        raise ValueError("blur_px must be non-negative")

    tone = replace(tone, darkness=_smoothed_darkness(tone.darkness, blur_px))
    angle = math.radians(angle_deg)
    direction = (math.cos(angle), math.sin(angle))
    perpendicular = (-direction[1], direction[0])
    center = (tone.width_mm / 2.0, tone.height_mm / 2.0)
    radius = math.hypot(tone.width_mm, tone.height_mm) / 2.0
    polylines: Polylines = []
    offset = -radius + line_spacing_mm / 2.0
    # Tone must come from line DENSITY, not presence: a fixed threshold turns any
    # photo into a solid block, because nearly every pixel clears it. Each scanline
    # gets its own threshold from a rotating ladder, so `levels` greys emerge from
    # how many of every `levels` lines survive at a given darkness.
    levels = max(1, int(round(line_spacing_mm / max(tone.cell_mm, 1e-6))) * 4)
    line_index = 0

    while offset < radius:
        floor = min_darkness + (1.0 - min_darkness) * (line_index % levels) / levels
        line_index += 1
        origin = (
            center[0] + offset * perpendicular[0],
            center[1] + offset * perpendicular[1],
        )
        interval = _line_interval(origin, direction, tone.width_mm, tone.height_mm)
        if interval is not None:
            start, end = interval
            sample_count = max(1, math.ceil((end - start) / tone.cell_mm))
            run: list[tuple[float, float]] = []
            for index in range(sample_count + 1):
                distance = start + (end - start) * index / sample_count
                x = origin[0] + distance * direction[0]
                y = origin[1] + distance * direction[1]
                darkness = _sample_darkness(tone, x, y)
                if darkness < floor:
                    if len(run) >= 2:
                        polylines.append(run)
                    run = []
                    continue
                displacement = math.sin(distance) * amplitude_mm * darkness if wavy else 0.0
                run.append(
                    (
                        _clip(x + displacement * perpendicular[0], 0, tone.width_mm),
                        _clip(y + displacement * perpendicular[1], 0, tone.height_mm),
                    )
                )
            if len(run) >= 2:
                polylines.append(run)
        offset += line_spacing_mm
    return polylines


def flow(
    tone: ToneGrid,
    *,
    min_spacing_mm: float = 0.6,
    max_spacing_mm: float = 3.0,
    white_point: float = 0.12,
    blur_px: float = 2.0,
    step_mm: float = 0.6,
    max_length_mm: float = 40.0,
) -> Polylines:
    """Streamlines that follow the image's iso-tone contours.

    The perpendicular of the darkness gradient runs along equal-tone contours. Following
    it is what makes the lines hug the represented surface instead of sweeping straight
    across the frame, while spacing the lines by darkness carries the shading.
    """
    if min_spacing_mm <= 0 or max_spacing_mm <= 0 or min_spacing_mm > max_spacing_mm:
        raise ValueError("flow spacings must be positive and min_spacing_mm <= max_spacing_mm")
    if step_mm <= 0:
        raise ValueError("step_mm must be positive")

    darkness = tone.darkness
    smoothed = _smoothed_darkness(darkness, blur_px)
    gradient_y, gradient_x = np.gradient(smoothed)
    direction_x, direction_y = -gradient_y, gradient_x
    flat = np.hypot(direction_x, direction_y) < 1e-4
    direction_x[flat], direction_y[flat] = 1.0, 0.0
    magnitude = np.hypot(direction_x, direction_y)
    magnitude[magnitude == 0] = 1.0
    direction_x /= magnitude
    direction_y /= magnitude

    rows, columns = darkness.shape
    occupancy_cell = min_spacing_mm
    occupancy: dict[tuple[int, int], list[tuple[float, float]]] = {}

    def spacing_at(x: float, y: float) -> tuple[float, float]:
        row = min(max(int(y / tone.cell_mm), 0), rows - 1)
        column = min(max(int(x / tone.cell_mm), 0), columns - 1)
        value = float(darkness[row, column])
        return max_spacing_mm + (min_spacing_mm - max_spacing_mm) * min(1.0, value), value

    def free(x: float, y: float, spacing: float) -> bool:
        key = (int(x / occupancy_cell), int(y / occupancy_cell))
        for offset_x in (-2, -1, 0, 1, 2):
            for offset_y in (-2, -1, 0, 1, 2):
                for occupied_x, occupied_y in occupancy.get((key[0] + offset_x, key[1] + offset_y), ()):
                    if math.hypot(occupied_x - x, occupied_y - y) < spacing * 0.9:
                        return False
        return True

    def mark(x: float, y: float) -> None:
        occupancy.setdefault((int(x / occupancy_cell), int(y / occupancy_cell)), []).append((x, y))

    def sample_direction(x: float, y: float) -> tuple[float, float]:
        row = min(max(int(y / tone.cell_mm), 0), rows - 1)
        column = min(max(int(x / tone.cell_mm), 0), columns - 1)
        return float(direction_x[row, column]), float(direction_y[row, column])

    # Fail fast rather than freeze. Seeding is a pure-Python double loop over
    # (width/min_spacing) x (height/min_spacing); on a full 250x440 bed at a fine spacing
    # that is millions of iterations, and the segment cap cannot help because it only runs
    # after this function returns. trace() guards the same way with max_skeleton_px.
    seed_estimate = (tone.width_mm / min_spacing_mm) * (tone.height_mm / min_spacing_mm)
    if seed_estimate > MAX_FLOW_SEEDS:
        raise ValueError(
            f"flow would place {int(seed_estimate)} seeds, exceeding {MAX_FLOW_SEEDS}; "
            "widen min_spacing_mm or reduce the drawing size"
        )

    seeds: list[tuple[float, float, float]] = []
    for row in range(int(tone.height_mm / min_spacing_mm)):
        for column in range(int(tone.width_mm / min_spacing_mm)):
            x = (column + 0.5) * min_spacing_mm
            y = (row + 0.5) * min_spacing_mm
            _, value = spacing_at(x, y)
            if value >= white_point:
                seeds.append((-value, x, y))
    # Dark areas claim their tighter spacing before lighter seeds can crowd them out.
    seeds.sort()

    polylines: Polylines = []
    for _, start_x, start_y in seeds:
        spacing, value = spacing_at(start_x, start_y)
        if value < white_point or not free(start_x, start_y, spacing):
            continue
        path = [(start_x, start_y)]
        # A streamline must not be tested against its own trail: the point marked one step
        # back is always closer than the spacing, so the line would stop dead after a single
        # step. Only in dark regions, where the spacing shrinks below step_mm, did it escape
        # at all — which looked like "highlights stay blank" and was really self-collision.
        # So the line is checked against committed neighbours and commits itself at the end.
        pending: list[tuple[float, float]] = [(start_x, start_y)]
        for sign in (1, -1):
            x, y = start_x, start_y
            travelled = 0.0
            side: list[tuple[float, float]] = []
            while travelled < max_length_mm / 2:
                direction_dx, direction_dy = sample_direction(x, y)
                x += sign * direction_dx * step_mm
                y += sign * direction_dy * step_mm
                travelled += step_mm
                if not (0 <= x <= tone.width_mm and 0 <= y <= tone.height_mm):
                    break
                next_spacing, next_value = spacing_at(x, y)
                if next_value < white_point or not free(x, y, next_spacing * 0.55):
                    break
                side.append((x, y))
                pending.append((x, y))
            path = path + side if sign == 1 else side[::-1] + path
        for point_x, point_y in pending:
            mark(point_x, point_y)
        if len(path) >= 2:
            polylines.append(path)
    return polylines


def dither(
    tone: ToneGrid,
    *,
    method: str = "floyd",
    dot_mm: float | None = None,
    chain_gap_mm: float = 0.0,
) -> Polylines:
    """Dither tone into dots, optionally chaining nearby dot centres within rows.

    Each dot is otherwise its own pen lift: one photo produced 77 129 strokes, about
    41 hours, with nearly all of that time spent lifting and dropping the pen.
    """
    size = tone.cell_mm * 0.6 if dot_mm is None else dot_mm
    if size < 0:
        raise ValueError("dot_mm must be non-negative")
    values = np.rint(tone.darkness * 255).astype(np.uint8)
    if method == "floyd":
        pixels = np.asarray(Image.fromarray(values, mode="L").convert("1"), dtype=bool)
    elif method == "bayer":
        bayer = np.array(
            [
                [0, 48, 12, 60, 3, 51, 15, 63],
                [32, 16, 44, 28, 35, 19, 47, 31],
                [8, 56, 4, 52, 11, 59, 7, 55],
                [40, 24, 36, 20, 43, 27, 39, 23],
                [2, 50, 14, 62, 1, 49, 13, 61],
                [34, 18, 46, 30, 33, 17, 45, 29],
                [10, 58, 6, 54, 9, 57, 5, 53],
                [42, 26, 38, 22, 41, 25, 37, 21],
            ],
            dtype=np.float64,
        )
        rows, cols = tone.darkness.shape
        threshold = np.tile((bayer + 0.5) / 64.0, ((rows + 7) // 8, (cols + 7) // 8))
        pixels = tone.darkness > threshold[:rows, :cols]
    else:
        raise ValueError("unknown dither method; valid methods: bayer, floyd")
    if size == 0:
        return []

    rows, cols = tone.darkness.shape
    step_x = tone.width_mm / cols
    step_y = tone.height_mm / rows
    radius = size / 2.0
    polylines: Polylines = []
    dots = np.argwhere(pixels)
    if chain_gap_mm > 0:
        centres: dict[int, list[tuple[float, float]]] = defaultdict(list)
        for row, col in dots:
            centre = ((float(col) + 0.5) * step_x, (float(row) + 0.5) * step_y)
            # Key on the row index itself. Recovering it as round(centre_y / step_y) looks
            # equivalent but is not: that is round(row + 0.5), and banker's rounding sends
            # rows 1 and 2 both to 2, 3 and 4 both to 4. Adjacent rows then merged into one
            # "row", so most chains zigzagged between two rows and the serpentine
            # alternation was indexed over merged buckets rather than real rows.
            centres[int(row)].append(centre)
        for row_number, row_centres in enumerate(centres[key] for key in sorted(centres)):
            row_centres.sort(key=lambda point: point[0], reverse=row_number % 2 == 1)
            run: list[tuple[float, float]] = []
            for centre in row_centres:
                if run and abs(centre[0] - run[-1][0]) > chain_gap_mm:
                    if len(run) >= 2:
                        polylines.append(run)
                    run = []
                run.append(centre)
            if len(run) >= 2:
                polylines.append(run)
        return polylines

    for row, col in dots:
        x = (float(col) + 0.5) * step_x
        y = (float(row) + 0.5) * step_y
        points = [
            (x, _clip(y - radius, 0, tone.height_mm)),
            (_clip(x + radius, 0, tone.width_mm), y),
            (x, _clip(y + radius, 0, tone.height_mm)),
            (_clip(x - radius, 0, tone.width_mm), y),
        ]
        polylines.append(points + [points[0]])
    return polylines


_MARCHING_CASES: tuple[tuple[tuple[int, int], ...], ...] = (
    (),
    ((3, 0),),
    ((0, 1),),
    ((3, 1),),
    ((1, 2),),
    ((3, 0), (1, 2)),
    ((0, 2),),
    ((3, 2),),
    ((2, 3),),
    ((0, 2),),
    ((0, 1), (2, 3)),
    ((1, 2),),
    ((3, 1),),
    ((0, 1),),
    ((3, 0),),
    (),
)


def contour(tone: ToneGrid, *, bands: int = 4, smooth: bool = True) -> Polylines:
    if bands <= 0:
        raise ValueError("bands must be positive")
    minimum = float(np.min(tone.darkness))
    maximum = float(np.max(tone.darkness))
    if minimum == maximum:
        return []

    rows, cols = tone.darkness.shape
    step_x = tone.width_mm / cols
    step_y = tone.height_mm / rows
    x_coordinates = np.concatenate(([-step_x / 2], (np.arange(cols) + 0.5) * step_x, [tone.width_mm + step_x / 2]))
    y_coordinates = np.concatenate(([-step_y / 2], (np.arange(rows) + 0.5) * step_y, [tone.height_mm + step_y / 2]))
    padded = np.pad(tone.darkness, 1, constant_values=minimum - (maximum - minimum))
    polylines: Polylines = []

    for level in np.linspace(minimum, maximum, bands + 2)[1:-1]:
        segments: list[tuple[tuple[float, float], tuple[float, float]]] = []
        cases = (
            (padded[:-1, :-1] >= level).astype(np.uint8)
            + 2 * (padded[:-1, 1:] >= level)
            + 4 * (padded[1:, 1:] >= level)
            + 8 * (padded[1:, :-1] >= level)
        )
        for row, col in np.argwhere((cases != 0) & (cases != 15)):
            top_left = float(padded[row, col])
            top_right = float(padded[row, col + 1])
            bottom_right = float(padded[row + 1, col + 1])
            bottom_left = float(padded[row + 1, col])
            x0 = float(x_coordinates[col])
            x1 = float(x_coordinates[col + 1])
            y0 = float(y_coordinates[row])
            y1 = float(y_coordinates[row + 1])
            edges = (
                _interpolate((x0, y0), (x1, y0), top_left, top_right, level),
                _interpolate((x1, y0), (x1, y1), top_right, bottom_right, level),
                _interpolate((x1, y1), (x0, y1), bottom_right, bottom_left, level),
                _interpolate((x0, y1), (x0, y0), bottom_left, top_left, level),
            )
            for first, second in _MARCHING_CASES[int(cases[row, col])]:
                start = _clip_point(edges[first], tone.width_mm, tone.height_mm)
                end = _clip_point(edges[second], tone.width_mm, tone.height_mm)
                if _point_key(start) != _point_key(end):
                    segments.append((start, end))
        runs = _join_segments(segments)
        polylines.extend(_chaikin(run) if smooth else run for run in runs)
    return polylines


_NEIGHBOUR_OFFSETS = ((-1, 0), (-1, 1), (0, 1), (1, 1), (1, 0), (1, -1), (0, -1), (-1, -1))
MAX_SKELETON_PX_DEFAULT = 150_000
PEN_WIDTH_MM_DEFAULT = 0.3
MAX_WEIGHT_PASSES = 6
# trace() overrides for AI-generated line art. Its shipped defaults were swept on scans and
# renders whose line weight means something; a diffusion model's output is a different animal
# and pays for that difference in pen lifts. Measured over five ComfyUI renders at 150 mm,
# 0.3 mm pen, cell 0.15: 673 strokes / 24.5 min collapse to 64 strokes / 4.1 min, for F
# 0.999 -> 0.990. Six times the plot speed, worth a look change on this one source and
# nothing else, which is why it is a profile the caller opts into and not a new default.
#   - weight_passes off is almost all of it. Filling a bold stroke with a thin nib is right
#     when the boldness is the artist's; here it is the sampler's, and reproducing it costs
#     ~1.8 s of Z per extra pass. Everything plots at one nib width, which is what one pen is.
#   - despeckling flips sign here. It ships off because on hatched scans the specks ARE the
#     hatching (F 0.905 -> 0.877); with the weight passes gone, what is left under 8 points
#     is sampler noise, and dropping it halves strokes again for F 0.991 -> 0.990.
# threshold deliberately stays at the default. 0.8 plots ~30% faster still, but it breaks
# thin light strokes into dashes — every boat in the sweep came out with a dotted mast.
AI_LINE_ART_TRACE: dict[str, Any] = {"weight_passes": False, "despeckle_px": 8}
# A 250x440 bed at 0.3 mm spacing is 1.2M seeds of pure-Python loop; this stops flow
# freezing the preview before the segment cap ever gets a chance to reject the result.
MAX_FLOW_SEEDS = 400_000
MAX_SPIRAL_POINTS = 400_000
MAX_STIPPLE_POINTS = 400_000
MAX_SQUIGGLE_POINTS = 400_000


def _shifted(mask: np.ndarray) -> list[np.ndarray]:
    """P2..P9 of the Zhang-Suen neighbourhood, clockwise from north."""
    return [np.roll(np.roll(mask, dy, 0), dx, 1) for dy, dx in _NEIGHBOUR_OFFSETS]


def _thin(mask: np.ndarray, max_iter: int = 40) -> np.ndarray:
    """Zhang-Suen thinning: erode strokes to a one-pixel skeleton, keeping connectivity.

    Vectorised over the whole grid — the per-pixel form is the textbook one but is ~1000x
    slower in Python. Measured at 0.05 s on a 1000x1000 grid.
    """
    thinned = mask.copy()
    for _ in range(max_iter):
        changed = False
        for sub_iteration in (0, 1):
            p = _shifted(thinned)
            neighbours = sum(part.astype(np.uint8) for part in p)
            ring = [*p, p[0]]
            crossings = sum(((~ring[i]) & ring[i + 1]).astype(np.uint8) for i in range(8))
            if sub_iteration == 0:
                first, second = ~(p[0] & p[2] & p[4]), ~(p[2] & p[4] & p[6])
            else:
                first, second = ~(p[0] & p[2] & p[6]), ~(p[0] & p[4] & p[6])
            doomed = thinned & (neighbours >= 2) & (neighbours <= 6) & (crossings == 1) & first & second
            if doomed.any():
                thinned &= ~doomed
                changed = True
        if not changed:
            break
    return thinned


def _walk_skeleton(skeleton: np.ndarray) -> list[list[tuple[int, int]]]:
    """Split a 1px skeleton into chains of (row, col), in pen-stroke order."""
    points = set(map(tuple, np.argwhere(skeleton)))
    steps = ((-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1))

    def around(point: tuple[int, int]) -> list[tuple[int, int]]:
        return [n for n in ((point[0] + dy, point[1] + dx) for dy, dx in steps) if n in points]

    degree = {point: len(around(point)) for point in points}
    unused = set(points)
    chains: list[list[tuple[int, int]]] = []

    def walk(start: tuple[int, int], first: tuple[int, int]) -> list[tuple[int, int]]:
        chain = [start, first]
        unused.discard(start)
        unused.discard(first)
        previous, current = start, first
        while degree[current] == 2:
            forward = [n for n in around(current) if n != previous and n in unused]
            if not forward:
                break
            previous, current = current, forward[0]
            unused.discard(current)
            chain.append(current)
        return chain

    # Free ends first, then branches off junctions, then whatever is left is a closed loop.
    for point in sorted(p for p in points if degree[p] == 1):
        if point in unused:
            for neighbour in around(point):
                if neighbour in unused:
                    chains.append(walk(point, neighbour))
                    break
    for point in sorted(p for p in points if degree[p] >= 3):
        for neighbour in around(point):
            if neighbour in unused:
                chains.append(walk(point, neighbour))
    while unused:
        point = next(iter(unused))
        loose = [n for n in around(point) if n in unused]
        if not loose:
            unused.discard(point)
            continue
        chains.append(walk(point, loose[0]))
    return [chain for chain in chains if len(chain) >= 2]


def _stitch[PointT: tuple[float, float]](chains: list[list[PointT]], tolerance: float) -> list[list[PointT]]:
    """Join chains whose ends nearly touch, so one pen stroke replaces several.

    This is the whole economics of the mode: an un-stitched trace of a hatched drawing is
    ~4700 strokes (2.5 hours of pen lifts) and stitching cuts that ~9x with no measurable
    loss of fidelity. Endpoints are bucketed on a grid of the tolerance so this stays near
    linear; the obvious all-pairs scan is 25M comparisons at that chain count.
    """
    if tolerance <= 0 or not chains:
        return chains

    cell = max(tolerance, 1e-6)
    buckets: dict[tuple[int, int], list[int]] = defaultdict(list)
    pool: dict[int, list[PointT]] = dict(enumerate(chains))

    def register(index: int) -> None:
        for end in (pool[index][0], pool[index][-1]):
            buckets[(int(end[0] // cell), int(end[1] // cell))].append(index)

    def candidates(end: PointT) -> set[int]:
        key = (int(end[0] // cell), int(end[1] // cell))
        found: set[int] = set()
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                found.update(buckets.get((key[0] + dy, key[1] + dx), ()))
        return found

    for index in pool:
        register(index)

    merged: list[list[PointT]] = []
    while pool:
        index = next(iter(pool))
        current = pool.pop(index)
        joining = True
        while joining:
            joining = False
            for tail_first, end in ((True, current[-1]), (False, current[0])):
                for other_index in candidates(end):
                    if other_index not in pool:
                        continue
                    other = pool[other_index]
                    if _distance(end, other[0]) <= tolerance:
                        current = current + other[1:] if tail_first else other[::-1] + current[1:]
                    elif _distance(end, other[-1]) <= tolerance:
                        current = current + other[::-1][1:] if tail_first else other + current[1:]
                    else:
                        continue
                    pool.pop(other_index)
                    joining = True
                    break
                if joining:
                    break
        merged.append(current)
    return merged


def _half_width_map(mask: np.ndarray, max_radius: int = 10) -> np.ndarray:
    """Distance from each ink pixel to the nearest blank one — half the local stroke width.

    Repeated erosion rather than a real distance transform: the widths that matter here are
    under ~15 px, so ten passes of a cheap numpy erosion beats importing scipy for an exact
    EDT we would immediately round anyway.
    """
    depth = np.zeros(mask.shape, dtype=np.int16)
    current = mask
    for step in range(max_radius):
        if not current.any():
            break
        depth[current] = step + 1
        eroded = current
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                eroded = eroded & np.roll(np.roll(current, dy, 0), dx, 1)
        current = eroded
    return depth


def _weight_passes(
    points: list[tuple[float, float]], half_widths: list[float], pen_px: float
) -> list[list[tuple[float, float]]]:
    """Extra parallel passes so a bold source stroke reads bold under a thin pen.

    A centerline covers one pen width. On these drawings 26% of the ink sits in strokes
    5-15 px wide, which one pass structurally cannot reach — measured recall rose 0.888 to
    0.936 once this existed. Passes alternate sides and every other one is reversed, so
    consecutive passes chain end-to-start instead of buying another pen lift.

    Widths are per point, not one figure for the whole stroke: a line that starts bold and
    tapers should taper. Each pass is emitted only over the contiguous runs still wide
    enough to need it, so the thin end does not get filled to the thick end's weight.
    """
    if len(points) < 2:
        return []
    # Smooth the widths before deciding pass counts. The erosion depth dips by a pixel at
    # junctions and on ragged edges, and reacting to each dip shatters one long pass into
    # dozens of fragments — measured, that doubled the stroke count, and strokes are pen
    # lifts. A short median window keeps genuine tapers and ignores the speckle.
    window = 5
    smoothed = [
        float(np.median(half_widths[max(i - window // 2, 0) : i + window // 2 + 1])) for i in range(len(half_widths))
    ]
    needed = [int(round((2.0 * half / max(pen_px, 1e-6)) - 1.0)) for half in smoothed]
    if max(needed, default=0) < 1:
        return []

    # A run shorter than a couple of pen widths is not weight, it is a dash lying beside the
    # stroke — the median window above reduces the width dips that cut runs but cannot remove
    # them, and every surviving fragment printed as visible speckle next to the artwork.
    min_run = max(2, int(round(2.0 * pen_px)))
    passes: list[list[tuple[float, float]]] = []
    for index in range(1, min(max(needed), MAX_WEIGHT_PASSES) + 1):
        offset = ((index + 1) // 2) * pen_px * (1.0 if index % 2 else -1.0)
        run: list[tuple[float, float]] = []
        for position, (y, x) in enumerate(points):
            if needed[position] < index:
                if len(run) >= min_run:
                    passes.append(run if index % 2 else run[::-1])
                run = []
                continue
            ahead = points[min(position + 1, len(points) - 1)]
            behind = points[max(position - 1, 0)]
            dy, dx = ahead[0] - behind[0], ahead[1] - behind[1]
            length = math.hypot(dy, dx) or 1.0
            run.append((y - offset * (dx / length), x + offset * (dy / length)))
        if len(run) >= min_run:
            passes.append(run if index % 2 else run[::-1])
    return passes


def simplify_polyline(points: Sequence[tuple[float, float]], tolerance: float) -> list[tuple[float, float]]:
    """Douglas-Peucker. Drops the collinear runs a pixel skeleton is mostly made of.

    Iterative, so it is safe on the thousands-of-points loops a contour off a large
    crop produces; svg_gcode._simplify_polyline is the recursive equivalent.

    The early return names its elements `y, x` because callers here pass (row, col).
    Both return paths preserve the input order -- this does not transpose.
    """
    if tolerance <= 0 or len(points) < 3:
        return [(float(y), float(x)) for y, x in points]
    array = np.array(points, dtype=np.float64)
    keep = np.zeros(len(array), dtype=bool)
    keep[0] = keep[-1] = True
    stack = [(0, len(array) - 1)]
    while stack:
        start, end = stack.pop()
        if end <= start + 1:
            continue
        span = array[end] - array[start]
        length = float(np.hypot(span[0], span[1]))
        relative = array[start + 1 : end] - array[start]
        if length == 0:
            distances = np.hypot(relative[:, 0], relative[:, 1])
        else:
            # numpy 2 removed the 2-D np.cross; this is that cross product written out.
            distances = np.abs(span[0] * relative[:, 1] - span[1] * relative[:, 0]) / length
        furthest = int(np.argmax(distances)) + start + 1
        if distances.max() > tolerance:
            keep[furthest] = True
            stack += [(start, furthest), (furthest, end)]
    return [(float(point[0]), float(point[1])) for point in array[keep]]


def _shade_fill(tone: ToneGrid, ink: np.ndarray, pen_width_mm: float, spacing_mm: float, floor: float) -> Polylines:
    """Hatch the filled areas a centerline trace leaves blank, and nothing else.

    Masking against the ink dilated by one pen width is what makes this safe to leave on:
    in pen-and-ink art the mid-tones ARE the hatching, already traced, so the mask swallows
    them and almost no fill is emitted. Measured over nine folders, the genuinely uncovered
    mid-tone is 0.04-1.7% of the image for eight of them — and 10.9% for the one drawn in
    flat colour, whose hull currently prints as blank paper.
    """
    grow = max(1, int(round(pen_width_mm / max(tone.cell_mm, 1e-6))))
    covered = (
        np.asarray(Image.fromarray((ink * 255).astype(np.uint8)).filter(ImageFilter.MaxFilter(2 * grow + 1))) > 127
    )
    shade = np.where(covered, 0.0, tone.darkness)
    shade[shade < floor] = 0.0
    if not shade.any():
        return []
    return hatch(
        ToneGrid(shade, tone.cell_mm, tone.width_mm, tone.height_mm),
        line_spacing_mm=spacing_mm,
        angle_deg=45.0,
    )


def trace(
    tone: ToneGrid,
    *,
    threshold: float = 0.5,
    despeckle_px: float = 0.0,
    stitch_px: float = 10.0,
    simplify_px: float = 1.0,
    pen_width_mm: float = PEN_WIDTH_MM_DEFAULT,
    weight_passes: bool = True,
    shade_spacing_mm: float = 0.0,
    shade_floor: float = 0.12,
    max_skeleton_px: int = MAX_SKELETON_PX_DEFAULT,
) -> Polylines:
    """Follow the drawing's own strokes instead of re-rendering its tone.

    The other four modes answer "how dark is it here" and invent geometry to match, which is
    right for a photograph and wrong for line art: they put ink where the source has none.
    This one thresholds, thins to a one-pixel skeleton and walks it, so every stroke it draws
    sits on a stroke that exists. Useless on a photograph, which has no lines to find.

    cell_mm is the trace resolution here, not a dot pitch — it should be near the source's
    own pixel size (150 mm / 1024 px is about 0.15).

    The defaults come from a sweep over one sample from each of nine real folders, scored
    against the source with a 3 px boundary F-score. Two results are worth keeping:
    despeckling only ever cost fidelity (F 0.905 -> 0.877 at 3 px, 0.838 at 6 px) because
    what looks like specks is the hatching, so it defaults off; and stitching 0 -> 10 px
    moved F by 0.001 while collapsing 7 239 strokes to 181, so the merging is all but free.
    Past ~16 px precision starts to drop as real gaps get bridged, hence stopping at 10.
    """
    if not 0.0 < threshold < 1.0:
        raise ValueError("threshold must be between 0 and 1")
    if despeckle_px < 0 or stitch_px < 0 or simplify_px < 0:
        raise ValueError("despeckle_px, stitch_px, and simplify_px must be non-negative")

    mask = tone.darkness > threshold
    skeleton = _thin(mask)
    ink = int(skeleton.sum())
    if ink > max_skeleton_px:
        raise ValueError(
            f"traced {ink} skeleton pixels, exceeding max_skeleton_px={max_skeleton_px}; "
            "increase cell_mm, or raise threshold if the image is not line art"
        )
    if not ink:
        return []

    chains = _walk_skeleton(skeleton)
    chains = _stitch(chains, stitch_px)
    # Despeckle AFTER stitching, not before. Before, the question is "is this fragment long on
    # its own?", which condemns legitimate hatching — that is why despeckling measured as a
    # fidelity loss and ended up disabled. After, the question is "did it end up part of
    # anything?": a hatch dash that stitched into a 40 mm stroke inherits that length and
    # survives, while a speck nothing would join to dies. Stitching is also what makes specks
    # visible in the first place, chaining 0.15 mm dots into printed millimetre dashes.
    if despeckle_px > 0:
        chains = [chain for chain in chains if len(chain) >= despeckle_px]

    pen_px = max(pen_width_mm / max(tone.cell_mm, 1e-6), 1.0)
    depth = _half_width_map(mask) if weight_passes else None
    cell_polylines: list[list[tuple[float, float]]] = []
    for chain in chains:
        simplified = simplify_polyline(chain, simplify_px)
        if len(simplified) < 2:
            continue
        cell_polylines.append(simplified)
        if depth is None:
            continue
        # Widths come off the full-resolution chain, not `simplified`: a straight tapered
        # stroke simplifies to its two endpoints, and two samples cannot describe a taper —
        # the passes would be dropped entirely. Simplify each pass afterwards instead.
        widths = [float(depth[y, x]) for y, x in chain]
        chain_points = [(float(y), float(x)) for y, x in chain]
        for extra in _weight_passes(chain_points, widths, pen_px):
            thinned_pass = simplify_polyline(extra, simplify_px)
            if len(thinned_pass) >= 2:
                cell_polylines.append(thinned_pass)

    if shade_spacing_mm > 0:
        cell_polylines.extend(
            [(y / tone.cell_mm, x / tone.cell_mm) for x, y in fill]
            for fill in _shade_fill(tone, mask, pen_width_mm, shade_spacing_mm, shade_floor)
        )

    # Clip on the way out, as the other modes do: an offset weight pass on a stroke that
    # touches the edge lands outside the sheet, and svg_gcode would happily drive there.
    return [
        [
            (_clip(x * tone.cell_mm, 0.0, tone.width_mm), _clip(y * tone.cell_mm, 0.0, tone.height_mm))
            for y, x in polyline
        ]
        for polyline in cell_polylines
        if len(polyline) >= 2
    ]


def crosshatch(
    tone: ToneGrid,
    *,
    line_spacing_mm: float = 1.2,
    angles: tuple[float, ...] = (0.0, 45.0, 90.0, 135.0),
    min_darkness: float = 0.05,
    stitch_mm: float = 0.0,
) -> Polylines:
    """Layered hatching at several angles — the tone mode for photographs.

    Each angle is a full hatch pass with its own darkness floor, so light areas receive one
    direction and only the darkest receive all of them. That is what buys tonal range: a
    single angle has to encode every grey in line spacing alone, and measured against a
    shaded render it holds tone at 0.796 close up where four angles reach 0.914.

    Stitching leaves tone correlation unchanged while cutting measured output from 622 to
    287 strokes and plot time from 40 to 28 minutes.

    Deliberately built on hatch() rather than reimplementing scanlines — the tone ladder,
    the rotation and the clipping are already correct there.
    """
    if not angles:
        raise ValueError("crosshatch needs at least one angle")
    polylines: Polylines = []
    for layer, angle_deg in enumerate(angles):
        floor = min_darkness + (1.0 - min_darkness) * (layer / len(angles))
        polylines.extend(hatch(tone, line_spacing_mm=line_spacing_mm, angle_deg=angle_deg, min_darkness=floor))
    return _stitch(polylines, stitch_mm) if stitch_mm > 0 else polylines


def spiral(
    tone: ToneGrid,
    *,
    pitch_mm: float = 1.5,
    amplitude_mm: float = 0.6,
    cycles_per_mm: float = 0.5,
    min_darkness: float = 0.05,
    max_points: int = MAX_SPIRAL_POINTS,
) -> Polylines:
    """One Archimedean spiral out from the centre, wobbling harder where the image is dark.

    An Archimedean spiral lays down constant line length per unit area, so the baseline
    carries no tone at all; every bit of tone comes from radial wobble adding length, and
    from the path lifting entirely below min_darkness. That gating is why this cannot be a
    single unbroken stroke on anything with white in it — the alternative, laying the
    baseline everywhere, inks blank paper. On a real image it is still a handful of strokes
    against thousands for the dot modes, which is the point: pen lifts dominate plot time.
    """
    if pitch_mm <= 0:
        raise ValueError("pitch_mm must be positive")
    if amplitude_mm < 0 or cycles_per_mm <= 0:
        raise ValueError("amplitude_mm must be non-negative and cycles_per_mm positive")

    center_x = tone.width_mm / 2.0
    center_y = tone.height_mm / 2.0
    reach = math.hypot(tone.width_mm, tone.height_mm) / 2.0
    # The step follows the wobble, not the tone grid. Sampling a sine at the cell size
    # aliases it into noise instead of drawing it, and the wobble IS the tone signal here.
    step_mm = 1.0 / (cycles_per_mm * 8.0)
    # Bound generation, not just the segment count: the cap in image_to_polylines only runs
    # once this returns, so a fine pitch on a big sheet would spin here first.
    if math.pi * reach * reach / pitch_mm / step_mm > max_points:
        raise ValueError(f"spiral would need more than max_points={max_points} samples; increase pitch_mm or cell_mm")

    polylines: Polylines = []
    run: list[tuple[float, float]] = []
    growth = pitch_mm / math.tau  # radius gained per radian
    angle = 0.0
    # Phase is accumulated rather than read off the angle so that darkness can drive the
    # wobble FREQUENCY as well as its amplitude, without a jump wherever tone changes. Both
    # together are what buys a usable tonal range: amplitude alone only doubles the ink
    # between white and black, because the spiral's own length per unit area is constant.
    phase = 0.0
    while True:
        radius = growth * angle
        if radius > reach:
            break
        x = center_x + radius * math.cos(angle)
        y = center_y + radius * math.sin(angle)
        angle += step_mm / max(radius, step_mm)
        if not (0 <= x <= tone.width_mm and 0 <= y <= tone.height_mm):
            if len(run) >= 2:
                polylines.append(run)
            run = []
            continue
        darkness = _sample_darkness(tone, x, y)
        if darkness < min_darkness:
            if len(run) >= 2:
                polylines.append(run)
            run = []
            continue
        phase += math.tau * cycles_per_mm * step_mm * (0.3 + darkness)
        wobble = math.sin(phase) * amplitude_mm * darkness
        run.append(
            _clip_point(
                (x + wobble * math.cos(angle), y + wobble * math.sin(angle)),
                tone.width_mm,
                tone.height_mm,
            )
        )
    if len(run) >= 2:
        polylines.append(run)
    return polylines


def wave(
    tone: ToneGrid,
    *,
    row_pitch_mm: float = 2.0,
    amplitude_mm: float = 0.8,
    cycles_per_mm: float = 0.35,
    min_darkness: float = 0.05,
) -> Polylines:
    """Rows that ripple harder and faster where the image is dark — the waveform-portrait look.

    Tone is carried twice over: amplitude and frequency both rise with darkness, so a dark
    row is a dense tall zigzag and a light one is nearly a straight rule. Unlike hatch this
    never drops a row to carry tone, so the result reads as a continuous field.

    Every run starts and ends on its own baseline. order_serpentine buckets by floor() of the
    first point's y in 1 mm bands, so a run that opened mid-swing could be filed under the
    neighbouring row and get sorted into the wrong band — the same trap documented for
    dither's row chaining.
    """
    if row_pitch_mm <= 0:
        raise ValueError("row_pitch_mm must be positive")
    if amplitude_mm < 0 or cycles_per_mm <= 0:
        raise ValueError("amplitude_mm must be non-negative and cycles_per_mm positive")

    polylines: Polylines = []
    step_mm = max(tone.cell_mm, 1.0 / (cycles_per_mm * 8.0))
    row_y = row_pitch_mm / 2.0
    # Keep the swing inside its own row so neighbouring rows cannot cross and merge into ink.
    swing = min(amplitude_mm, row_pitch_mm * 0.45)
    while row_y < tone.height_mm:
        phase = 0.0
        run: list[tuple[float, float]] = []
        samples = max(1, math.ceil(tone.width_mm / step_mm))
        for index in range(samples + 1):
            x = tone.width_mm * index / samples
            darkness = _sample_darkness(tone, x, row_y)
            if darkness < min_darkness:
                if len(run) >= 2:
                    run.append((run[-1][0], row_y))
                    polylines.append(run)
                run = []
                continue
            phase += math.tau * cycles_per_mm * step_mm * (0.4 + darkness)
            if not run:
                run.append((x, row_y))
                continue
            run.append((x, _clip(row_y + math.sin(phase) * swing * darkness, 0, tone.height_mm)))
        if len(run) >= 2:
            run.append((run[-1][0], row_y))
            polylines.append(run)
        row_y += row_pitch_mm
    return polylines


def stipple(
    tone: ToneGrid,
    *,
    row_pitch_mm: float = 1.0,
    min_spacing_mm: float = 1.0,
    max_spacing_mm: float = 3.0,
    dot_mm: float = 0.6,
    chain_gap_mm: float = 3.0,
    min_darkness: float = 0.05,
    max_points: int = MAX_STIPPLE_POINTS,
) -> Polylines:
    """Density-weighted dots, chained within rows so pen lifts don't dominate the plot.

    Each dot is otherwise its own pen lift, measured at ~0.9 s apiece on this machine (see
    dither's docstring, which hit 77 129 of them on one photo). dither solves this by
    chaining raster dots that happen to land within chain_gap_mm of each other; here
    darkness instead drives the dot SPACING directly — dense in dark areas, sparse near
    white — so consecutive dots in a row are already close together by construction, and
    chain_gap_mm only has to bridge the rare wider gap rather than carry the whole scheme.

    Spacing alone tops out at "the row reads as continuously inked" once every gap is
    already below chain_gap_mm, which would flatten the darkest quarter of the tone range
    into one plateau — a run of tightly packed dots and a run of dots just under the chain
    threshold cover the same distance either way. Each dot also gets a small sideways jog
    scaled by its own darkness, so a darker row keeps adding ink even once its dots are
    already fully chained.
    """
    if row_pitch_mm <= 0:
        raise ValueError("row_pitch_mm must be positive")
    if min_spacing_mm <= 0 or max_spacing_mm <= 0 or min_spacing_mm > max_spacing_mm:
        raise ValueError("stipple spacings must be positive and min_spacing_mm <= max_spacing_mm")
    if dot_mm < 0:
        raise ValueError("dot_mm must be non-negative")
    if chain_gap_mm < 0:
        raise ValueError("chain_gap_mm must be non-negative")

    # Fail fast rather than freeze: placing a dot is a pure-Python loop iteration, and the
    # segment cap in image_to_polylines only runs once this returns — the same trap flow
    # guards against with MAX_FLOW_SEEDS. Worst case is every row filled at the finest
    # spacing this call allows.
    estimate = (tone.height_mm / row_pitch_mm) * (tone.width_mm / min_spacing_mm)
    if estimate > max_points:
        raise ValueError(
            f"stipple would place more than max_points={max_points} dots; "
            "widen min_spacing_mm or row_pitch_mm, or reduce the drawing size"
        )

    half_jog = dot_mm / 2.0
    polylines: Polylines = []
    row_y = row_pitch_mm / 2.0
    while row_y < tone.height_mm:
        run: list[tuple[float, float]] = []
        prev_x: float | None = None
        x = 0.0
        while x <= tone.width_mm:
            darkness = _sample_darkness(tone, x, row_y)
            if darkness < min_darkness:
                if len(run) >= 2:
                    polylines.append(run)
                run = []
                prev_x = None
                # Skip ahead at the sparsest pitch rather than min_spacing_mm: stepping fine
                # through a blank margin is what made an early version of this loop slow on
                # a mostly-white sheet.
                x += max_spacing_mm
                continue
            if prev_x is not None and x - prev_x > chain_gap_mm:
                if len(run) >= 2:
                    polylines.append(run)
                run = []
            jog = half_jog * darkness
            if jog > 0:
                run.append(_clip_point((x, row_y - jog), tone.width_mm, tone.height_mm))
                run.append(_clip_point((x, row_y + jog), tone.width_mm, tone.height_mm))
            else:
                run.append(_clip_point((x, row_y), tone.width_mm, tone.height_mm))
            prev_x = x
            spacing = max_spacing_mm + (min_spacing_mm - max_spacing_mm) * darkness
            x += spacing
        if len(run) >= 2:
            polylines.append(run)
        row_y += row_pitch_mm
    return polylines


def squiggle(
    tone: ToneGrid,
    *,
    min_row_pitch_mm: float = 1.0,
    max_row_pitch_mm: float = 3.0,
    amplitude_mm: float = 0.6,
    cycles_per_mm: float = 0.4,
    min_darkness: float = 0.05,
    max_points: int = MAX_SQUIGGLE_POINTS,
) -> Polylines:
    """One continuous meandering line, packing its rows tighter where the image is dark.

    Tone is carried twice, the way spiral carries it: the sine's amplitude and frequency
    both scale with the sampled darkness (wave's trick), and on top of that the vertical
    gap between successive sweeps shrinks toward min_row_pitch_mm in dark rows and relaxes
    toward max_row_pitch_mm in light ones, so a dark region gets more rows through the same
    height, not only wider wiggles in the rows it already had.

    The row-to-row connection is never broken on purpose — one continuous line rather than a
    stack of separately lifted hatch strokes is the entire point of this mode. It is still
    gated on min_darkness exactly like spiral, for the same reason: the alternative, drawing
    the meander everywhere, inks every white margin of every source image.
    """
    if min_row_pitch_mm <= 0 or max_row_pitch_mm <= 0 or min_row_pitch_mm > max_row_pitch_mm:
        raise ValueError("squiggle row pitches must be positive and min_row_pitch_mm <= max_row_pitch_mm")
    if amplitude_mm < 0 or cycles_per_mm <= 0:
        raise ValueError("amplitude_mm must be non-negative and cycles_per_mm positive")

    # The step follows the wobble, not the tone grid, for the same reason spiral's does:
    # sampling a sine at the cell size aliases it into noise instead of drawing it.
    step_mm = 1.0 / (cycles_per_mm * 8.0)
    # Bound generation before it runs, not just the segment count afterwards: worst case is
    # every row packed at min_row_pitch_mm, each walked at step_mm.
    estimate = (tone.height_mm / min_row_pitch_mm) * (tone.width_mm / step_mm)
    if estimate > max_points:
        raise ValueError(
            f"squiggle would need more than max_points={max_points} samples; "
            "increase min_row_pitch_mm, cycles_per_mm, or cell_mm"
        )

    polylines: Polylines = []
    run: list[tuple[float, float]] = []
    phase = 0.0
    row_y = max_row_pitch_mm / 2.0
    direction = 1.0
    while row_y < tone.height_mm:
        # A cheap 8-point pre-sample decides this row's pitch and swing ceiling before the
        # fine walk draws it: the swing has to stay inside the band this row is given, and
        # that band's width is also what row_y advances by afterwards, so both need the
        # row's darkness known up front rather than discovered point by point.
        preview = [_sample_darkness(tone, tone.width_mm * i / 7, row_y) for i in range(8)]
        row_darkness = sum(preview) / len(preview)
        row_pitch = max_row_pitch_mm + (min_row_pitch_mm - max_row_pitch_mm) * row_darkness
        swing_limit = min(amplitude_mm, row_pitch * 0.45)

        samples = max(1, math.ceil(tone.width_mm / step_mm))
        xs = [tone.width_mm * index / samples for index in range(samples + 1)]
        if direction < 0:
            xs.reverse()
        for x in xs:
            darkness = _sample_darkness(tone, x, row_y)
            if darkness < min_darkness:
                if len(run) >= 2:
                    polylines.append(run)
                run = []
                continue
            phase += math.tau * cycles_per_mm * step_mm * (0.4 + darkness)
            y = row_y + math.sin(phase) * swing_limit * darkness
            run.append(_clip_point((x, y), tone.width_mm, tone.height_mm))
        row_y += row_pitch
        direction = -direction
    if len(run) >= 2:
        polylines.append(run)
    return polylines


MODES: dict[str, Callable[..., Polylines]] = {
    "halftone": halftone,
    "hatch": hatch,
    "flow": flow,
    "dither": dither,
    "contour": contour,
    "trace": trace,
    "crosshatch": crosshatch,
    "spiral": spiral,
    "wave": wave,
    "stipple": stipple,
    "squiggle": squiggle,
}

# Modes whose own emission order IS the plot order. Serpentine would bucket their arcs by
# first-point y and reshuffle them into a raster scan, adding back the pen lifts they exist
# to avoid. squiggle joins spiral here for the same reason: its rows are already one
# continuous top-to-bottom path, built serpentine already, so bucketing by first-point y
# would cut it back into per-row strokes and reintroduce the very lifts it exists to avoid.
# stipple is deliberately NOT here — each row is its own short chained run, not a single
# through-line, so serpentine's raster ordering is what makes those runs plot efficiently.
CONTINUOUS_MODES = frozenset({"spiral", "squiggle"})


def order_serpentine(polylines: Polylines) -> Polylines:
    rows: dict[int, Polylines] = defaultdict(list)
    for polyline in polylines:
        if polyline:
            rows[math.floor(polyline[0][1])].append(list(polyline))

    ordered: Polylines = []
    previous: tuple[float, float] | None = None
    for row_number, row in enumerate(rows[key] for key in sorted(rows)):
        left_to_right = row_number % 2 == 0
        row.sort(key=lambda line: min(line[0][0], line[-1][0]) if left_to_right else -max(line[0][0], line[-1][0]))
        for polyline in row:
            if previous is not None and _distance(previous, polyline[-1]) < _distance(previous, polyline[0]):
                polyline.reverse()
            ordered.append(polyline)
            previous = polyline[-1]
    return ordered


def _stroke_extent_mm(polyline: list[tuple[float, float]]) -> float:
    """Bounding-box diagonal of one stroke, in mm.

    Deliberately not arc length. A contour band drawn around a single noisy cell is a closed
    loop whose perimeter can exceed 2 mm while it prints as one dot; its bounding box is one
    cell across. A long stroke has a long box however it wanders. One measure catches the
    isolated speck and the micro-loop alike, and both are what the pen turns into dirt.
    """
    xs = [x for x, _ in polyline]
    ys = [y for _, y in polyline]
    return math.hypot(max(xs) - min(xs), max(ys) - min(ys))


def travel_length_mm(polylines: Polylines) -> tuple[float, float]:
    draw = sum(
        _distance(start, end) for polyline in polylines for start, end in zip(polyline, polyline[1:], strict=False)
    )
    travel = sum(
        _distance(previous[-1], current[0])
        for previous, current in zip(polylines, polylines[1:], strict=False)
        if previous and current
    )
    return draw, travel


def _validate_render_request(mode: str, min_stroke_mm: float) -> None:
    if mode not in MODES:
        raise ValueError(f"unknown mode {mode!r}; valid modes: {', '.join(sorted(MODES))}")
    if min_stroke_mm < 0:
        raise ValueError("min_stroke_mm must be non-negative")


def tone_to_polylines(
    tone: ToneGrid,
    *,
    mode: str,
    max_segments: int = MAX_SEGMENTS_DEFAULT,
    min_stroke_mm: float = 0.0,
    **params: Any,
) -> Polylines:
    """Render an already-built ToneGrid.

    The half of image_to_polylines that does not care where the tone came from -- a scan, or a
    procedural texture graph (imaging/texture.py). Everything a renderer needs is in the ToneGrid,
    so a second tone producer costs nothing here.
    """
    _validate_render_request(mode, min_stroke_mm)
    strokes = MODES[mode](tone, **params)
    # Centre-out modes carry their own order. Serpentine buckets by floor(first point's y),
    # which would reshuffle a spiral's arcs into a raster scan and add back every pen lift
    # the mode exists to avoid.
    if mode not in CONTINUOUS_MODES:
        strokes = order_serpentine(strokes)
    polylines = [polyline for polyline in strokes if len(polyline) >= 2]
    if min_stroke_mm > 0:
        polylines = [polyline for polyline in polylines if _stroke_extent_mm(polyline) >= min_stroke_mm]
    segment_count = sum(len(polyline) - 1 for polyline in polylines)
    if segment_count > max_segments:
        raise ValueError(
            f"generated {segment_count} segments, exceeding max_segments={max_segments}; "
            "increase cell_mm or line_spacing_mm, or raise max_segments"
        )
    return polylines


def image_to_polylines(
    data: bytes,
    *,
    mode: str,
    width_mm: float,
    height_mm: float,
    cell_mm: float = 1.0,
    invert: bool = False,
    gamma: float = 1.0,
    levels: int | None = None,
    autocontrast: bool = True,
    max_segments: int = MAX_SEGMENTS_DEFAULT,
    min_stroke_mm: float = 0.0,
    **params: Any,
) -> Polylines:
    # Validated here as well as in tone_to_polylines on purpose: these guards must fire BEFORE
    # load_tone, so image_to_polylines(b"garbage", mode="nope") still says "unknown mode" rather
    # than "unable to read raster image data". It is one dict lookup.
    _validate_render_request(mode, min_stroke_mm)
    tone = load_tone(
        data,
        width_mm=width_mm,
        height_mm=height_mm,
        cell_mm=cell_mm,
        invert=invert,
        gamma=gamma,
        levels=levels,
        # Worth turning off for photographs: it stretches the histogram to full range,
        # which lifts fabric texture and JPEG noise into ink (tests/test_imaging_speckle.py).
        autocontrast=autocontrast,
    )
    return tone_to_polylines(tone, mode=mode, max_segments=max_segments, min_stroke_mm=min_stroke_mm, **params)


def polylines_to_svg(
    polylines: Polylines, *, width_mm: float, height_mm: float, pen_width_mm: float = PEN_WIDTH_MM_DEFAULT
) -> str:
    """Serialize mm polylines for the direct-SVG print path.

    data-neje-simplify-mm="0" matters: svg_gcode reads it, and the default tolerance
    would otherwise flatten small halftone dots away.
    """
    lines = [
        '<svg xmlns="http://www.w3.org/2000/svg" '
        f'viewBox="0 0 {width_mm:g} {height_mm:g}" width="{width_mm:g}mm" '
        f'height="{height_mm:g}mm" data-neje-simplify-mm="0">'
    ]
    lines.extend(
        f'<polyline points="{" ".join(f"{x:.3f},{y:.3f}" for x, y in polyline)}" '
        f'fill="none" stroke="black" stroke-width="{pen_width_mm:g}"/>'
        for polyline in polylines
    )
    lines.append("</svg>")
    return "\n".join(lines)


def travel_preview_svg(polylines: Polylines, *, width_mm: float, height_mm: float) -> str:
    """Screen-only preview: ink in black, pen-up travel in red, start dot at the origin.

    Never send this to the plotter — the travel hairlines are real <polyline> elements and
    svg_gcode would happily draw every one of them. polylines_to_svg stays the print path.

    The travel is derived from the polylines themselves, not from generated G-code, so the
    preview costs nothing and needs no spool file: the pen goes from the end of one stroke
    to the start of the next, which is exactly what travel_length_mm already measures.
    """
    parts = [
        '<svg xmlns="http://www.w3.org/2000/svg" '
        f'viewBox="0 0 {width_mm:g} {height_mm:g}" width="{width_mm:g}mm" height="{height_mm:g}mm">',
        f'<rect x="0" y="0" width="{width_mm:g}" height="{height_mm:g}" fill="none" '
        'stroke="#dac9ad" stroke-width="0.4"/>',
    ]
    previous: tuple[float, float] | None = (0.0, 0.0)
    for polyline in polylines:
        if not polyline:
            continue
        if previous is not None:
            parts.append(
                f'<line x1="{previous[0]:.2f}" y1="{previous[1]:.2f}" '
                f'x2="{polyline[0][0]:.2f}" y2="{polyline[0][1]:.2f}" '
                'stroke="#c4623f" stroke-width="0.15" opacity="0.55"/>'
            )
        previous = polyline[-1]
    parts.extend(
        f'<polyline points="{" ".join(f"{x:.3f},{y:.3f}" for x, y in polyline)}" '
        'fill="none" stroke="black" stroke-width="0.3"/>'
        for polyline in polylines
    )
    parts.append('<circle cx="0" cy="0" r="1.2" fill="none" stroke="#c0392b" stroke-width="0.4"/>')
    parts.append("</svg>")
    return "\n".join(parts)


def image_to_svg(
    data: bytes,
    *,
    mode: str,
    width_mm: float,
    height_mm: float,
    **kwargs: Any,
) -> str:
    polylines = image_to_polylines(
        data,
        mode=mode,
        width_mm=width_mm,
        height_mm=height_mm,
        **kwargs,
    )
    return polylines_to_svg(polylines, width_mm=width_mm, height_mm=height_mm)


def _clip(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def _clip_point(point: tuple[float, float], width: float, height: float) -> tuple[float, float]:
    return _clip(point[0], 0, width), _clip(point[1], 0, height)


def _distance(a: tuple[float, float], b: tuple[float, float]) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def _sample_darkness(tone: ToneGrid, x: float, y: float) -> float:
    rows, cols = tone.darkness.shape
    column = min(cols - 1, max(0, int(x * cols / tone.width_mm)))
    row = min(rows - 1, max(0, int(y * rows / tone.height_mm)))
    return float(tone.darkness[row, column])


def _line_interval(
    origin: tuple[float, float],
    direction: tuple[float, float],
    width: float,
    height: float,
) -> tuple[float, float] | None:
    lower = -math.inf
    upper = math.inf
    for coordinate, delta, maximum in zip(origin, direction, (width, height), strict=True):
        if abs(delta) < 1e-12:
            if not 0 <= coordinate <= maximum:
                return None
            continue
        first = -coordinate / delta
        second = (maximum - coordinate) / delta
        lower = max(lower, min(first, second))
        upper = min(upper, max(first, second))
    return (lower, upper) if upper > lower else None


def _interpolate(
    start: tuple[float, float],
    end: tuple[float, float],
    start_value: float,
    end_value: float,
    level: float,
) -> tuple[float, float]:
    ratio = 0.5 if start_value == end_value else (level - start_value) / (end_value - start_value)
    return (
        start[0] + _clip(ratio, 0, 1) * (end[0] - start[0]),
        start[1] + _clip(ratio, 0, 1) * (end[1] - start[1]),
    )


def _point_key(point: tuple[float, float]) -> tuple[int, int]:
    return round(point[0] * 1_000_000), round(point[1] * 1_000_000)


def _join_segments(
    segments: list[tuple[tuple[float, float], tuple[float, float]]],
) -> Polylines:
    adjacency: dict[tuple[int, int], list[int]] = defaultdict(list)
    for index, (start, end) in enumerate(segments):
        adjacency[_point_key(start)].append(index)
        adjacency[_point_key(end)].append(index)
    unused = set(range(len(segments)))
    starts = [key for key, indexes in adjacency.items() if len(indexes) == 1]
    starts.extend(key for key, indexes in adjacency.items() if len(indexes) != 1)
    polylines: Polylines = []

    for start_key in starts:
        available = [index for index in adjacency[start_key] if index in unused]
        while available:
            points: list[tuple[float, float]] = []
            current_key = start_key
            while True:
                candidates = [index for index in adjacency[current_key] if index in unused]
                if not candidates:
                    break
                index = candidates[0]
                unused.remove(index)
                first, second = segments[index]
                if not points:
                    points.append(first if _point_key(first) == current_key else second)
                next_point = second if _point_key(first) == current_key else first
                points.append(next_point)
                current_key = _point_key(next_point)
            if len(points) >= 2:
                polylines.append(points)
            available = [index for index in adjacency[start_key] if index in unused]
    return polylines


def _chaikin(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    if len(points) < 3:
        return points
    closed = _point_key(points[0]) == _point_key(points[-1])
    source = points[:-1] if closed else points
    smoothed = [] if closed else [source[0]]
    pairs = zip(source, source[1:] + ([source[0]] if closed else []), strict=False)
    for start, end in pairs:
        smoothed.extend(
            (
                (0.75 * start[0] + 0.25 * end[0], 0.75 * start[1] + 0.25 * end[1]),
                (0.25 * start[0] + 0.75 * end[0], 0.25 * start[1] + 0.75 * end[1]),
            )
        )
    if closed:
        smoothed.append(smoothed[0])
    else:
        smoothed.append(source[-1])
    return smoothed
