from __future__ import annotations

from neje_oracle.shared.models import SheetPlacement
from neje_oracle.shared.origin_markers import (
    ORIGIN_FILLER_MACBOOK,
    ORIGIN_REAL_MACMINI,
    ORIGIN_TEST_MACBOOK,
    ORIGIN_TEST_MACMINI,
    classify_session_origin,
    marker_center_for_position,
    marker_position_for_origin,
)


def test_classify_session_origin_for_current_sources() -> None:
    real = classify_session_origin({})
    assert real.origin == ORIGIN_REAL_MACMINI
    assert real.tags == ["real", "oracle", "macmini"]
    assert real.visible_in_library is True

    test_macbook = classify_session_origin({"kind": "test-user", "generatedBy": "neje-generate-sessions"})
    assert test_macbook.origin == ORIGIN_TEST_MACBOOK
    assert test_macbook.visible_in_library is False

    test_macmini = classify_session_origin({"kind": "test-user", "sourceMachine": "mac-mini"})
    assert test_macmini.origin == ORIGIN_TEST_MACMINI
    assert test_macmini.visible_in_library is False

    filler = classify_session_origin({"kind": "filler"})
    assert filler.origin == ORIGIN_FILLER_MACBOOK
    assert filler.tags == ["filler", "local", "macbook"]


def test_marker_positions_stay_inside_cell_ring() -> None:
    placement = SheetPlacement(index=0, center_x_mm=100, center_y_mm=100, diameter_mm=80)
    for origin in (ORIGIN_REAL_MACMINI, ORIGIN_TEST_MACBOOK, ORIGIN_TEST_MACMINI, ORIGIN_FILLER_MACBOOK):
        x, y = marker_center_for_position(
            placement,
            marker_position_for_origin(origin),
            marker_diameter_mm=1.5,
        )
        distance = ((x - placement.center_x_mm) ** 2 + (y - placement.center_y_mm) ** 2) ** 0.5
        assert distance < placement.diameter_mm / 2
