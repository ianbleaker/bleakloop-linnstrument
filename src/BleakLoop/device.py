"""LinnStrument message building and the LED driver (spec section 3). Pure Python."""

from .core import layout
from .core.leds import DEVICE_DEFAULT, resolve
from .core.values import CONTROL_CC_BASE, CONTROL_CHANNEL, SPLIT_POINT

CC_STATUS = 0xB0

# Device protocol numbers (spec section 3, architecture section 9).
NRPN_USER_FIRMWARE_MODE = 245
CC_Y_AXIS = 11
CC_LIGHT_COLUMN = 20
CC_LIGHT_ROW = 21
CC_LIGHT_COLOUR = 22


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
    # One message list per NRPN, for pacing (architecture section 9).
    settings = [
        (200, 1),  # split on
        (202, SPLIT_POINT),  # left split is column 1
        (0, 0),  # left split MIDI mode: one channel
        (1, CONTROL_CHANNEL + 1),  # left split main channel
        (35, 2),  # left split special mode: CC Faders
    ] + [(40 + i, CONTROL_CC_BASE + i) for i in range(8)]  # faders 1-8 send CC 102-109
    return [nrpn(number, value) for number, value in settings]


class LedDriver:
    """Sends only the pads whose resolved colour changed (S-93)."""

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
        # S-94: forget what was sent so the next update repaints everything.
        self._sent = {}

    def release_column_1(self):
        # S-6: hand column 1's lights back to the device.
        return [m for pad in range(1, layout.ROWS + 1) for m in light(1, pad, DEVICE_DEFAULT)]
