"""Picture -> cleaned, optimised bank motif.

Almost all of this is assembly. load_tone does the greyscale/contrast/gamma cleanup,
image_to_polylines does the tracing and the size-based despeckle, simplify_polyline
does the optimising, and to_unit_box does the normalization. The only genuinely new
step is cropping: a photo of a shirt carries dozens of motifs, and nothing in the
repo could select one.

Default mode is `contour`, not `trace`. trace() skeletonizes, which is documented as
useless on photographs -- it finds structure in noise. contour() is marching squares,
so it yields closed loops and at low band counts collapses to the silhouette.
"""

from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO

from PIL import Image, UnidentifiedImageError

from ..imaging.modes import Polylines, image_to_polylines, polylines_to_svg, simplify_polyline
from .bank import to_unit_box

# Stored size. to_unit_box renormalizes on load, so this is arbitrary to the pipeline --
# it only decides how sane the file looks when opened in Inkscape.
CANONICAL_MOTIF_MM = 100.0

DEFAULT_MODE = "contour"

# A motif is tiled into every cell of a grid, so its polyline count is multiplied by the
# cell count downstream. Far tighter than the 40k image_to_polylines allows for a whole
# artwork: past a few hundred strokes a single motif eats the sketch's whole shape budget
# and the field goes sparse. Refusing early names the problem at import time.
MAX_MOTIF_SEGMENTS = 4_000

# contour() defaults to 4 bands, which traces an inner and an outer loop per band: every
# printed stroke comes back as a double line and the motif reads as outline-of-outline.
# Measured on RAW_Patterns/Screenshot_20260805-113455.png, one hatched-triangle crop:
# 4 bands -> 300 strokes / 2210 points, 1 band -> 61 / 641, and only the second is a
# recognisable single-line motif. The GUI reached the same conclusion for line art
# (workspaces/image.py:246).
_MOTIF_MODE_DEFAULTS: dict[str, dict[str, object]] = {"contour": {"bands": 1}}


@dataclass(frozen=True)
class CropBox:
    """Region of interest, in percent of the source image."""

    left: float = 0.0
    top: float = 0.0
    width: float = 100.0
    height: float = 100.0

    def pixels(self, image_width: int, image_height: int) -> tuple[int, int, int, int]:
        """Resolve to a pixel box, clamped inside the image."""
        if self.width <= 0 or self.height <= 0:
            raise ValueError("crop width and height must be positive percentages")

        # Both ends derive from the SAME clamped origin. Computing `right` from the raw
        # self.left instead would let a negative left produce left=0 with a right measured
        # from off-image, and the positive-area guard above cannot catch it because left
        # has already been clamped.
        left_pct = _clamp(self.left, 0.0, 100.0)
        top_pct = _clamp(self.top, 0.0, 100.0)
        left = int(round(left_pct / 100.0 * image_width))
        top = int(round(top_pct / 100.0 * image_height))
        right = int(round((left_pct + self.width) / 100.0 * image_width))
        bottom = int(round((top_pct + self.height) / 100.0 * image_height))

        right = min(max(right, left + 1), image_width)
        bottom = min(max(bottom, top + 1), image_height)
        if left >= image_width or top >= image_height:
            raise ValueError("crop origin falls outside the image")
        return left, top, right, bottom


def crop_image(data: bytes, crop: CropBox) -> bytes:
    """Crop to the region of interest, returning PNG bytes.

    PNG rather than the source format: the result is re-read by load_tone, and a second
    JPEG round trip would add exactly the compression noise this feature fights.
    """
    try:
        image = Image.open(BytesIO(data))
        image.load()
    except (UnidentifiedImageError, OSError) as error:
        raise ValueError(f"unreadable image: {error}") from error

    box = crop.pixels(image.width, image.height)
    buffer = BytesIO()
    image.crop(box).save(buffer, format="PNG")
    return buffer.getvalue()


def image_to_motif_polylines(
    data: bytes,
    *,
    mode: str = DEFAULT_MODE,
    crop: CropBox | None = None,
    cell_mm: float = 0.8,
    gamma: float = 1.0,
    levels: int | None = None,
    invert: bool = False,
    autocontrast: bool = True,
    despeckle_mm: float = 1.5,
    simplify_mm: float = 0.4,
    max_segments: int = MAX_MOTIF_SEGMENTS,
    **params: object,
) -> Polylines:
    """Trace a picture into a normalized motif: unit box, centred on the origin."""
    if simplify_mm < 0:
        raise ValueError("simplify_mm must be non-negative")

    source = crop_image(data, crop) if crop is not None else data
    width_mm, height_mm = _motif_extent_mm(source)
    params = {**_MOTIF_MODE_DEFAULTS.get(mode, {}), **params}

    polylines = image_to_polylines(
        source,
        mode=mode,
        width_mm=width_mm,
        height_mm=height_mm,
        cell_mm=cell_mm,
        gamma=gamma,
        levels=levels,
        invert=invert,
        autocontrast=autocontrast,
        min_stroke_mm=despeckle_mm,
        max_segments=max_segments,
        **params,
    )

    optimised = [simplify_polyline(polyline, simplify_mm) for polyline in polylines]
    optimised = [polyline for polyline in optimised if len(polyline) >= 2]
    if not optimised:
        raise ValueError("no motif found: try a tighter crop, lower despeckle, or higher gamma")
    return to_unit_box(optimised)


def image_to_motif_svg(data: bytes, **kwargs: object) -> str:
    """The saveable artefact: a motif SVG at CANONICAL_MOTIF_MM on its longest side."""
    return motif_svg(image_to_motif_polylines(data, **kwargs))  # type: ignore[arg-type]


def motif_svg(unit: Polylines) -> str:
    """Serialize unit-box polylines. Split out so a caller that already traced -- the GUI
    preview, which also wants the stroke count -- does not pay for a second trace."""
    points = [point for polyline in unit for point in polyline]
    width = (max(x for x, _ in points) - min(x for x, _ in points)) * CANONICAL_MOTIF_MM
    height = (max(y for _, y in points) - min(y for _, y in points)) * CANONICAL_MOTIF_MM

    # to_unit_box centres on the origin; shift into the positive quadrant for the viewBox.
    placed = [
        [(x * CANONICAL_MOTIF_MM + width / 2.0, y * CANONICAL_MOTIF_MM + height / 2.0) for x, y in polyline]
        for polyline in unit
    ]
    return polylines_to_svg(placed, width_mm=width, height_mm=height)


def _motif_extent_mm(data: bytes) -> tuple[float, float]:
    """Longest side at CANONICAL_MOTIF_MM, so cell_mm means the same at any resolution."""
    try:
        with Image.open(BytesIO(data)) as image:
            width_px, height_px = image.width, image.height
    except (UnidentifiedImageError, OSError) as error:
        raise ValueError(f"unreadable image: {error}") from error
    if width_px <= 0 or height_px <= 0:
        raise ValueError("image has no pixels")

    longest = float(max(width_px, height_px))
    return (
        CANONICAL_MOTIF_MM * width_px / longest,
        CANONICAL_MOTIF_MM * height_px / longest,
    )


def _clamp(value: float, low: float, high: float) -> float:
    return min(high, max(low, value))
