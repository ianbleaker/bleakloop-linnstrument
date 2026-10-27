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
    controls_other_clips: bool = False  # a group slot whose members have clips here
    # A group slot: one bool per leaf member, in song.tracks order, true if that member has a
    # clip here. Read only while Copy is held.
    member_clips: tuple = ()


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
    set_index: int | None = None  # index in song.tracks


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


@dataclass(frozen=True)
class NoteView:
    note_id: int
    pitch: int
    start: float  # beats from clip time 0
    duration: float
    velocity: float


@dataclass(frozen=True)
class ScaleView:
    # Live 12's Scale Mode: the root and the intervals from it, both in semitones.
    on: bool = False
    root: int = 0
    intervals: tuple = ()


@dataclass(frozen=True)
class DrumView:
    scroll: int  # Live's drum_pads_scroll_position: the rack row at the bottom of its view
    selected: int | None  # the selected drum pad's note
    filled: frozenset  # the notes of the pads with chains


@dataclass(frozen=True)
class SequencerView:
    # Sequencer Mode's target: Live's highlighted slot. Track indexes are song.tracks indexes.
    track: int | None = None
    name: str = ""
    scene: int = 0
    is_midi: bool = False  # a MIDI track: has MIDI input and isn't a group
    has_clip: bool = False
    is_playing: bool = False
    loop_start: float = 0.0
    loop_end: float = 0.0
    position: float = 0.0  # the clip's playing position
    notes: tuple = ()  # NoteView per note in the clip
    drum: DrumView | None = None
    scale: ScaleView = ScaleView()


@dataclass(frozen=True)
class SeqEntry:
    # Read only while Seq is held: where a Seq tap enters. Track indexes are song.tracks indexes.
    selected: int | None = None
    selected_midi: bool = False
    scene: int = 0  # Live's highlighted scene
    has_clip: bool = False  # the highlighted slot has a clip
    detail: tuple | None = None  # (track, scene) of the Detail-view clip, a Session MIDI clip
    playing_scene: int | None = None  # the selected track's playing slot


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
    # One bool per window row that exists, true while that scene waits to launch.
    scene_triggered: tuple = ()
    # Read only in Linnstrument Mode. None when the selected track isn't in the track list.
    selected_track: SelectedTrack | None = None
    selected_scene: int = 0  # Live's highlighted scene
    can_capture_midi: bool = False
    # Over every track and return track in the Set, not just the window.
    any_muted: bool = False
    any_soloed: bool = False
    any_armed: bool = False
    # FaderView or None per fader row, pad 1 first; read only while the faders show.
    faders: tuple = ()
    # Per song.tracks: True, False, or None when it can't be armed. Read only for Sequencer
    # Mode.
    arms: tuple = ()
    sequencer: SequencerView | None = None  # read only in Sequencer Mode
    seq_entry: SeqEntry | None = None  # read only while Seq is held


@dataclass(frozen=True)
class MacroView:
    value: float
    min: float
    max: float
    is_quantized: bool = False  # on/off or chooser: switches, never glides


@dataclass(frozen=True)
class FaderView:
    # The parameter one horizontal fader row controls.
    name: str
    value: float
    min: float
    max: float
    is_quantized: bool = False
    macro: tuple | None = None  # (path, rack name, index) for a top-level rack's macro


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
    velocity: int = 127  # the strike velocity of a press


@dataclass(frozen=True)
class YAxis:
    # Y position within a pressed pad, 0 at the near edge to 127 at the far edge.
    column: int
    pad: int
    value: int


@dataclass(frozen=True)
class XAxis:
    # X position across the whole surface, 0-2730 (architecture section 5).
    column: int
    pad: int
    value: int


@dataclass(frozen=True)
class SlideMoved:
    # A finger held on a pad crossed into the next column of the same row.
    pad: int
    from_column: int
    to_column: int


@dataclass(frozen=True)
class FaderBound:
    # Fed back by the adapter after BindFader.
    row: int  # 0-7, pad 1 first
    binding: object  # FaderBinding, or None when the parameter can't be bound
    message: str


@dataclass(frozen=True)
class SceneSelected:
    # Fed back by the adapter after Capture.
    scene: int


@dataclass(frozen=True)
class ScenesChanged:
    # From the display tick, when the Set's scene list changed (fx.scene_origins).
    origin: tuple  # per new scene: its old index, or None for a new scene
    copies: tuple  # per new scene: the old index a duplicate copies its snapshot from, or None


@dataclass(frozen=True)
class RacksRead:
    # Fed back by the adapter after StoreFxSnapshot or RecallFxSnapshot.
    slot: int  # 0-15, or the scene index of a scene snapshot
    racks: tuple  # RackView per rack, in Set order
    recall: bool
    bars: int | None = None  # the morph length; None for a jump
    scene: bool = False
    end_beats: float | None = None  # a scene launch's landing time, decided at the press


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
class UnarmAll:
    # Every armable track in the Set; returns and master can't be armed.
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
class CopyGroupClips:
    # Each leaf member of the group track copies its own clip from source_scene to scene.
    track: int
    source_scene: int
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
class DeleteGroupClips:
    # Each leaf member of the group track deletes its own clip in scene.
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
    slot: int  # 0-15, or the scene index of a scene snapshot
    scene: bool = False


@dataclass(frozen=True)
class RecallFxSnapshot:
    slot: int  # 0-15, or the scene index of a scene snapshot
    bars: int | None  # None for a jump
    scene: bool = False
    end_beats: float | None = None  # a scene launch's landing time, decided at the press


@dataclass(frozen=True)
class SetMacros:
    writes: tuple  # (path, rack name, macro index, value) per macro


@dataclass(frozen=True)
class SaveFxSnapshots:
    text: str


@dataclass(frozen=True)
class SaveFxScenes:
    text: str


@dataclass(frozen=True)
class SetFaderParameter:
    row: int  # 0-7, pad 1 first
    name: str  # the parameter's name at the press: a different parameter isn't written
    value: float


@dataclass(frozen=True)
class BindFader:
    row: int  # 0-7: bind Live's selected parameter to this row


@dataclass(frozen=True)
class SaveFaderBindings:
    text: str


@dataclass(frozen=True)
class StepTrack:
    step: int  # -1 previous, 1 next


@dataclass(frozen=True)
class StepDevice:
    step: int  # -1 previous, 1 next


# Sequencer Mode actions. Track indexes are song.tracks indexes.


@dataclass(frozen=True)
class HighlightSlot:
    track: int
    scene: int


@dataclass(frozen=True)
class SetArms:
    arms: tuple  # (track, bool) per track to change


@dataclass(frozen=True)
class ToggleDetailView:
    # Clip view if the Detail view shows anything else or is hidden, else Device view.
    pass


@dataclass(frozen=True)
class EditNotes:
    # One undo step: create the clip if the slot is empty, remove, then add.
    track: int
    scene: int
    remove: tuple = ()  # note ids
    add: tuple = ()  # (pitch, start, duration, velocity) per note
    create_length: float | None = None  # beats, for a new clip


@dataclass(frozen=True)
class RemovePitch:
    track: int
    scene: int
    pitch: int


@dataclass(frozen=True)
class ModifyNotes:
    track: int
    scene: int
    changes: tuple  # (note_id, start, velocity) per note


@dataclass(frozen=True)
class SetLoop:
    track: int
    scene: int
    start: float
    end: float


@dataclass(frozen=True)
class DuplicateLoop:
    track: int
    scene: int


@dataclass(frozen=True)
class SetDrumScroll:
    # The track's Drum Rack view: the rack row at the bottom of Live's 16 pads.
    track: int
    position: int


@dataclass(frozen=True)
class SelectDrumPad:
    track: int
    note: int


@dataclass(frozen=True)
class ShowMessage:
    text: str


# The colour of every pad the current mode owns, keyed by (column, pad).
Frame = dict[tuple[int, int], Light]
