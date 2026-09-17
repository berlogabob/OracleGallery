import math

from neje_oracle.blocks.gcode.estimate import MachineLimits, estimate, line_times

LIMITS = MachineLimits(xy_acceleration_mm_s2=100.0)


def test_long_line_is_a_trapezoid():
    # 100 mm at 60 mm/s, a=100: 0.6 s up, 0.6 s down (36 mm), 64 mm cruise at 60 mm/s.
    xy, pen = estimate("G1 F3600\nG1 X100\n", LIMITS)
    assert math.isclose(xy, 0.6 + 0.6 + 64 / 60, rel_tol=1e-6)
    assert pen == 0


def test_short_segment_never_reaches_feed():
    # 0.5 mm from rest to rest: triangle peak sqrt(a*L) = sqrt(50), far below 133 mm/s.
    xy, _ = estimate("G1 F8000\nG1 X0.5\n", LIMITS)
    assert math.isclose(xy, 2 * math.sqrt(50) / 100, rel_tol=1e-6)
    assert xy > 0.5 / (8000 / 60) * 5


def test_corner_is_faster_than_a_stop_and_slower_than_straight():
    straight, _ = estimate("G1 F3600\nG1 X10\nG1 X20\n", LIMITS)
    corner, _ = estimate("G1 F3600\nG1 X10\nG1 X10 Y10\n", LIMITS)
    reversal, _ = estimate("G1 F3600\nG1 X10\nG1 X0\n", LIMITS)
    assert straight < corner < reversal


def test_dwell_and_z_count_as_pen_time():
    _, pen = estimate("G4 P0.5\nG1 Z-25 F10000\n", LIMITS)
    # 25 mm Z at 1000 mm/s^2 capped at 166.7 mm/s: triangle peak sqrt(25000)=158 < cap.
    assert math.isclose(pen, 0.5 + 2 * math.sqrt(25 * 1000) / 1000, rel_tol=1e-6)


def test_feed_is_modal_and_g0_ignores_it():
    slow, _ = estimate("G1 F600\nG1 X100\nG1 X200\n", LIMITS)
    fast, _ = estimate("G1 F600\nG0 F600 X100\nG0 X200\n", LIMITS)
    assert fast < slow / 5


def test_line_times_are_cumulative_and_indexed_by_line():
    gcode = "; header\nG1 F3600\nG1 X100\nG4 P1\n"
    times = line_times(gcode, LIMITS)
    assert len(times) == 4
    assert times[0] == times[1] == 0
    assert times[3] - times[2] == 1.0
    assert math.isclose(times[-1], sum(estimate(gcode, LIMITS)))


def test_servo_stroke_draws_at_draw_rate_not_z_feed():
    from neje_oracle.blocks.gcode.svg_gcode import _append_polyline_gcode, _draw_feed

    lines: list[str] = []
    _append_polyline_gcode(
        lines,
        [(0.0, 0.0), (10.0, 0.0), (20.0, 0.0)],
        pen_down="G1 Z-25.000 F10000.00",
        pen_up="G0 Z0.000",
        draw_feed=_draw_feed(2500.0, use_z_servo=True),
    )
    assert lines[2] == "G1 X10.000 Y0.000 F2500.00"
    assert lines[3] == "G1 X20.000 Y0.000"
    assert _draw_feed(2500.0, use_z_servo=False) == ""
