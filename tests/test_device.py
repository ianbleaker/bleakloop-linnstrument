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
    steps = device.split_setup()
    assert len(steps) == 13
    assert steps[0] == device.query(200) + device.nrpn(200, 1)
    assert steps[3][-6:] == device.nrpn(1, 1)  # main channel 1
    assert steps[5] == device.query(40) + device.nrpn(40, 102)
    assert steps[-1] == device.query(47) + device.nrpn(47, 109)


def test_query():
    assert device.query(35) == device.nrpn(299, 35)


def test_split_restore_follows_setup_order():
    assert device.split_restore({35: 0, 200: 0}) == [device.nrpn(200, 0), device.nrpn(35, 0)]


def test_split_restore_skips_missing():
    assert device.split_restore({202: 5}) == [device.nrpn(202, 5)]


def test_split_restore_empty():
    assert device.split_restore({}) == []


def feed_all(reader, messages):
    return [r for _, number, value in messages if (r := reader.feed(number, value)) is not None]


def test_reader_decodes_reply():
    assert feed_all(device.NrpnReader(), device.nrpn(202, 2)) == [(202, 2)]


def test_reader_decodes_value_msb():
    assert feed_all(device.NrpnReader(), device.nrpn(40, 300)) == [(40, 300)]


def test_reader_needs_whole_reply():
    assert device.NrpnReader().feed(38, 1) is None


def test_reader_resets_mid_reply():
    reader = device.NrpnReader()
    for _, number, value in device.nrpn(202, 2)[:3]:
        reader.feed(number, value)
    reader.feed(101, 127)
    assert reader.feed(38, 2) is None


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
