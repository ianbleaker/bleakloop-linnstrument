"""Modes and the core's state (S-7–S-16)."""

import enum
from dataclasses import dataclass, replace

from .layout import Window


class Mode(enum.Enum):
    SESSION = enum.auto()
    NOTE = enum.auto()


@dataclass(frozen=True)
class ClipSource:
    track: int
    scene: int
    midi: bool


@dataclass(frozen=True)
class SceneSource:
    scene: int


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
    copy: bool = False
    delete: bool = False
    copy_source: ClipSource | SceneSource | None = None
    fixed_length: int | None = None  # bars; Note Mode's Record Clip uses it too (S-78)


def enter(state, mode):
    # The only place mode-entry resets happen (S-9, S-13). The window, the launch
    # quantization memory and Fixed Length survive both directions.
    state = replace(
        state, mode=mode, mixer=False, shift=False, copy=False, delete=False, copy_source=None
    )
    if mode is Mode.SESSION:
        state = replace(state, track_control=TrackControl.ARM)
    return state
