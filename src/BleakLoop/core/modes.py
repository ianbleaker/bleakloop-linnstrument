"""Modes and the core's state."""

import enum
from dataclasses import dataclass, replace

from . import values
from .layout import Window


class Mode(enum.Enum):
    SESSION = enum.auto()
    LINNSTRUMENT = enum.auto()
    SEQUENCER = enum.auto()


class Origin(enum.Enum):
    # The Session Mode layer, or Sequencer Mode, Linnstrument Mode was entered from, which
    # Back returns to.
    SESSION = enum.auto()
    MIXER = enum.auto()
    FX = enum.auto()
    SEQUENCER = enum.auto()


@dataclass(frozen=True)
class ClipSource:
    track: int
    scene: int
    midi: bool


@dataclass(frozen=True)
class GroupSource:
    # A group track's slot: its members' clips in that row.
    track: int
    scene: int


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
class FaderTouch:
    # One finger on a horizontal fader row. The parameter is taken at the press, so an X
    # report needs no snapshot.
    pad: int
    column: int  # the cell the finger is on, which a slide moves
    first: int  # the fader's first and last column
    last: int
    name: str
    min: float
    max: float
    is_quantized: bool
    macro: tuple | None  # as FaderView.macro
    norm: float | None = None  # the last position written, None before the first


@dataclass(frozen=True)
class FaderBinding:
    # A Mapped FX row's parameter, found again by names: the LOM has no stable IDs.
    track: str
    tn: int  # the count of earlier tracks with this name, tracks then returns then master
    device: str | None  # a top-level device's name; None for the track's mixer
    dn: int  # the count of earlier devices with this name on the track
    param: int  # index into device.parameters, or into [volume, panning, *sends]
    name: str  # the parameter's name: a renamed or moved parameter isn't found


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
    slot: int | None  # None once a morphing scene snapshot's scene is deleted
    start_beats: float
    end_beats: float
    last_beats: float  # song time at the last tick
    macros: tuple = ()  # MorphMacro per macro still morphing
    scene: bool = False  # slot is a scene index, not a global slot


@dataclass(frozen=True)
class StepHold:
    # One finger on a Sequencer Mode step.
    step: int  # the global step, from clip time 0
    column: int  # the cell the finger is on, which a slide moves
    pad: int
    velocity: int  # the strike velocity
    used: bool = False  # by a span, a note pad, a slide or a paste: no toggle on release
    shift: bool = False  # Shift was held at the press: a slide nudges
    x0: int | None = None  # the first X report
    notes: tuple = ()  # the step's NoteViews at the press, which a slide moves
    sliding: bool = False
    target: tuple | None = None  # (track, scene) at the press: an X report has no snapshot
    length: float = 0.0  # the step length at the press, in beats
    moved: int = 0  # the slide's last written velocity change, or nudge in columns


@dataclass(frozen=True)
class State:
    mode: Mode = Mode.SESSION
    window: Window = Window()
    shift: bool = False
    mixer: bool = False
    quantization_memory: int | None = None
    copy: bool = False
    delete: bool = False
    copy_source: ClipSource | GroupSource | SceneSource | None = None
    stop: bool = False  # Stop is held
    fixed_length: int | None = None  # bars; Linnstrument Mode's Record Clip uses it too
    touches: tuple = ()  # Touch per held fader column
    lifts: tuple = ()  # Lift per fader column whose pad was just released
    dead: tuple = ()  # Lift per column whose slide started on rows 7-8: the fader ignores it
    glides: tuple = ()  # Glide per track
    glide_ms: float | None = None  # time of the last glide step, None when none is moving
    undo_open: bool = False  # a fader gesture's undo step is open in Live
    scene_page: bool = False  # Linnstrument Mode column 1 shows the scene page
    came_from: Origin = Origin.SESSION  # where Linnstrument Mode's Back returns to
    fx: bool = False
    fx_length: int | None = None  # bars of the held FX length pad
    fx_slots: tuple = (None,) * 16  # tuple of FxRack per stored slot, None when empty
    morph: Morph | None = None  # runs in every mode
    fx_undo_open: bool = False  # a recall's undo step is open in Live
    fx_landed: int | None = None  # the slot of the last recall that landed
    fx_scenes: tuple = ()  # per scene index: tuple of FxRack, or None when empty
    fx_landed_scene: int | None = None  # the scene of the last recall that landed
    fader_touches: tuple = ()  # FaderTouch per touched fader row
    fader_undo_open: bool = False  # a fader gesture's undo step is open in Live
    fader_source: str = "device"  # "device" or "mapped"
    device_clip: bool = False  # Device/Clip is held
    split: bool = False  # Session Mode's split view
    fader_bindings: tuple = (None,) * 8  # Mapped FX: FaderBinding or None per row
    seq_held: bool = False  # Seq is held in Session Mode
    seq_used: bool = False  # the Seq hold entered on a slot: its release does nothing
    # Sequencer Mode's arm: per song.tracks, the arm before entry and what BleakLoop set.
    seq_saved_arms: tuple | None = None
    seq_set_arms: tuple | None = None
    seq_track: int | None = None  # the song.tracks index BleakLoop last armed
    seq_refused: int | None = None  # the non-MIDI track the selection last moved to
    seq_rate: float = values.SEQ_DEFAULT_RATE  # beats per step, before Triplet
    seq_triplet: bool = False
    seq_follow: bool = True
    seq_page: int = 0  # the page in view while Follow is off
    seq_page_held: int | None = None
    seq_settings: bool = False  # columns 11-14 show the settings, not the note pads
    seq_base: int = values.SEQ_BASE_NOTE  # the melodic note pads' bottom-left note
    seq_pitch: int = values.SEQ_BASE_NOTE  # the selected note on a melodic track
    seq_holds: tuple = ()  # StepHold per held step
    # (step, notes) of the copied step, each note (pitch, offset in the step, duration, velocity)
    seq_copy_source: tuple | None = None
    seq_undo_open: bool = False  # a slide's undo step is open in Live


def enter(state, mode):
    # The only place mode-entry resets happen, including the fader state.
    # The window, the launch quantization memory and Fixed Length survive both directions.
    # Entering Linnstrument Mode clears Shift: a Shift held then was pressed in User Firmware
    # Mode, and the firmware sends its release as a User Firmware note, not on the control
    # channel, so BleakLoop never sees it.
    # A caller leaving Mixer Mode closes an open undo step first (mixer.reset), and one
    # leaving the faders closes theirs (faders.reset). The split view, the fader source and
    # the bindings survive.
    # FX Mode turns off, but a running morph, its undo step and the snapshots carry on.
    # Sequencer Mode's holds reset; its arm, rate, Triplet, note range and pitch survive. A
    # caller leaving it closes a slide's undo step first.
    if mode is Mode.LINNSTRUMENT and state.mode is Mode.SESSION:
        origin = Origin.MIXER if state.mixer else Origin.FX if state.fx else Origin.SESSION
        state = replace(state, came_from=origin)
    elif mode is Mode.LINNSTRUMENT and state.mode is Mode.SEQUENCER:
        state = replace(state, came_from=Origin.SEQUENCER)
    state = replace(
        state,
        mode=mode,
        mixer=False,
        copy=False,
        delete=False,
        copy_source=None,
        stop=False,
        touches=(),
        lifts=(),
        dead=(),
        glides=(),
        glide_ms=None,
        undo_open=False,
        scene_page=False,
        fx=False,
        fx_length=None,
        device_clip=False,
        fader_touches=(),
        seq_held=False,
        seq_used=False,
        seq_holds=(),
        seq_copy_source=None,
        seq_page_held=None,
    )
    if mode is Mode.SEQUENCER:
        # Page 1: a page pinned on another clip can lie past this one's end.
        state = replace(state, seq_follow=True, seq_page=0, seq_settings=False)
    if mode is Mode.LINNSTRUMENT:
        state = replace(state, shift=False)
    return state
