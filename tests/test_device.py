import pytest

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


def test_loading_column_lights_one_column_per_tick():
    for tick, column in ((0, 1), (15, 16), (16, 1)):
        messages = device.loading_column(tick)
        assert len(messages) == 3 * 8
        assert {m[2] for m in messages if m[1] == 20} == {column}
        assert {m[2] for m in messages if m[1] == 22} <= set(device.RAINBOW)


def test_loading_column_shifts_hues_each_sweep():
    first = [m[2] for m in device.loading_column(0) if m[1] == 22]
    second = [m[2] for m in device.loading_column(16) if m[1] == 22]
    rainbow = device.RAINBOW
    assert second == [rainbow[(rainbow.index(c) + 1) % len(rainbow)] for c in first]


def test_query():
    assert device.query(35) == device.nrpn(299, 35)


# Column 1's notes


def steps(start, offset):
    return tuple(start + r * offset for r in range(8))


def custom(value):
    return {227: 12, 253: value}


GUITAR = (30, 35, 40, 45, 50, 55, 59, 64)


@pytest.mark.parametrize(
    ("reads", "notes"),
    [
        ({227: 3}, steps(30, 3)),
        ({227: 4}, steps(30, 4)),
        ({227: 5}, (30, 35, 40, 45, 50, 55, 60, 65)),
        ({227: 6}, steps(30, 6)),
        ({227: 7}, steps(30, 7)),
        ({227: 127}, (30,) * 8),
        (custom(28), steps(18, 12)),  # Octave
        (custom(23), steps(30, 7)),
        (custom(32), steps(18, 16)),
        (custom(13), steps(65, -3)),
        (custom(9), steps(65, -7)),
        (custom(0), steps(130, -16)),
        ({227: 13, **dict(zip(range(263, 271), GUITAR))}, GUITAR),
        ({227: 0}, steps(30, 1)),  # No Overlap
        (custom(33), (64, 59, 55, 50, 45, 40, 35, 30)),  # inverted guitar
    ],
)
def test_row_notes(reads, notes):
    assert device.row_notes(reads) == notes


@pytest.mark.parametrize("reads", [{}, {227: 8}, {227: 12}, {227: 13, 263: 30}])
def test_row_notes_unknown(reads):
    assert device.row_notes(reads) is None


@pytest.mark.parametrize(
    ("notes", "octave"),
    [
        ((30, 35, 40, 45, 50, 55, 60, 65), 5),
        (steps(18, 16), 4),  # 130 needs an octave down
        (steps(130, -16), 4),
        (steps(0, 17), 5),  # a tuning spanning 0-119 fits unshifted
    ],
)
def test_fit_octave(notes, octave):
    assert device.fit_octave(notes) == octave


def test_control_map_refuses_repeats():
    assert device.control_map({227: 127}) == (None, 5, device.REFUSE_DUPLICATES)


def test_control_map_refuses_unknown_offset():
    assert device.control_map({227: 8}) == (None, 5, device.REFUSE_ROW_OFFSET)


def test_control_map_fourths():
    notes = {30: 8, 35: 7, 40: 6, 45: 5, 50: 4, 55: 3, 60: 2, 65: 1}
    assert device.control_map({227: 5}) == (notes, 5, None)


def test_control_map_shifts_by_octave():
    note_to_pad, octave, _ = device.control_map(custom(32))
    assert octave == 4
    assert note_to_pad[6] == 8 and note_to_pad[118] == 1


# The control channel


def per_note(channels, main, mode=1):
    reads = {100: mode, 101: main}
    reads.update({101 + c: int(c in channels) for c in range(1, 17)})
    return reads


FACTORY = per_note(range(9, 16), main=16)


def test_factory_split_channels():
    assert device.right_split_channels(FACTORY) == set(range(9, 17))


def test_factory_split_takes_channel_8():
    assert device.control_channel(FACTORY) == (7, [])


def test_one_channel_on_1():
    assert device.control_channel({100: 0, 101: 1}) == (15, [])


def test_per_row_wraps():
    reads = {100: 2, 101: 1, 118: 12}
    assert device.right_split_channels(reads) == {1, 2, 3, 12, 13, 14, 15, 16}
    assert device.control_channel(reads) == (10, [])


def test_all_channels_used_borrows_highest_per_note():
    assert device.control_channel(per_note(range(2, 17), main=1)) == (15, [(117, 0)])


def test_borrow_skips_main_channel():
    assert device.control_channel(per_note(range(1, 16), main=16)) == (14, [(116, 0)])


@pytest.mark.parametrize(
    "reads", [{100: 0}, {101: 1}, {100: 1, 101: 1}, {100: 2, 101: 1}]
)
def test_right_split_unread(reads):
    assert device.right_split_channels(reads) is None
    assert device.control_channel(reads) == (15, [])


def test_free_channel():
    assert device.free_channel(set(range(9, 17))) == 7
    assert device.free_channel(set(range(1, 17))) is None


@pytest.mark.parametrize(
    ("reads", "channel", "clash"),
    [
        (FACTORY, 7, False),
        (FACTORY, 8, True),
        ({100: 0, 101: 8}, 7, True),
        ({100: 2, 101: 1, 118: 6}, 7, True),
        ({100: 1, 101: 1}, 7, False),  # per-note channels unread
    ],
)
def test_channel_clash(reads, channel, clash):
    assert device.channel_clash(reads, channel) is clash


# Setup, poll and restore steps


def queries(*numbers):
    return [m for number in numbers for m in device.query(number)]


def test_read_steps_two_queries_each():
    read = device.read_steps()
    assert len(read) == 15
    assert read[0] == queries(227, 253)
    assert read[-1] == queries(118)  # 29 numbers: the last step holds one


def test_read_numbers():
    assert device.READ_NUMBERS == [227, 253, *range(263, 271), 100, 101, *range(102, 119)]


def test_fixed_steps():
    fixed = device.fixed_steps()
    assert len(fixed) == 11
    assert fixed[0] == device.query(200) + device.nrpn(200, 1)
    assert fixed[1] == device.query(202) + device.nrpn(202, 2)
    assert fixed[-1] == device.query(38) + device.nrpn(38, 7)


def test_computed_settings_factory():
    settings, channel, note_to_pad, refusal = device.computed_settings({227: 5, **FACTORY})
    assert settings == [(1, 8), (36, 5)]
    assert channel == 7
    assert note_to_pad[30] == 8
    assert refusal is None


def test_computed_settings_borrow():
    settings, channel, _, _ = device.computed_settings({227: 5, **per_note(range(2, 17), 1)})
    assert settings == [(1, 16), (36, 5), (117, 0)]
    assert channel == 15


def test_computed_settings_refuses_unread_right_split():
    settings, channel, note_to_pad, refusal = device.computed_settings({227: 5})
    assert settings == [(1, 16), (36, 5)]
    assert (channel, note_to_pad, refusal) == (15, None, device.REFUSE_RIGHT_SPLIT)


def test_computed_settings_row_offset_refusal():
    _, _, note_to_pad, refusal = device.computed_settings({227: 127, **FACTORY})
    assert (note_to_pad, refusal) == (None, device.REFUSE_DUPLICATES)


def test_computed_steps():
    assert device.computed_steps([(1, 8)]) == [device.query(1) + device.nrpn(1, 8)]


@pytest.mark.parametrize(
    ("offset", "numbers"),
    [
        (5, [227, 36, 37, 38]),
        (12, [227, 36, 37, 38, 253]),
        (13, [227, 36, 37, 38, *range(263, 271)]),
    ],
)
def test_poll_numbers(offset, numbers):
    assert device.poll_numbers({227: offset}, 7, False) == [*numbers, 100, 101, 118, 109]


def test_poll_numbers_rescan():
    assert device.poll_numbers({227: 5}, 7, True) == [227, 36, 37, 38, 100, 101, 118, *range(102, 118)]


OFFSETS = [3, 5, 7, 0, 127, 12, 13]


@pytest.mark.parametrize("before", OFFSETS)
@pytest.mark.parametrize("after", OFFSETS)
def test_poll_missed_after_offset_change(before, after):
    # Only a change into custom or Guitar needs reads the last poll didn't make.
    polled = device.poll_numbers({227: before}, 7, False)
    assert device.poll_missed({227: after}, polled, 7, False) is (after in (12, 13) and after != before)


def test_poll_missed_not_when_already_polled():
    polled = device.poll_numbers({227: 12}, 7, False)
    assert device.poll_missed({227: 12}, polled, 7, False) is False


def test_poll_steps():
    assert device.poll_steps([227, 36, 37]) == [queries(227, 36), queries(37)]


SENT = {36: 5, 37: 7, 38: 7}


def test_realign_unchanged():
    note_to_pad, refusal, settings, changed = device.realign({227: 5, **SENT}, SENT)
    assert note_to_pad[65] == 1
    assert (refusal, settings, changed) == (None, [], False)


def test_realign_player_octave():
    _, _, settings, changed = device.realign({227: 5, 36: 7, 37: 7, 38: 7}, SENT)
    assert (settings, changed) == ([(36, 5)], True)


def test_realign_offset_change():
    note_to_pad, _, settings, changed = device.realign({227: 0, **SENT}, SENT)
    assert note_to_pad == {30 + r: 8 - r for r in range(8)}
    assert (settings, changed) == ([], False)


def test_realign_new_octave_is_not_a_player_change():
    _, _, settings, changed = device.realign({**custom(32), **SENT}, SENT)
    assert (settings, changed) == ([(36, 4)], False)


def test_realign_refused():
    note_to_pad, refusal, settings, _ = device.realign({227: 127, **SENT}, SENT)
    assert (note_to_pad, refusal, settings) == (None, device.REFUSE_DUPLICATES, [])


def test_split_restore_follows_numbers_order():
    assert device.split_restore({35: 0, 200: 0}, [200, 35]) == [
        device.nrpn(200, 0),
        device.nrpn(35, 0),
    ]


def test_split_restore_skips_missing():
    assert device.split_restore({202: 5}, [200, 202]) == [device.nrpn(202, 5)]


def test_split_restore_empty():
    assert device.split_restore({}, [200]) == []


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
