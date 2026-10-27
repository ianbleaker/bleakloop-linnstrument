"""One example Set per manual layer, built from the core's own types."""

import enum
from dataclasses import replace

from BleakLoop.core.model import FaderView, SelectedTrack, SlotView, Snapshot, TrackView
from BleakLoop.core.modes import FxRack, Mode, State


class Layer(enum.Enum):
    SESSION = "session"
    SIDE = "side"
    SESSION_SHIFT = "session-shift"
    SPLIT = "session-split"
    MIXER = "mixer"
    FX = "fx"
    MAPPED_FX = "fx-mapped"
    DEV = "dev"
    LINNSTRUMENT = "linnstrument"
    LINNSTRUMENT_SHIFT = "linnstrument-shift"
    LINNSTRUMENT_SCENES = "linnstrument-scenes"

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

# Five stored snapshots, slot 2 the last to land, with the 4-bar length held.
_STORED = (FxRack("Drums", "FX Rack", 0, (0.0,) * 8),)
FX_SLOTS = tuple(_STORED if slot in (0, 1, 2, 8, 9) else None for slot in range(16))

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

SCENES = {
    Layer.SESSION: (State(fixed_length=2), SNAPSHOT),
    Layer.SIDE: (State(fixed_length=2), SNAPSHOT),
    Layer.SESSION_SHIFT: (State(fixed_length=2, shift=True), SNAPSHOT),
    Layer.SPLIT: (State(split=True, fixed_length=2), FX_SNAPSHOT),
    Layer.MIXER: (State(mixer=True), MIXER_SNAPSHOT),
    Layer.FX: (State(fx=True, fx_slots=FX_SLOTS, fx_landed=1, fx_length=4), FX_SNAPSHOT),
    Layer.MAPPED_FX: (
        State(fx=True, fx_slots=FX_SLOTS, fader_source="mapped"),
        MAPPED_SNAPSHOT,
    ),
    Layer.DEV: (State(dev=True, fixed_length=2), SNAPSHOT),
    Layer.LINNSTRUMENT: (State(mode=Mode.LINNSTRUMENT), SNAPSHOT),
    Layer.LINNSTRUMENT_SHIFT: (State(mode=Mode.LINNSTRUMENT, shift=True), SNAPSHOT),
    Layer.LINNSTRUMENT_SCENES: (State(mode=Mode.LINNSTRUMENT, scene_page=True), SNAPSHOT),
}
