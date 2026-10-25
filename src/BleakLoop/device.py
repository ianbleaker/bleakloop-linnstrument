"""LinnStrument message building and the LED driver (architecture section 5). Pure Python."""

from .core import layout
from .core.leds import DEVICE_DEFAULT, resolve
from .core.values import CONTROL_CC_BASE, CONTROL_CHANNEL, SPLIT_POINT

CC_STATUS = 0xB0

# Device protocol numbers.
NRPN_USER_FIRMWARE_MODE = 245
NRPN_QUERY = 299
CC_Y_AXIS = 11
CC_LIGHT_COLUMN = 20
CC_LIGHT_ROW = 21
CC_LIGHT_COLOUR = 22

# The control split, in setup order.
SPLIT_SETTINGS = [
    (200, 1),  # split on
    (202, SPLIT_POINT),  # left split is column 1
    (0, 0),  # left split MIDI mode: one channel
    (1, CONTROL_CHANNEL + 1),  # left split main channel
    (35, 2),  # left split special mode: CC Faders
] + [(40 + i, CONTROL_CC_BASE + i) for i in range(8)]  # faders 1-8 send CC 102-109


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


def user_firmware_mode(on):
    return nrpn(NRPN_USER_FIRMWARE_MODE, 1 if on else 0)


def y_axis(on):
    return [m for channel in range(layout.ROWS) for m in cc(channel, CC_Y_AXIS, int(on))]


def split_setup():
    # One message list per NRPN, for pacing. Each query is answered before its set.
    return [query(number) + nrpn(number, value) for number, value in SPLIT_SETTINGS]


def split_restore(saved):
    # One message list per NRPN, for pacing.
    return [nrpn(number, saved[number]) for number, _ in SPLIT_SETTINGS if number in saved]


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
