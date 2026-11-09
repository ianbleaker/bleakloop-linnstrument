"""Modes and the core's state."""

import enum
from dataclasses import dataclass, replace

from . import values
from .layout import FX_SNAPSHOTS, Window


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
    # A bound snapshot slot's parameter, found again by names: the LOM has no stable IDs.
    track: str
    tn: int  # the count of earlier tracks with this name, tracks then returns then master
    device: str | None  # a top-level device's name; None for the track's mixer
    dn: int  # the count of earlier devices with this name on the track
    param: int  # index into device.parameters, or into [volume, panning, *sends]
    name: str  # the parameter's name: a renamed or moved parameter isn't found


@dataclass(frozen=True)
class BoundSlot:
    # A snapshot slot bound to parameters: a slide moves them from wherever they are. params
    # holds a FaderBinding locator per parameter; a rack macro's is matched by its index alone.
    # values holds each parameter's stored punch-in value, a float or None; () means all None.
    params: tuple
    values: tuple = ()


@dataclass(frozen=True)
class BoundRead:
    # A bound slot's parameter as the press found it. key is its rack macro identity when it is
    # one, as Set-wide slides and faders use, else its locator.
    key: object
    name: str
    start: float
    low: float
    high: float
    quantized: bool
    text: str = ""  # Live's display of the value at the press, such as "1.20 kHz"
    owner: str = ""  # its device's name, or its track's for a mixer parameter
    target: float | None = None  # its punch-in value, clamped to its range; None when none
    target_text: str = ""  # Live's display of the punch-in value

    @property
    def span(self):
        return self.high - self.low


@dataclass(frozen=True)
class FxRack:
    # One rack's macros in a stored snapshot, keyed as fx.keys gives them.
    track: str
    rack: str
    n: int
    values: tuple


@dataclass(frozen=True)
class MorphMacro:
    # key: a rack macro as (path, rack name, macro index from 0), or a parameter locator
    # (a FaderBinding), as live_state.target_parameters resolves either.
    key: object
    start: float
    target: float
    quantized: bool
    written: float  # BleakLoop's last write, or the start value
    span: float  # max - min


@dataclass(frozen=True)
class SlotHold:
    # A finger on a stored snapshot slot: a tap recalls on the lift, a slide right blends.
    pad: int  # the row's pad, 1-8
    column: int  # the column the finger is on now
    slot: int  # the global slot
    x0: int | None = None  # the first X report, the slide's zero
    slid: bool = False  # moved a quarter column: the lift won't recall
    f: float = 0.0  # the blend, 0 to 1
    read: tuple | None = None  # MorphMacro per parameter, as the press found it; None until read
    note: str = ""  # the read's "N racks not found" note
    lifted: bool = False  # released before the read landed
    order: int = 0  # when the slide started: the latest owns the parameters it shares
    wrote: bool = False  # the slide has written: a running morph is cancelled
    dropped: frozenset = frozenset()  # keys taken out of this slide
    bound: bool = False  # a bound slot: BoundRead per parameter, and a slide both ways
    punch: bool = False  # Device/Clip + the slot: it lands at once, and returns on the lift


@dataclass(frozen=True)
class PunchReturn:
    # A punch's lift, ramping its parameters back: MorphMacro per parameter, start its value at
    # the lift and target its value at the press.
    macros: tuple
    started_at: float | None = None  # the first tick's time, None until it stamps


@dataclass(frozen=True)
class BindHold:
    # Shift + a snapshot slot, held: its lift binds Live's selected parameter, unless a Device
    # FX row was tapped during the hold, which bound that row's instead.
    pad: int
    column: int
    slot: int  # the global slot
    used: bool = False


@dataclass(frozen=True)
class SlideParam:
    # A parameter a held slide has taken: one origin for every slide holding it.
    key: object
    origin: float
    written: float
    span: float


@dataclass(frozen=True)
class Morph:
    slot: int | None  # None once a morphing scene snapshot's scene is deleted
    start_beats: float
    end_beats: float
    last_beats: float  # song time at the last tick
    macros: tuple = ()  # MorphMacro per macro still morphing
    scene: bool = False  # slot is a scene index, not a global slot
    launch: bool = False  # a scene launch's snapshot, landing as the scene starts
    # After a wrap of the loop, end_beats may no longer fall on Live's launch grid: a launch
    # morph then lands as Live starts the scene, seen waiting to launch (triggered) and then not.
    wrapped: bool = False
    triggered: bool = False


@dataclass(frozen=True)
class PendingLaunch:
    # A scene launch held back until its bar line: decided at the press, fired by the timer.
    scene: int
    fire_beats: float  # song time to fire it at, so Live's launch quantization starts it on time
    last_beats: float  # song time at the press, then at the last tick


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
    scene_page: bool = False  # Linnstrument Mode's Global column shows the scene page
    came_from: Origin = Origin.SESSION  # where Linnstrument Mode's Back returns to
    fx: bool = False
    fx_length: int | None = None  # bars of the held FX length pad
    # Per global slot (bank * FX_SLOTS + slot): a Set-wide tuple of FxRack, a BoundSlot, or
    # None when empty.
    fx_slots: tuple = (None,) * FX_SNAPSHOTS
    fx_bank: int = 0  # the snapshot bank the slot pads show, 0-based; never saved
    morph: Morph | None = None  # runs in every mode
    fx_holds: tuple = ()  # SlotHold per row holding a stored slot
    fx_slide_params: tuple = ()  # SlideParam per parameter a held slide has written
    fx_slide_undo_open: bool = False  # held slides' shared undo step is open in Live
    fx_slide_count: int = 0  # counts slides as they start, for SlotHold.order
    fx_returns: tuple = ()  # PunchReturn per lifted punch still ramping back
    fx_bind_hold: BindHold | None = None  # Shift + a slot, held
    # The Undo pad's bind history: (slot, locator, punch-in value, fx.ADDED/REMOVED/UPDATED)
    # per bind, removal or update, newest last;
    # the time of the last one, None until the next 10 ms tick stamps it; the last tick's time.
    bind_undo: tuple = ()
    bind_undo_at: float | None = None
    bind_undo_now: float | None = None
    fx_undo_open: bool = False  # a recall's undo step is open in Live
    fx_landed: int | None = None  # the global slot of the last recall that landed
    fx_scenes: tuple = ()  # per scene index: tuple of FxRack, or None when empty
    fx_landed_scene: int | None = None  # the scene of the last recall that landed
    fx_copy_source: tuple | None = None  # (slot, scene) of the snapshot Copy picked
    fader_touches: tuple = ()  # FaderTouch per touched fader row
    fader_undo_open: bool = False  # a fader gesture's undo step is open in Live
    device_clip: bool = False  # Device/Clip is held
    device_clip_used: bool = False  # a press during the hold: its release doesn't flip the view
    split: bool = False  # Session Mode's split view
    mixer_split: bool = False  # Mixer Mode's split view
    split_snapshots: bool = False  # the split views show the snapshots, not the faders
    pending_launch: PendingLaunch | None = None  # fires in every mode, as a morph runs
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
    # leaving the faders closes theirs (faders.reset). The split views, their panel, the fader
    # source and the bindings survive.
    # FX Mode turns off, but a running morph, its undo step, a pending scene launch and the
    # snapshots carry on.
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
        fx_copy_source=None,
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
        device_clip_used=False,
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
