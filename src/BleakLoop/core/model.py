"""Plain types passed between the plumbing, the adapters and the core."""

import enum
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
    has_midi_input: bool = False
    is_foldable: bool = False  # a group track: its slots can't hold clips
    volume: float = 0.0  # Live's volume control position
    slots: tuple = ()  # one SlotView per window row that exists, top first


@dataclass(frozen=True)
class ClipView:
    is_midi: bool


class ClipTarget(enum.Enum):
    # The quantize candidates, in S-48 order.
    HIGHLIGHTED = enum.auto()
    DETAIL = enum.auto()
    PLAYING = enum.auto()


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
    signature_numerator: int = 4
    signature_denominator: int = 4
    session_record: bool = False
    arrangement_overdub: bool = False
    arrangement_record: bool = False
    back_to_arranger: bool = False
    highlighted_clip: ClipView | None = None
    detail_clip: ClipView | None = None
    playing_clip: ClipView | None = None
    # One bool per window row that exists, true if any track in the Set has a clip there.
    # Read only while Copy is held.
    scene_clips: tuple = ()


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


@dataclass(frozen=True)
class YAxis:
    # Y position within a pressed pad, 0 at the near edge to 127 at the far edge (S-4).
    column: int
    pad: int
    value: int


@dataclass(frozen=True)
class SceneSelected:
    # Fed back by the adapter after Capture (S-47).
    scene: int


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
    record_length: float | None = None  # beats


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
class ShowClip:
    track: int
    scene: int


@dataclass(frozen=True)
class CopyClip:
    source_track: int
    source_scene: int
    track: int
    scene: int


@dataclass(frozen=True)
class CopyScene:
    source: int
    target: int


@dataclass(frozen=True)
class DeleteClip:
    track: int
    scene: int


@dataclass(frozen=True)
class DeleteScene:
    scene: int


@dataclass(frozen=True)
class CaptureAndInsertScene:
    pass


@dataclass(frozen=True)
class QuantizeClip:
    target: ClipTarget


@dataclass(frozen=True)
class SetSessionRecord:
    on: bool


@dataclass(frozen=True)
class SetArrangementRecord:
    on: bool


@dataclass(frozen=True)
class ClearBackToArrangement:
    pass


@dataclass(frozen=True)
class SetVolume:
    track: int
    value: float


@dataclass(frozen=True)
class SetMixer:
    on: bool


@dataclass(frozen=True)
class BeginUndoStep:
    pass


@dataclass(frozen=True)
class EndUndoStep:
    pass


@dataclass(frozen=True)
class ShowMessage:
    text: str


# The colour of every pad the current mode owns, keyed by (column, pad).
Frame = dict[tuple[int, int], Light]
