"""Modes and the core's state (S-7–S-16)."""

import enum
from dataclasses import dataclass, replace

from .layout import Window


class Mode(enum.Enum):
    SESSION = enum.auto()
    NOTE = enum.auto()


class TrackControl(enum.Enum):
    MUTE = enum.auto()
    SOLO = enum.auto()
    ARM = enum.auto()


@dataclass(frozen=True)
class State:
    mode: Mode = Mode.SESSION
    window: Window = Window()
    shift: bool = False
    track_control: TrackControl = TrackControl.ARM
    mixer: bool = False
    quantization_memory: int | None = None


def enter(state, mode):
    # The only place mode-entry resets happen (S-9, S-13). The window and the
    # launch quantization memory survive both directions.
    state = replace(state, mode=mode, mixer=False, shift=False)
    if mode is Mode.SESSION:
        state = replace(state, track_control=TrackControl.ARM)
    return state
