from BleakLoop.core import layout


def test_play_stop_comes_from_the_registry():
    assert layout.PLAY_STOP == (1, 1)
