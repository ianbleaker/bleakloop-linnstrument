"""Plain types passed between the plumbing, the adapters and the core."""

from dataclasses import dataclass

from .leds import Light


@dataclass(frozen=True)
class SlotView:
    has_clip: bool = False
    is_playing: bool = False
    is_triggered: bool = False
    is_recording: bool = False


@dataclass(frozen=True)
class TrackView:
    index: int  # position in the track list
    name: str = ""
    colour: int = 0
    arm: bool = False
    implicit_arm: bool = False
    can_be_armed: bool = True
    mute: bool = False
    solo: bool = False
    slots: tuple = ()  # one SlotView per window row that exists, top first


@dataclass(frozen=True)
class Snapshot:
    is_playing: bool
    song_beats: float
    tempo: float
    metronome: bool
    session_view: bool
    track_count: int = 0
    scene_count: int = 0
    tracks: tuple = ()  # one TrackView per window column that has a track, left first
    can_undo: bool = False
    can_redo: bool = False
    launch_quantization: int = 4


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


# track and scene are indexes into the track list and Live's scene list.


@dataclass(frozen=True)
class FireSlot:
    track: int
    scene: int
    legato: bool


@dataclass(frozen=True)
class FireScene:
    scene: int
    legato: bool


@dataclass(frozen=True)
class ToggleMute:
    track: int


@dataclass(frozen=True)
class ToggleSolo:
    track: int


@dataclass(frozen=True)
class SelectTrack:
    track: int


@dataclass(frozen=True)
class ArmExclusive:
    track: int
    arm: bool


@dataclass(frozen=True)
class StopTrackClips:
    track: int


@dataclass(frozen=True)
class StopAllClips:
    pass


@dataclass(frozen=True)
class Undo:
    pass


@dataclass(frozen=True)
class Redo:
    pass


@dataclass(frozen=True)
class SetTempo:
    bpm: float


@dataclass(frozen=True)
class SetLaunchQuantization:
    value: int


@dataclass(frozen=True)
class ShowMessage:
    text: str


# The colour of every pad the current mode owns, keyed by (column, pad).
Frame = dict[tuple[int, int], Light]
