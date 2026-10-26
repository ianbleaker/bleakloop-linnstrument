"""Modes and the core's state."""

import enum
from dataclasses import dataclass, replace

from .layout import Window


class Mode(enum.Enum):
    SESSION = enum.auto()
    LINNSTRUMENT = enum.auto()


@dataclass(frozen=True)
class ClipSource:
    track: int
    scene: int
    midi: bool


@dataclass(frozen=True)
class SceneSource:
    scene: int


@dataclass(frozen=True)
class Touch:
    # One finger on a Mixer fader column.
    column: int
    track: int  # the track at the gesture's first press: a window move doesn't change it
    pad: int
    anchor: float  # the volume Y moves from
    pressed_ms: float | None = None  # set by the first glide tick after the press
    previous_ms: float | None = None  # when the slide's previous pad was pressed


@dataclass(frozen=True)
class Lift:
    # A fader pad just released, which a press on the next pad can continue.
    column: int
    track: int
    pad: int
    pressed_ms: float | None = None
    expires_ms: float | None = None  # set by the first glide tick after the release


@dataclass(frozen=True)
class Glide:
    # A track volume moving toward its fader target.
    track: int
    current: float
    target: float
    pace: float | None = None  # volume per ms during a slide; None for the normal glide


@dataclass(frozen=True)
class FxRack:
    # One rack's macros in a stored snapshot, keyed as fx.keys gives them.
    track: str
    rack: str
    n: int
    values: tuple


@dataclass(frozen=True)
class MorphMacro:
    path: tuple
    rack_name: str
    index: int  # macro index, 0 for Macro 1
    start: float
    target: float
    quantized: bool
    written: float  # BleakLoop's last write, or the start value
    span: float  # max - min


@dataclass(frozen=True)
class Morph:
    slot: int
    start_beats: float
    end_beats: float
    last_beats: float  # song time at the last tick
    macros: tuple = ()  # MorphMacro per macro still morphing


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
    fixed_length: int | None = None  # bars; Linnstrument Mode's Record Clip uses it too
    touches: tuple = ()  # Touch per held fader column
    lifts: tuple = ()  # Lift per fader column whose pad was just released
    glides: tuple = ()  # Glide per track
    glide_ms: float | None = None  # time of the last glide step, None when none is moving
    undo_open: bool = False  # a fader gesture's undo step is open in Live
    scene_page: bool = False  # Linnstrument Mode column 1 shows the scene page
    fx: bool = False
    fx_length: int | None = None  # bars of the held FX length pad
    fx_slots: tuple = (None,) * 16  # tuple of FxRack per stored slot, None when empty
    morph: Morph | None = None  # runs in every mode
    fx_undo_open: bool = False  # a recall's undo step is open in Live
    fx_landed: int | None = None  # the slot of the last recall that landed


def enter(state, mode):
    # The only place mode-entry resets happen, including the fader state.
    # The window, the launch quantization memory and Fixed Length survive both directions.
    # Entering Linnstrument Mode clears Shift: a Shift held then was pressed in User Firmware
    # Mode, and the firmware sends its release as a User Firmware note, not on the control
    # channel, so BleakLoop never sees it.
    # A caller leaving Mixer Mode closes an open undo step first (mixer.reset).
    # FX Mode turns off, but a running morph, its undo step and the snapshots carry on.
    state = replace(
        state,
        mode=mode,
        mixer=False,
        copy=False,
        delete=False,
        copy_source=None,
        touches=(),
        lifts=(),
        glides=(),
        glide_ms=None,
        undo_open=False,
        scene_page=False,
        fx=False,
        fx_length=None,
    )
    if mode is Mode.SESSION:
        state = replace(state, track_control=TrackControl.ARM)
    else:
        state = replace(state, shift=False)
    return state
