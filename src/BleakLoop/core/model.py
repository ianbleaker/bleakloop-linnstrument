"""Plain types passed between the plumbing, the adapters and the core.

Track and scene indexes are positions in the track list and Live's scene list.
"""

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
    index: int
    name: str = ""
    colour: int = 0
    arm: bool = False
    implicit_arm: bool = False
    can_be_armed: bool = True
    mute: bool = False
    solo: bool = False
    has_midi_input: bool = False
    is_foldable: bool = False  # a group track: its slots can't hold clips
    selected: bool = False  # Live's selected track
    volume: float = 0.0  # Live's volume control position
    slots: tuple = ()  # one SlotView per window row that exists, top first


@dataclass(frozen=True)
class ClipView:
    is_midi: bool


@dataclass(frozen=True)
class SelectedTrack:
    # Live's selected track, which may be outside the window.
    index: int
    name: str = ""
    armed: bool = False  # can_be_armed and (arm or implicit_arm)
    is_foldable: bool = False
    clips: tuple = ()  # one bool per scene in the Set, true if that slot has a clip


class ClipTarget(enum.Enum):
    # The quantize candidates, in the order Quantize tries them.
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
    # Read only in Linnstrument Mode. None when the selected track isn't in the track list.
    selected_track: SelectedTrack | None = None
    selected_scene: int = 0  # Live's highlighted scene
    can_capture_midi: bool = False
    # Over every track and return track in the Set, not just the window.
    any_muted: bool = False
    any_soloed: bool = False


@dataclass(frozen=True)
class MacroView:
    value: float
    min: float
    max: float
    is_quantized: bool = False  # on/off or chooser: switches, never glides


@dataclass(frozen=True)
class RackView:
    # A top-level rack. path is (kind, track index, device index), kind "track", "return" or
    # "master"; the track index is 0 for master.
    path: tuple
    track_name: str
    rack_name: str
    macros: tuple = ()  # MacroView per visible macro


# Events


@dataclass(frozen=True)
class PadPress:
    column: int
    pad: int
    pressed: bool


@dataclass(frozen=True)
class YAxis:
    # Y position within a pressed pad, 0 at the near edge to 127 at the far edge.
    column: int
    pad: int
    value: int


@dataclass(frozen=True)
class SceneSelected:
    # Fed back by the adapter after Capture.
    scene: int


@dataclass(frozen=True)
class RacksRead:
    # Fed back by the adapter after StoreFxSnapshot or RecallFxSnapshot.
    slot: int  # 0-15
    racks: tuple  # RackView per rack, in Set order
    recall: bool
    bars: int | None = None  # the morph length; None for a jump


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
class SetArm:
    # Only this track's arm: the others are left as they are.
    track: int
    arm: bool


@dataclass(frozen=True)
class UnmuteAll:
    # Every track and return track in the Set.
    pass


@dataclass(frozen=True)
class UnsoloAll:
    # Every track and return track in the Set.
    pass


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
class CaptureMidi:
    pass


@dataclass(frozen=True)
class AddScene:
    # Adds a scene at the end of the Set.
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
class StoreFxSnapshot:
    slot: int


@dataclass(frozen=True)
class RecallFxSnapshot:
    slot: int
    bars: int | None  # None for a jump


@dataclass(frozen=True)
class SetMacros:
    writes: tuple  # (path, rack name, macro index, value) per macro


@dataclass(frozen=True)
class SaveFxSnapshots:
    text: str


@dataclass(frozen=True)
class ShowMessage:
    text: str


# The colour of every pad the current mode owns, keyed by (column, pad).
Frame = dict[tuple[int, int], Light]
