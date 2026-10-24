"""Device colours and blinking (S-87, S-88, S-90, S-91)."""

import enum
from dataclasses import dataclass

from .values import FAST_BLINK_MS

# CC 22 colour values (S-87, S-88).
DEVICE_DEFAULT = 0
RED = 1
YELLOW = 2
GREEN = 3
CYAN = 4
BLUE = 5
MAGENTA = 6
OFF = 7
WHITE = 8
ORANGE = 9
LIME = 10
PINK = 11


class Blink(enum.Enum):
    STEADY = enum.auto()
    TEMPO = enum.auto()
    FAST = enum.auto()


@dataclass(frozen=True)
class Light:
    colour: int
    blink: Blink = Blink.STEADY


@dataclass(frozen=True)
class Clock:
    beats: float
    now_ms: float


def tempo_on(beats):
    return beats % 1 < 0.5


def fast_on(now_ms):
    return (now_ms // FAST_BLINK_MS) % 2 == 0


def resolve(light, clock):
    if light.blink is Blink.TEMPO and not tempo_on(clock.beats):
        return OFF
    if light.blink is Blink.FAST and not fast_on(clock.now_ms):
        return OFF
    return light.colour


def phase_key(clock):
    return (tempo_on(clock.beats), fast_on(clock.now_ms))
