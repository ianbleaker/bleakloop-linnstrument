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
