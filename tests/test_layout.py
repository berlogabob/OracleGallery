import pytest

from neje_oracle.blocks.gcode.layout import build_grid_layout, build_hex_layout, build_sheet_layout, group_layout_rows


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


def test_grid_layout_stays_within_sheet() -> None:
    placements = build_grid_layout(
        9,
        sheet_width_mm=594,
        sheet_height_mm=841,
        margin_mm=24,
        diameter_mm=160,
    )

    assert len(placements) == 9
    assert placements[0].center_x_mm == placements[3].center_x_mm
    for placement in placements:
        radius = placement.diameter_mm / 2
        assert placement.center_x_mm - radius >= 24
        assert placement.center_y_mm - radius >= 24
        assert placement.center_x_mm + radius <= 594 - 24
        assert placement.center_y_mm + radius <= 841 - 24


def test_grid_layout_accepts_zero_diameter() -> None:
    placements = build_grid_layout(
        count=5,
        sheet_width_mm=100,
        sheet_height_mm=100,
        margin_mm=0,
        diameter_mm=0,
        gap_mm=0,
    )

    assert isinstance(placements, list)


def test_hex_layout_accepts_zero_diameter() -> None:
    placements = build_hex_layout(
        count=5,
        sheet_width_mm=100,
        sheet_height_mm=100,
        margin_mm=0,
        diameter_mm=0,
        gap_mm=0,
    )

    assert isinstance(placements, list)


def test_hex_layout_offsets_odd_rows_inside_bounds() -> None:
    placements = build_hex_layout(
        6,
        sheet_width_mm=594,
        sheet_height_mm=841,
        margin_mm=24,
        diameter_mm=160,
    )

    assert placements[0].center_y_mm == placements[1].center_y_mm
    assert placements[3].center_y_mm > placements[0].center_y_mm
    assert placements[3].center_x_mm > placements[0].center_x_mm


def test_hex_layout_odd_rows_have_one_less_cell_than_even_rows() -> None:
    placements = build_hex_layout(
        20,
        sheet_width_mm=300,
        sheet_height_mm=260,
        margin_mm=0,
        diameter_mm=80,
    )

    first_row_y = placements[0].center_y_mm
    second_row_y = next(placement.center_y_mm for placement in placements if placement.center_y_mm > first_row_y)
    first_row = [placement for placement in placements if placement.center_y_mm == first_row_y]
    second_row = [placement for placement in placements if placement.center_y_mm == second_row_y]

    assert len(first_row) == 3
    assert len(second_row) == 2
    assert second_row[0].center_x_mm == first_row[0].center_x_mm + 40


def test_grid_layout_centers_used_cells_in_printable_area() -> None:
    placements = build_grid_layout(
        6,
        sheet_width_mm=250,
        sheet_height_mm=440,
        margin_mm=0,
        diameter_mm=80,
    )

    min_x = min(placement.center_x_mm - placement.diameter_mm / 2 for placement in placements)
    max_x = max(placement.center_x_mm + placement.diameter_mm / 2 for placement in placements)
    min_y = min(placement.center_y_mm - placement.diameter_mm / 2 for placement in placements)
    max_y = max(placement.center_y_mm + placement.diameter_mm / 2 for placement in placements)

    assert (min_x + max_x) / 2 == pytest.approx(125)
    assert (min_y + max_y) / 2 == pytest.approx(220)


def test_grid_gap_is_distance_between_cell_diameters() -> None:
    placements = build_grid_layout(
        2,
        sheet_width_mm=300,
        sheet_height_mm=120,
        margin_mm=0,
        diameter_mm=80,
        gap_mm=10,
    )

    first_right_edge = placements[0].center_x_mm + placements[0].diameter_mm / 2
    second_left_edge = placements[1].center_x_mm - placements[1].diameter_mm / 2

    assert second_left_edge - first_right_edge == pytest.approx(10)


def test_hex_gap_is_distance_between_even_row_cell_diameters() -> None:
    placements = build_hex_layout(
        2,
        sheet_width_mm=300,
        sheet_height_mm=180,
        margin_mm=0,
        diameter_mm=80,
        gap_mm=10,
    )

    first_right_edge = placements[0].center_x_mm + placements[0].diameter_mm / 2
    second_left_edge = placements[1].center_x_mm - placements[1].diameter_mm / 2

    assert second_left_edge - first_right_edge == pytest.approx(10)


def test_hex_layout_centers_used_cells_in_printable_area() -> None:
    placements = build_hex_layout(
        5,
        sheet_width_mm=250,
        sheet_height_mm=440,
        margin_mm=0,
        diameter_mm=80,
    )

    min_x = min(placement.center_x_mm - placement.diameter_mm / 2 for placement in placements)
    max_x = max(placement.center_x_mm + placement.diameter_mm / 2 for placement in placements)
    min_y = min(placement.center_y_mm - placement.diameter_mm / 2 for placement in placements)
    max_y = max(placement.center_y_mm + placement.diameter_mm / 2 for placement in placements)

    assert (min_x + max_x) / 2 == pytest.approx(125)
    assert (min_y + max_y) / 2 == pytest.approx(220)


def test_group_layout_rows_keeps_left_to_right_order() -> None:
    placements = build_hex_layout(
        5,
        sheet_width_mm=300,
        sheet_height_mm=260,
        margin_mm=0,
        diameter_mm=80,
    )

    rows = group_layout_rows(placements)

    assert [len(row) for row in rows[:2]] == [3, 2]
    assert all(row[index].center_x_mm <= row[index + 1].center_x_mm for row in rows for index in range(len(row) - 1))


def test_organic_layout_is_deterministic_and_varied() -> None:
    first = build_sheet_layout(
        9,
        mode="grid",
        sheet_width_mm=300,
        sheet_height_mm=300,
        margin_mm=0,
        diameter_mm=80,
        organic_enabled=True,
        organic_cell_size_mm=18,
        organic_rotation_ramp=1,
        organic_scale_ramp=1,
        organic_seed=42,
    )
    second = build_sheet_layout(
        9,
        mode="grid",
        sheet_width_mm=300,
        sheet_height_mm=300,
        margin_mm=0,
        diameter_mm=80,
        organic_enabled=True,
        organic_cell_size_mm=18,
        organic_rotation_ramp=1,
        organic_scale_ramp=1,
        organic_seed=42,
    )
    regular = build_grid_layout(9, sheet_width_mm=300, sheet_height_mm=300, margin_mm=0, diameter_mm=80)

    assert first == second
    assert any((organic.center_x_mm, organic.center_y_mm) != (base.center_x_mm, base.center_y_mm) for organic, base in zip(first, regular, strict=True))
    assert any(abs(placement.rotation_deg) > 0.001 for placement in first)
    assert any(abs(placement.symbol_scale - 1.0) > 0.001 for placement in first)


def test_organic_layout_stays_inside_printable_bounds_and_keeps_row_groups() -> None:
    placements = build_sheet_layout(
        12,
        mode="hex",
        sheet_width_mm=300,
        sheet_height_mm=300,
        margin_mm=10,
        diameter_mm=80,
        organic_enabled=True,
        organic_cell_size_mm=80,
        organic_rotation_ramp=1,
        organic_scale_ramp=1,
        organic_seed=12,
    )
    regular_rows = group_layout_rows(
        build_sheet_layout(12, mode="hex", sheet_width_mm=300, sheet_height_mm=300, margin_mm=10, diameter_mm=80)
    )
    organic_rows = group_layout_rows(placements)

    assert [len(row) for row in organic_rows] == [len(row) for row in regular_rows]
    for placement in placements:
        radius = placement.diameter_mm / 2
        assert placement.center_x_mm - radius >= 10
        assert placement.center_y_mm - radius >= 10
        assert placement.center_x_mm + radius <= 300 - 10
        assert placement.center_y_mm + radius <= 300 - 10


def test_organic_disabled_keeps_regular_layout() -> None:
    regular = build_grid_layout(9, sheet_width_mm=300, sheet_height_mm=300, margin_mm=0, diameter_mm=80)
    disabled = build_sheet_layout(
        9,
        mode="grid",
        sheet_width_mm=300,
        sheet_height_mm=300,
        margin_mm=0,
        diameter_mm=80,
        organic_enabled=False,
        organic_cell_size_mm=80,
        organic_rotation_ramp=1,
        organic_scale_ramp=1,
        organic_seed=12,
    )

    assert disabled == regular
