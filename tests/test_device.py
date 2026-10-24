from BleakLoop import device
from BleakLoop.core.leds import BLUE, DEVICE_DEFAULT, OFF, WHITE, Clock, Light

CLOCK = Clock(beats=0.0, now_ms=0)


def test_nrpn_bytes():
    assert device.nrpn(245, 1) == [
        (0xB0, 99, 1),
        (0xB0, 98, 117),
        (0xB0, 6, 0),
        (0xB0, 38, 1),
        (0xB0, 101, 127),
        (0xB0, 100, 127),
    ]


def test_light_bytes():
    assert device.light(1, 8, 8) == [(0xB0, 20, 1), (0xB0, 21, 0), (0xB0, 22, 8)]


def test_user_firmware_mode():
    assert device.user_firmware_mode(True) == device.nrpn(245, 1)
    assert device.user_firmware_mode(False) == device.nrpn(245, 0)


def test_y_axis_off_on_all_rows():
    assert device.y_axis(False) == [(0xB0 + ch, 11, 0) for ch in range(8)]


def test_split_setup():
    messages = device.split_setup()
    assert len(messages) == 78
    assert messages[:6] == device.nrpn(200, 1)
    assert device.nrpn(1, 1) == messages[18:24]  # main channel 1
    assert messages[-6:] == device.nrpn(47, 8)


def frame(mode_colour=WHITE):
    return {(1, 5): Light(OFF), (1, 8): Light(mode_colour), (2, 1): Light(OFF)}


def test_driver_sends_everything_first():
    driver = device.LedDriver()
    assert driver.update(frame(), CLOCK) == (
        device.light(1, 5, OFF) + device.light(1, 8, WHITE) + device.light(2, 1, OFF)
    )


def test_driver_sends_nothing_when_unchanged():
    driver = device.LedDriver()
    driver.update(frame(), CLOCK)
    assert driver.update(frame(), CLOCK) == []


def test_driver_sends_only_changes():
    driver = device.LedDriver()
    driver.update(frame(), CLOCK)
    assert driver.update(frame(BLUE), CLOCK) == device.light(1, 8, BLUE)


def test_driver_repaints_after_reset():
    driver = device.LedDriver()
    driver.update(frame(), CLOCK)
    driver.reset()
    assert len(driver.update(frame(), CLOCK)) == 9


def test_release_column_1():
    driver = device.LedDriver()
    expected = [m for pad in range(1, 9) for m in device.light(1, pad, DEVICE_DEFAULT)]
    assert driver.release_column_1() == expected
