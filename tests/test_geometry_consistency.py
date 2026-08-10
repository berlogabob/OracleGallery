from neje_oracle.shared.gui_settings import GuiSettings
from neje_oracle.shared.models import PlotterRuntimeConfig

# Keep these synchronized with echodraw/hardware/GEOMETRY.md, which was corrected against
# the running controller on 2026-08-07 ($CD: X 255, Y 440, both homing negative to 0).
# The previous values here claimed Y travel was 420 mm and asserted a "20 mm overshoot"
# that does not exist -- that came from a pre-servo draft config which was never flashed.
HARDWARE_TRAVEL_X_MM = 255.0
HARDWARE_TRAVEL_Y_MM = 440.0


def test_default_sheet_fits_hardware_travel() -> None:
    settings = GuiSettings()
    assert settings.sheet_width_mm <= HARDWARE_TRAVEL_X_MM
    assert settings.sheet_height_mm <= HARDWARE_TRAVEL_Y_MM


def test_gui_and_runtime_config_defaults_agree() -> None:
    """The operator's defaults and the daemon's defaults must describe one machine."""
    settings = GuiSettings()
    config = PlotterRuntimeConfig()
    assert (settings.sheet_width_mm, settings.sheet_height_mm) == (
        config.sheet_width_mm,
        config.sheet_height_mm,
    )


def test_default_sheet_height_has_no_y_margin() -> None:
    """440 mm of sheet in 440 mm of travel leaves nothing for the work-zero offset.

    Not a bug in itself, but it is why the preflight travel check has to subtract the G54
    offset (see SystemCheckService._check_tinybee_hardware). If either number changes,
    update GEOMETRY.md and this test.
    """
    assert GuiSettings().sheet_height_mm == HARDWARE_TRAVEL_Y_MM
