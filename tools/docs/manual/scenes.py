"""One example Set per manual layer, built from the core's own types."""

import enum
from dataclasses import replace

from BleakLoop.core.model import (
    DrumView,
    FaderView,
    NoteView,
    SelectedTrack,
    SequencerView,
    SlotView,
    Snapshot,
    TrackView,
)
from BleakLoop.core.modes import FxRack, Mode, State


class Layer(enum.Enum):
    SESSION = "session"
    SIDE = "side"
    SESSION_SHIFT = "session-shift"
    SPLIT = "session-split"
    MIXER = "mixer"
    FX = "fx"
    MAPPED_FX = "fx-mapped"
    DEVICE_CLIP = "dev"
    LINNSTRUMENT = "linnstrument"
    LINNSTRUMENT_SHIFT = "linnstrument-shift"
    LINNSTRUMENT_SCENES = "linnstrument-scenes"
    SEQUENCER = "sequencer"
    SEQUENCER_SETTINGS = "sequencer-settings"
    SEQUENCER_SHIFT = "sequencer-shift"
    SEQUENCER_DRUMS = "sequencer-drums"

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
        index=2,
        name="Keys",
        colour=0x5C8BF9,
        solo=True,
        slots=(TRIGGERED, CLIP, CLIP, EMPTY),
    ),
    TrackView(
        index=3,
        name="Lead",
        colour=0xB85BDB,
        arm=True,
        selected=True,
        has_midi_input=True,
        slots=(CLIP, RECORDING, EMPTY, EMPTY),
    ),
    TrackView(
        index=4,
        name="Pads",
        colour=0xFFFD4C,
        mute=True,
        slots=(EMPTY, CLIP, EMPTY, PLAYING),
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
    any_muted=True,
    any_soloed=True,
    any_armed=True,
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

# Five stored snapshots and two scene snapshots, scene 3's the last to land, with the 4-bar
# length held.
_STORED = (FxRack("Drums", "FX Rack", 0, (0.0,) * 8),)
FX_SLOTS = tuple(_STORED if slot in (0, 1, 2, 8, 9) else None for slot in range(16))
FX_SCENES = (_STORED, None, _STORED)

# Device FX on an eight-macro rack, at varied values.
FADER_VALUES = (100, 30, 64, 127, 0, 85, 45, 110)
FX_SNAPSHOT = replace(
    SNAPSHOT,
    faders=tuple(
        FaderView(f"Macro {row + 1}", value, 0.0, 127.0)
        for row, value in enumerate(FADER_VALUES)
    ),
)

# Mapped FX with rows 3 and 7 unbound.
MAPPED_VALUES = (0.85, 0.5, None, 0.3, 0.7, 1.0, None, 0.15)
MAPPED_SNAPSHOT = replace(
    SNAPSHOT,
    faders=tuple(
        None if value is None else FaderView("Bound", value, 0.0, 1.0)
        for value in MAPPED_VALUES
    ),
)

# Sequencer Mode on Lead's clip at 1/16, as in the mockup: E2 selected, G2 on the other
# steps, the loop on pages 1-2, and the playhead on step 9, whose G2 is playing.
SEQ_PITCH = 52  # E2
SEQ_OTHER = 55  # G2
_SELECTED_STEPS = (0, 3, 6, 10, 16, 19, 22, 28, 32, 35, 38, 42, 48, 51, 54, 60)
_OTHER_STEPS = (2, 8, 12, 14, 24, 26, 30, 34, 40, 44, 46, 56, 58, 62)
SEQ_SNAPSHOT = replace(
    SNAPSHOT,
    sequencer=SequencerView(
        track=3,
        name="Lead",
        scene=1,
        is_midi=True,
        has_clip=True,
        is_playing=True,
        loop_end=32.0,
        position=2.1,
        notes=tuple(
            NoteView(i, pitch, step * 0.25, 0.25, 100)
            for i, (pitch, step) in enumerate(
                [(SEQ_PITCH, step) for step in _SELECTED_STEPS]
                + [(SEQ_OTHER, step) for step in _OTHER_STEPS]
            )
        ),
    ),
)
SEQUENCER = State(mode=Mode.SEQUENCER, seq_pitch=SEQ_PITCH, fixed_length=2)

# A Drum Rack in Live's default view: kick, snare and hats filled, the snare selected, the
# kick playing on the playhead's step.
_KICK, _SNARE, _HAT, _OPEN_HAT = 36, 38, 42, 46
_DRUM_HITS = (
    [(_KICK, step) for step in range(0, 64, 8)]
    + [(_SNARE, step) for step in range(4, 64, 8)]
    + [(_HAT, step) for step in range(2, 64, 4)]
)
SEQ_DRUM_SNAPSHOT = replace(
    SEQ_SNAPSHOT,
    sequencer=replace(
        SEQ_SNAPSHOT.sequencer,
        name="Drums",
        position=2.1,
        notes=tuple(
            NoteView(i, pitch, step * 0.25, 0.25, 100) for i, (pitch, step) in enumerate(_DRUM_HITS)
        ),
        drum=DrumView(9, _SNARE, frozenset({_KICK, _SNARE, 39, _HAT, 44, _OPEN_HAT, 49, 51})),
    ),
)

SCENES = {
    Layer.SESSION: (State(fixed_length=2), SNAPSHOT),
    Layer.SIDE: (State(fixed_length=2), SNAPSHOT),
    Layer.SESSION_SHIFT: (State(fixed_length=2, shift=True), SNAPSHOT),
    Layer.SPLIT: (State(split=True, fixed_length=2), FX_SNAPSHOT),
    Layer.MIXER: (State(mixer=True), MIXER_SNAPSHOT),
    Layer.FX: (
        State(fx=True, fx_slots=FX_SLOTS, fx_scenes=FX_SCENES, fx_landed_scene=2, fx_length=4),
        FX_SNAPSHOT,
    ),
    Layer.MAPPED_FX: (
        State(fx=True, fx_slots=FX_SLOTS, fader_source="mapped"),
        MAPPED_SNAPSHOT,
    ),
    Layer.DEVICE_CLIP: (State(device_clip=True, fixed_length=2), SNAPSHOT),
    Layer.LINNSTRUMENT: (State(mode=Mode.LINNSTRUMENT), SNAPSHOT),
    Layer.LINNSTRUMENT_SHIFT: (State(mode=Mode.LINNSTRUMENT, shift=True), SNAPSHOT),
    Layer.LINNSTRUMENT_SCENES: (State(mode=Mode.LINNSTRUMENT, scene_page=True), SNAPSHOT),
    Layer.SEQUENCER: (SEQUENCER, SEQ_SNAPSHOT),
    Layer.SEQUENCER_SETTINGS: (replace(SEQUENCER, seq_settings=True), SEQ_SNAPSHOT),
    Layer.SEQUENCER_SHIFT: (replace(SEQUENCER, shift=True), SEQ_SNAPSHOT),
    Layer.SEQUENCER_DRUMS: (SEQUENCER, SEQ_DRUM_SNAPSHOT),
}
