"""Circle packing: non-overlapping circles, small and crowded where the picture is dark.

Candidate centres are walked in a fixed order and each one takes the largest circle that fits
without touching a circle already placed, capped by what the local tone allows. Dark tone caps
the radius low, so a shadow fills with many small circles and a highlight with a few large
ones -- which is also what makes ink follow darkness, since a circle's perimeter grows with r
while the number of circles that fit in an area grows with 1/r^2. Halving the radius doubles
the ink over the same patch.

The candidate order is a deterministic low-discrepancy sequence, not an RNG: the same picture
must give the same plot, and an R2 sequence spreads far more evenly than a seeded uniform draw,
which clumps and leaves visible holes at this density.
"""

from __future__ import annotations

import math
from collections import defaultdict

from ..modes import Polylines, ToneGrid, _sample_darkness

HELP = (
    "Non-overlapping circles sized by brightness: dark areas pack many small ones, "
    "light areas a few large. Detail = smallest circle radius in mm."
)

MAX_CIRCLES_DEFAULT = 6_000
# The R2 sequence: the plastic constant is to two dimensions what the golden ratio is to one.
# Using the golden ratio twice (phi, phi^2) looks right and is not: phi + phi^2 == 1, so every
# candidate lands on one of two diagonal lines and the "pack" is two stripes. Measured before
# the fix: 34 circles on a solid black 64 mm square, where the plastic pair places 1100.
_PLASTIC = 1.324717957244746
_R2_X = 1.0 / _PLASTIC
_R2_Y = 1.0 / (_PLASTIC * _PLASTIC)
# Points per circle, at the largest radius. Fewer at small radii (see _ring): a 1 mm circle
# drawn with 40 points spends vertices on a curve the pen cannot resolve.
_MAX_RING_POINTS = 40
_MIN_RING_POINTS = 8


def _ring(cx: float, cy: float, radius: float) -> list[tuple[float, float]]:
    points = max(_MIN_RING_POINTS, min(_MAX_RING_POINTS, int(radius * 12)))
    ring = [
        (cx + radius * math.cos(2.0 * math.pi * i / points), cy + radius * math.sin(2.0 * math.pi * i / points))
        for i in range(points)
    ]
    ring.append(ring[0])
    return ring


def circlepack(
    tone: ToneGrid,
    *,
    min_radius_mm: float = 0.8,
    max_radius_mm: float = 6.0,
    candidates: int = 6_000,
    min_darkness: float = 0.10,
    max_circles: int = MAX_CIRCLES_DEFAULT,
) -> Polylines:
    """Greedily place circles at candidate points, radius capped by local tone.

    The tone cap is `max_radius` at `min_darkness` falling to `min_radius` at full black, so
    the picture reads as density rather than as size alone. A candidate whose allowed radius
    is already below `min_radius_mm` is dropped rather than drawn small: that is the white
    gate, and it is why paper stays bare instead of filling with minimum-radius circles.

    Neighbours are found through a bucket grid at `max_radius_mm`, so each placement tests a
    handful of circles rather than every circle placed so far. The obvious all-pairs version
    is quadratic and takes minutes at the shipped candidate count.
    """
    if min_radius_mm <= 0 or max_radius_mm < min_radius_mm:
        raise ValueError("radii must be positive and max_radius_mm >= min_radius_mm")
    if candidates <= 0:
        raise ValueError("candidates must be positive")
    if min_darkness < 0:
        raise ValueError("min_darkness must be non-negative")

    if tone.darkness.size == 0:
        return []

    # TWICE the largest radius, not the radius: two max-size circles overlap whenever their
    # centres are closer than 2 * max_radius_mm, and at one radius per bucket a pair 1.9 radii
    # apart sits two buckets away and is never compared. That is invisible on a flat tone,
    # where every circle is the same size, and shows up as crossed circles the moment sizes
    # vary -- which is to say, on every real picture.
    bucket_mm = max(2.0 * max_radius_mm, 1e-6)
    buckets: dict[tuple[int, int], list[tuple[float, float, float]]] = defaultdict(list)
    polylines: Polylines = []

    def free_radius(x: float, y: float, wanted: float) -> float:
        """The largest radius at (x, y) that touches nothing, capped at `wanted`."""
        col, row = int(x / bucket_mm), int(y / bucket_mm)
        allowed = min(wanted, x, y, tone.width_mm - x, tone.height_mm - y)
        for dc in (-1, 0, 1):
            for dr in (-1, 0, 1):
                for ox, oy, orad in buckets.get((col + dc, row + dr), ()):
                    allowed = min(allowed, math.dist((x, y), (ox, oy)) - orad)
                    if allowed < min_radius_mm:
                        return allowed
        return allowed

    wanted: list[tuple[float, float, float]] = []
    for index in range(candidates):
        # An even sweep with no lattice alignment, and the same sequence for every render of
        # the same picture.
        x = ((index * _R2_X) % 1.0) * tone.width_mm
        y = ((index * _R2_Y) % 1.0) * tone.height_mm
        value = _sample_darkness(tone, x, y)
        if value < min_darkness:
            continue
        # Dark caps the radius small; the span is measured from the gate, not from zero, so
        # the first tone that draws at all still gets a full-size circle. Clamped to the floor
        # rather than merely computed down to it: at full black the expression is exactly
        # min_radius_mm in real arithmetic and 0.7999999999999998 in floats, and the "solid
        # black must draw something" check then found nothing at all.
        reach = (value - min_darkness) / max(1e-6, 1.0 - min_darkness)
        wanted.append((max(min_radius_mm, max_radius_mm - reach * (max_radius_mm - min_radius_mm)), x, y))

    # Largest first, so the light areas claim their space before the dark ones fill in around
    # them. In candidate order the packing is what carries the picture instead of the tone:
    # once the sheet is half full every later circle takes whatever gap is left, and the
    # result is an even field of mixed sizes that reads as texture, not as a photograph.
    wanted.sort(key=lambda item: -item[0])
    for want, x, y in wanted:
        if len(polylines) >= max_circles:
            break
        radius = free_radius(x, y, want)
        if radius < min_radius_mm:
            continue
        buckets[(int(x / bucket_mm), int(y / bucket_mm))].append((x, y, radius))
        polylines.append(_ring(x, y, radius))
    return polylines


def quality_params(spacing_mm: float) -> dict[str, float | int]:
    """Radii and candidate count from the quality fader.

    Radii track spacing_mm and reproduce the defaults (0.8 / 6.0) at the draft rung
    (spacing 2.5). Candidates rise as the radius floor falls, because a finer pack needs more
    attempts to find the gaps; the product is what the segment cap sees, so both move together
    rather than the count alone.
    """
    return {
        "min_radius_mm": max(0.35, spacing_mm * 0.32),
        "max_radius_mm": max(2.5, spacing_mm * 2.4),
        "candidates": int(min(30_000, 3_000 * (2.5 / max(0.5, spacing_mm)) ** 1.5)),
    }
