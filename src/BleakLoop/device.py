"""LinnStrument message building and the LED driver (architecture section 5). Pure Python."""

from .core import layout
from .core.leds import (
    BLUE,
    CYAN,
    DEVICE_DEFAULT,
    GREEN,
    LIME,
    MAGENTA,
    ORANGE,
    PINK,
    RED,
    YELLOW,
    resolve,
)
from .core.model import PadPress, SlideMoved, XAxis
from .core.values import SPLIT_POINT

CC_STATUS = 0xB0

# Device protocol numbers.
NRPN_USER_FIRMWARE_MODE = 245
NRPN_QUERY = 299
CC_SLIDE_MODE = 9
CC_X_AXIS = 10
CC_Y_AXIS = 11
CC_LIGHT_COLUMN = 20
CC_LIGHT_ROW = 21
CC_LIGHT_COLOUR = 22
NRPN_LEFT_MAIN_CHANNEL = 1  # left split main channel: the control channel
NRPN_ROW_OFFSET = 227  # global Row Offset
NRPN_CUSTOM_ROW_OFFSET = 253  # Row Offset when 227 = 12: offset + 16
NRPN_GUITAR_TUNING = tuple(range(263, 271))  # Guitar Row Offset: each row's note, nearest first
NRPN_OCTAVE = 36  # left split Octave
NRPN_TRANSPOSE_PITCH = 37  # left split Transpose Pitch
NRPN_TRANSPOSE_LIGHTS = 38  # left split Transpose Lights
NRPN_RIGHT_MIDI_MODE = 100  # right split MIDI mode: 0 one channel, 1 per note, 2 per row
NRPN_RIGHT_MAIN_CHANNEL = 101  # right split main channel
NRPN_RIGHT_PER_NOTE = tuple(range(102, 118))  # right split per-note channel c on: 101 + c
NRPN_RIGHT_PER_ROW_LOWEST = 118  # right split per-row lowest channel
OCTAVE_ZERO = 5  # Octave value for no shift
TRANSPOSE_ZERO = 7  # Transpose value for no shift

# The left split, in setup order. Each is queried first, for the restore.
FIXED_SETTINGS = [
    (200, 1),  # split on
    (202, SPLIT_POINT),  # left split is column 1
    (0, 0),  # left split MIDI mode: one channel
    (20, 0),  # left split Send X off
    (24, 0),  # left split Send Y off
    (27, 0),  # left split Send Z off
    (32, 0),  # left split Played colour off: column 1 keeps BleakLoop's lights
    (34, 0),  # left split LowRow off: pad 8 stays a pad
    (35, 0),  # left split special mode off: a note split
    (NRPN_TRANSPOSE_PITCH, TRANSPOSE_ZERO),
    (NRPN_TRANSPOSE_LIGHTS, TRANSPOSE_ZERO),
]

# Read before any set: Row Offset, then the right split's channels.
READ_NUMBERS = [
    NRPN_ROW_OFFSET,
    NRPN_CUSTOM_ROW_OFFSET,
    *NRPN_GUITAR_TUNING,
    NRPN_RIGHT_MIDI_MODE,
    NRPN_RIGHT_MAIN_CHANNEL,
    *NRPN_RIGHT_PER_NOTE,
    NRPN_RIGHT_PER_ROW_LOWEST,
]

REFUSE_DUPLICATES = "Row Offset repeats notes in column 1: controls off"
REFUSE_ROW_OFFSET = "Couldn't read Row Offset: controls off"
REFUSE_RIGHT_SPLIT = "Couldn't read the right split: controls off"
REFUSE_CHANNELS = "The right split uses every channel: controls off"
CONTROLS_ON = "Column 1 controls on"
CONTROLS_MOVED = "The right split took column 1's channel: controls moved to channel {}"
OCTAVE_RESET = "Left split Octave/Transpose reset: select the right split to change yours"


def cc(channel, number, value):
    return [(CC_STATUS + channel, number, value)]


def nrpn(number, value):
    return [
        (CC_STATUS, 99, number >> 7),
        (CC_STATUS, 98, number & 127),
        (CC_STATUS, 6, value >> 7),
        (CC_STATUS, 38, value & 127),
        (CC_STATUS, 101, 127),
        (CC_STATUS, 100, 127),
    ]


def query(number):
    return nrpn(NRPN_QUERY, number)


def light(column, pad, colour):
    return (
        cc(0, CC_LIGHT_COLUMN, column)
        + cc(0, CC_LIGHT_ROW, layout.device_row(pad))
        + cc(0, CC_LIGHT_COLOUR, colour)
    )


# The loading rainbow's hues, in order.
RAINBOW = (RED, ORANGE, YELLOW, LIME, GREEN, CYAN, BLUE, MAGENTA, PINK)


def loading_column(tick):
    # One column of the loading rainbow per setup tick, sweeping columns 1-16. Each sweep
    # shifts the diagonal hues by one, so the rainbow rolls.
    sweep, index = divmod(tick, layout.COLUMNS - 1)
    column = index + 1
    return [
        m
        for pad in range(1, layout.ROWS + 1)
        for m in light(column, pad, RAINBOW[(column + pad + sweep) % len(RAINBOW)])
    ]


def user_firmware_mode(on):
    return nrpn(NRPN_USER_FIRMWARE_MODE, 1 if on else 0)


def y_axis(on):
    return [m for channel in range(layout.ROWS) for m in cc(channel, CC_Y_AXIS, int(on))]


def x_rows(rows):
    # X and slide mode on for the device rows in rows, off for the others.
    return [
        m
        for channel in range(layout.ROWS)
        for number in (CC_X_AXIS, CC_SLIDE_MODE)
        for m in cc(channel, number, int(channel in rows))
    ]


# Column 1's notes (architecture section 5, "Note numbers in a playing split").


def row_notes(reads):
    # Rows nearest first, at Octave and Transpose 0. None when Row Offset can't be read.
    setting = reads.get(NRPN_ROW_OFFSET)
    rows = range(8)
    if setting in (3, 4, 5, 6, 7):
        return tuple(30 + r * setting for r in rows)
    if setting == 127:  # zero offset
        return (30,) * 8
    if setting == 0:  # No Overlap: the offset is the split's width
        return tuple(30 + r * (SPLIT_POINT - 1) for r in rows)
    if setting == 12:
        custom = reads.get(NRPN_CUSTOM_ROW_OFFSET)
        if custom is None:
            return None
        if custom == 33:  # inverted guitar: rows 0 and 1 one lower
            return tuple(65 - 5 * r - (r <= 1) for r in rows)
        offset = custom - 16
        if offset >= 12:
            start = 18
        elif offset <= -12:
            start = 18 - 7 * offset
        elif offset < 0:
            start = 65
        else:
            start = 30
        return tuple(start + r * offset for r in rows)
    if setting == 13:  # Guitar
        tuning = tuple(reads.get(number) for number in NRPN_GUITAR_TUNING)
        return None if None in tuning else tuning
    return None


def fit_octave(notes):
    # The Octave closest to no shift, ties lower, that keeps every note in 0-127.
    # Every firmware Row Offset spans at most 112, so one always fits.
    for octave in sorted(range(11), key=lambda v: (abs(v - OCTAVE_ZERO), v)):
        shift = 12 * (octave - OCTAVE_ZERO)
        if all(0 <= note + shift <= 127 for note in notes):
            return octave
    return None


def control_map(reads):
    # (note -> pad, Octave, refusal message).
    notes = row_notes(reads)
    if notes is None:
        return None, OCTAVE_ZERO, REFUSE_ROW_OFFSET
    if len(set(notes)) < len(notes):
        return None, OCTAVE_ZERO, REFUSE_DUPLICATES
    octave = fit_octave(notes)
    shift = 12 * (octave - OCTAVE_ZERO)
    return {note + shift: layout.pad_of(row) for row, note in enumerate(notes)}, octave, None


def right_split_channels(reads):
    # 1-based channels the right split plays on. None when a read it needs is missing.
    mode = reads.get(NRPN_RIGHT_MIDI_MODE)
    main = reads.get(NRPN_RIGHT_MAIN_CHANNEL)
    if mode is None or main is None:
        return None
    used = {main}
    if mode == 1:
        per_note = [reads.get(number) for number in NRPN_RIGHT_PER_NOTE]
        if None in per_note:
            return None
        used |= {channel for channel, on in enumerate(per_note, 1) if on}
    elif mode == 2:
        lowest = reads.get(NRPN_RIGHT_PER_ROW_LOWEST)
        if lowest is None:
            return None
        used |= {(lowest - 1 + row) % 16 + 1 for row in range(8)}
    return used


def free_channel(used):
    # 0-based: the highest channel outside the right split's, or None.
    return next((channel - 1 for channel in range(16, 0, -1) if channel not in used), None)


def channel_clash(reads, channel):
    # Whether the right split plays on the 0-based channel. False when it can't be read.
    used = right_split_channels(reads)
    return used is not None and channel + 1 in used


def control_channel(reads):
    # (0-based channel, right split changes). The highest channel the right split leaves
    # free; with none free, its highest per-note channel other than the main one.
    used = right_split_channels(reads)
    if used is None:
        return 15, []
    channel = free_channel(used)
    if channel is not None:
        return channel, []
    main = reads[NRPN_RIGHT_MAIN_CHANNEL]
    channel = max(channel for channel in used if channel != main)
    return channel - 1, [(NRPN_RIGHT_MAIN_CHANNEL + channel, 0)]


# Setup, poll and restore steps: one message list per step, for pacing.


def _query_steps(numbers):
    # Two queries per step: the size of a query-then-set step.
    return [
        [m for number in numbers[i : i + 2] for m in query(number)]
        for i in range(0, len(numbers), 2)
    ]


def _set_steps(settings):
    # Each query is answered before its set, so the first reply is the player's value.
    return [query(number) + nrpn(number, value) for number, value in settings]


def read_steps():
    return _query_steps(READ_NUMBERS)


def fixed_steps():
    return _set_steps(FIXED_SETTINGS)


def computed_settings(reads):
    # (settings, 0-based channel, note -> pad, refusal), from the read replies.
    channel, changes = control_channel(reads)
    note_to_pad, octave, refusal = control_map(reads)
    if right_split_channels(reads) is None:
        note_to_pad, refusal = None, REFUSE_RIGHT_SPLIT
    settings = [(NRPN_LEFT_MAIN_CHANNEL, channel + 1), (NRPN_OCTAVE, octave)] + changes
    return settings, channel, note_to_pad, refusal


def computed_steps(settings):
    return _set_steps(settings)


def poll_numbers(reads, channel, rescan):
    # Row Offset, the left split's Octave/Transpose and enough of the right split to see it
    # move onto the 0-based control channel. Every per-note channel only on a rescan,
    # to pick a free channel: all 16 each poll would slow the Row Offset re-check.
    numbers = [NRPN_ROW_OFFSET, NRPN_OCTAVE, NRPN_TRANSPOSE_PITCH, NRPN_TRANSPOSE_LIGHTS]
    if reads.get(NRPN_ROW_OFFSET) == 12:
        numbers.append(NRPN_CUSTOM_ROW_OFFSET)
    elif reads.get(NRPN_ROW_OFFSET) == 13:
        numbers += NRPN_GUITAR_TUNING
    numbers += [NRPN_RIGHT_MIDI_MODE, NRPN_RIGHT_MAIN_CHANNEL, NRPN_RIGHT_PER_ROW_LOWEST]
    numbers += NRPN_RIGHT_PER_NOTE if rescan else [NRPN_RIGHT_PER_NOTE[channel]]
    return numbers


def poll_missed(reads, polled, channel, rescan):
    # Whether the new reads need numbers the poll didn't query: a Row Offset change to
    # custom or Guitar, whose values would otherwise come from an older read.
    return not set(poll_numbers(reads, channel, rescan)) <= set(polled)


def poll_steps(numbers):
    return _query_steps(numbers)


def realign(reads, sent):
    # (note -> pad, refusal, sets to send, whether the player changed BleakLoop's values).
    note_to_pad, octave, refusal = control_map(reads)
    wanted = {
        NRPN_OCTAVE: octave,
        NRPN_TRANSPOSE_PITCH: TRANSPOSE_ZERO,
        NRPN_TRANSPOSE_LIGHTS: TRANSPOSE_ZERO,
    }
    settings = [(number, value) for number, value in wanted.items() if reads.get(number) != value]
    player_changed = any(reads.get(number) != value for number, value in sent.items())
    return note_to_pad, refusal, settings, player_changed


def split_restore(saved, numbers):
    # The player's values for what BleakLoop set, in setup order.
    return [nrpn(number, saved[number]) for number in numbers if number in saved]


class NrpnReader:
    """Decodes incoming NRPNs (query replies) from single CCs."""

    def __init__(self):
        self._seen = {}

    def feed(self, number, value):
        if number in (101, 100) and value == 127:
            self._seen = {}
        elif number in (99, 98, 6):
            self._seen[number] = value
        elif number == 38 and len(self._seen) == 3:
            seen = self._seen
            return (seen[99] << 7) | seen[98], (seen[6] << 7) | value
        return None


class SlideDecoder:
    """Turns X CCs, slide transfers (CC 119) and pad notes into core events."""

    def __init__(self):
        self.reset()

    def reset(self):
        self._lsb = {}  # (row, column) -> the latest X LSB
        self._armed = {}  # row -> the source column of a transfer, until its target's Note On
        self._swallow = set()  # (row, column): a transfer's source release, still to come

    def x_lsb(self, row, column, value):
        # The LSB comes first; the MSB completes the report.
        self._lsb[(row, column)] = value

    def x_msb(self, row, column, value):
        return XAxis(column, layout.pad_of(row), value << 7 | self._lsb.get((row, column), 0))

    def transfer(self, row, from_column):
        self._armed[row] = from_column

    def pad(self, row, column, value):
        # None for a swallowed message: a transfer's source Note Off, whose velocity is the
        # target column, so Live may hand it over with any value.
        if (row, column) in self._swallow:
            self._swallow.discard((row, column))
            return None
        source = self._armed.get(row)
        if source is not None and value > 0:
            del self._armed[row]
            self._swallow.add((row, source))
            return SlideMoved(layout.pad_of(row), source, column)
        return PadPress(column, layout.pad_of(row), value > 0, value)


class LedDriver:
    """Sends only the pads whose resolved colour changed."""

    def __init__(self):
        self._sent = {}

    def update(self, frame, clock):
        messages = []
        for key in sorted(frame):
            colour = resolve(frame[key], clock)
            if self._sent.get(key) != colour:
                self._sent[key] = colour
                messages += light(*key, colour)
        return messages

    def reset(self):
        self._sent = {}

    def release_column_1(self):
        return [m for pad in range(1, layout.ROWS + 1) for m in light(1, pad, DEVICE_DEFAULT)]
