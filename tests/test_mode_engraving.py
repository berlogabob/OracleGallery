"""Contract + engraving-specific coverage for the iso-tone streamline mode."""

from __future__ import annotations

import math

import numpy as np
from mode_contract import check_mode_contract

from neje_oracle.blocks.imaging.art.engraving import engraving, quality_params
from neje_oracle.blocks.imaging.modes import ToneGrid


def test_engraving_contract() -> None:
    report = check_mode_contract(engraving, quality_params, monotonic=True)
    print(report)


def _uniform_tone(darkness: float, *, size_mm: float = 32.0, cell_mm: float = 1.0) -> ToneGrid:
    cells = round(size_mm / cell_mm)
    return ToneGrid(np.full((cells, cells), darkness), cell_mm, size_mm, size_mm)


def _vertical_ramp_tone(*, width_mm: float = 40.0, height_mm: float = 40.0, cell_mm: float = 1.0) -> ToneGrid:
    """Darkness falls top (1.0) to bottom (0.0): the gradient points straight down, so the
    iso-tone direction -- perpendicular to it -- is straight across.
    """
    rows = round(height_mm / cell_mm)
    cols = round(width_mm / cell_mm)
    ramp = np.linspace(1.0, 0.0, rows, dtype=np.float64).reshape(-1, 1)
    return ToneGrid(np.tile(ramp, (1, cols)), cell_mm, width_mm, height_mm)


def _stroke_angles_deg(polylines: list[list[tuple[float, float]]]) -> list[float]:
    """Each stroke's own start-to-end chord angle, folded into [0, 180) so direction (not
    which end is which) is what gets compared.
    """
    angles = []
    for polyline in polylines:
        if len(polyline) < 2:
            continue
        start, end = polyline[0], polyline[-1]
        dx, dy = end[0] - start[0], end[1] - start[1]
        if math.hypot(dx, dy) < 1.0:
            continue  # too short a chord to read a direction from
        angle = math.degrees(math.atan2(dy, dx)) % 180.0
        angles.append(angle)
    return angles


def test_streamlines_follow_iso_tone_direction_on_a_vertical_ramp() -> None:
    """On a top-dark-to-bottom-light ramp the gradient is vertical, so hatch/crosshatch's
    own fixed-angle strokes would run straight across it no matter the image; engraving's
    strokes must instead run along the iso-tone direction, which here is also straight
    across (0 deg) -- the useful check is that the strokes track the FIELD, not a
    coincidence, so most chords must land near horizontal within a wide but real tolerance.
    """
    tone = _vertical_ramp_tone()
    polylines = engraving(tone, line_spacing_mm=1.0)
    angles = _stroke_angles_deg(polylines)
    assert len(angles) >= 5, "too few strokes with a readable chord to judge direction"
    near_horizontal = [angle for angle in angles if angle <= 25.0 or angle >= 155.0]
    assert len(near_horizontal) / len(angles) >= 0.8, (
        "most strokes should run near-horizontal (perpendicular to the vertical gradient)",
        angles,
    )


def test_flat_black_field_inks_via_the_fallback_angle() -> None:
    """A flat field has zero gradient everywhere, so there is no iso-tone direction to
    follow; without the fallback in _direction_field this mode would draw nothing on solid
    black (the trap check_mode_contract's solid_ink assertion catches generically). This
    test pins down that the fallback is what fires, and that it fires at its fixed angle
    rather than an arbitrary one, by checking strokes trend toward _FALLBACK_ANGLE_DEG (30).
    """
    tone = _uniform_tone(1.0)
    polylines = engraving(tone)
    assert polylines, "solid black must still draw"
    ink = sum(math.dist(p[i], p[i + 1]) for p in polylines for i in range(len(p) - 1))
    assert ink > 0

    angles = _stroke_angles_deg(polylines)
    assert len(angles) >= 5
    near_fallback = [angle for angle in angles if abs(angle - 30.0) <= 20.0]
    assert len(near_fallback) / len(angles) >= 0.8, (
        "flat-field strokes should trend toward the fixed fallback angle",
        angles,
    )
