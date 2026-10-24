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
