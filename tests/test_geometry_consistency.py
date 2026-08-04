from neje_oracle.shared.config import PlotterSettings


# Keep these synchronized with echodraw/hardware/GEOMETRY.md.
HARDWARE_TRAVEL_X_MM = 255.0
HARDWARE_TRAVEL_Y_MM = 420.0


def test_default_sheet_width_fits_hardware_travel() -> None:
    assert PlotterSettings().sheet_width_mm <= HARDWARE_TRAVEL_X_MM


def test_default_sheet_height_known_overshoot_is_visible() -> None:
    """This test exists to make the 20 mm overshoot visible.

    If either value changes, update GEOMETRY.md and this test.
    """
    assert PlotterSettings().sheet_height_mm == 440.0
    assert HARDWARE_TRAVEL_Y_MM == 420.0
