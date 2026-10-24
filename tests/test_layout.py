import pytest

from BleakLoop.core import layout


@pytest.mark.parametrize("pad", range(1, 9))
def test_round_trip(pad):
    assert layout.pad_of(layout.device_row(pad)) == pad


def test_nearest_row_is_pad_8():
    assert layout.device_row(8) == 0
    assert layout.device_row(1) == 7


@pytest.mark.parametrize("pad", [0, 9])
def test_device_row_rejects_bad_pad(pad):
    with pytest.raises(ValueError):
        layout.device_row(pad)


@pytest.mark.parametrize("row", [-1, 8])
def test_pad_of_rejects_bad_row(row):
    with pytest.raises(ValueError):
        layout.pad_of(row)


def test_control_pad():
    assert layout.control_pad(102) == 8
    assert layout.control_pad(109) == 1


@pytest.mark.parametrize("cc", [101, 110])
def test_control_pad_rejects_bad_cc(cc):
    with pytest.raises(ValueError):
        layout.control_pad(cc)


def test_move_up_and_left_from_origin_stays():
    origin = layout.Window()
    assert layout.move_window(origin, 0, -1, 20, 20) == origin
    assert layout.move_window(origin, -1, 0, 20, 20) == origin


def test_move_down_stops_at_last_full_window():
    window = layout.Window(0, 13)
    assert layout.move_window(window, 0, 1, 20, 20) == layout.Window(0, 13)


def test_move_right_stops_at_last_full_window():
    window = layout.Window(7, 0)
    assert layout.move_window(window, 1, 0, 20, 20) == layout.Window(7, 0)


def test_short_session_stays_at_origin():
    origin = layout.Window()
    assert layout.move_window(origin, 0, 1, 20, 5) == origin
    assert layout.move_window(origin, 1, 0, 0, 20) == origin


def test_move_one_step():
    assert layout.move_window(layout.Window(2, 3), 1, 0, 20, 20) == layout.Window(3, 3)
    assert layout.move_window(layout.Window(2, 3), 0, 1, 20, 20) == layout.Window(2, 4)


def test_scroll_to_scene_above_window():
    assert layout.scroll_to_scene(layout.Window(2, 5), 3, 20, 20) == layout.Window(2, 3)


def test_scroll_to_scene_below_window():
    assert layout.scroll_to_scene(layout.Window(2, 0), 9, 20, 20) == layout.Window(2, 3)


def test_scroll_to_scene_inside_window_stays():
    assert layout.scroll_to_scene(layout.Window(2, 4), 10, 20, 20) == layout.Window(2, 4)


def test_scroll_to_scene_below_window_near_end_is_clamped():
    # Scene 9 is the last of 10; the window can't start past scene 3.
    assert layout.scroll_to_scene(layout.Window(0, 0), 9, 20, 10) == layout.Window(0, 3)
