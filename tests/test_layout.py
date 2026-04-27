from neje_oracle.layout import build_hex_layout


def test_hex_layout_stays_within_sheet() -> None:
    placements = build_hex_layout(
        7,
        sheet_width_mm=594,
        sheet_height_mm=841,
        margin_mm=24,
        diameter_mm=160,
    )

    assert len(placements) == 7
    for placement in placements:
        radius = placement.diameter_mm / 2
        assert placement.center_x_mm - radius >= 24
        assert placement.center_y_mm - radius >= 24
        assert placement.center_x_mm + radius <= 594 - 24
        assert placement.center_y_mm + radius <= 841 - 24

