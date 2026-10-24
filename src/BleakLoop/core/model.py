"""Plain types passed between the plumbing, the adapters and the core."""

from dataclasses import dataclass

from .leds import Light


@dataclass(frozen=True)
class Snapshot:
    is_playing: bool
    song_beats: float
    tempo: float
    metronome: bool
    session_view: bool


# Events


@dataclass(frozen=True)
class PadPress:
    column: int
    pad: int
    pressed: bool


@dataclass(frozen=True)
class ControlCC:
    cc: int
    value: int


# Actions


@dataclass(frozen=True)
class EnterMode:
    mode: object


@dataclass(frozen=True)
class ToggleMetronome:
    pass


@dataclass(frozen=True)
class TogglePlay:
    pass


# The colour of every pad the current mode owns, keyed by (column, pad).
Frame = dict[tuple[int, int], Light]
