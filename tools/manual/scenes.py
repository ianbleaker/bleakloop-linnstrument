"""One example Set per manual layer, built from the core's own types."""

import enum
from dataclasses import replace

from BleakLoop.core.model import SelectedTrack, SlotView, Snapshot, TrackView
from BleakLoop.core.modes import Mode, State


class Layer(enum.Enum):
    SESSION = "session"
    SIDE = "side"
    SESSION_SHIFT = "session-shift"
    MIXER = "mixer"
    NOTE = "note"
    NOTE_SCENES = "note-scenes"

    @property
    def slug(self):
        return self.value


EMPTY = SlotView()
CLIP = SlotView(has_clip=True)
PLAYING = SlotView(has_clip=True, is_playing=True)
TRIGGERED = SlotView(has_clip=True, is_triggered=True)
RECORDING = SlotView(has_clip=True, is_playing=True, is_recording=True)

# Live track colours chosen to match five different device colours.
TRACKS = (
    TrackView(
        index=0, name="Drums", colour=0xEE9969, slots=(PLAYING, CLIP, EMPTY, EMPTY)
    ),
    TrackView(
        index=1, name="Bass", colour=0x70FC6A, slots=(CLIP, PLAYING, EMPTY, EMPTY)
    ),
    TrackView(
        index=2, name="Keys", colour=0x5C8BF9, slots=(TRIGGERED, CLIP, CLIP, EMPTY)
    ),
    TrackView(
        index=3,
        name="Lead",
        colour=0xB85BDB,
        arm=True,
        has_midi_input=True,
        slots=(CLIP, RECORDING, EMPTY, EMPTY),
    ),
    TrackView(
        index=4, name="Pads", colour=0xFFFD4C, slots=(EMPTY, CLIP, EMPTY, PLAYING)
    ),
)

VOLUMES = (0.85, 0.6, 0.4, 0.25, 0.95)

SNAPSHOT = Snapshot(
    is_playing=True,
    song_beats=0.0,
    tempo=120.0,
    metronome=False,
    session_view=True,
    track_count=len(TRACKS),
    scene_count=4,
    tracks=TRACKS,
    selected_track=SelectedTrack(
        index=3, name="Lead", armed=True, clips=(True, True, False, False)
    ),
)

MIXER_SNAPSHOT = replace(
    SNAPSHOT,
    tracks=tuple(
        replace(track, volume=volume) for track, volume in zip(TRACKS, VOLUMES)
    ),
)

SCENES = {
    Layer.SESSION: (State(fixed_length=2), SNAPSHOT),
    Layer.SIDE: (State(fixed_length=2), SNAPSHOT),
    Layer.SESSION_SHIFT: (State(fixed_length=2, shift=True), SNAPSHOT),
    Layer.MIXER: (State(mixer=True), MIXER_SNAPSHOT),
    Layer.NOTE: (State(mode=Mode.NOTE), SNAPSHOT),
    Layer.NOTE_SCENES: (State(mode=Mode.NOTE, scene_page=True), SNAPSHOT),
}
