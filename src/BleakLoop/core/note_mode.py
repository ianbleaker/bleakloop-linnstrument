"""Note Mode: column 1's controls page and scene page."""

from dataclasses import replace

from . import controls, layout, modes
from .leds import GREEN, LIME, MAGENTA, PINK, WHITE, Light
from .model import (
    AddScene,
    CaptureMidi,
    EnterMode,
    FireScene,
    FireSlot,
    PadPress,
    ShowClip,
    ShowMessage,
    StopTrackClips,
    TogglePlay,
)
from .modes import Mode


def handle(state, event, snapshot):
    if not isinstance(event, PadPress) or event.column != 1 or not event.pressed:
        return state, []
    key = (event.column, event.pad)
    if state.scene_page:
        return _scene_page(state, key, snapshot)
    if key == layout.UNDO:
        return state, controls.undo(snapshot)
    if key == layout.RECORD_CLIP:
        return state, _record_clip(state, snapshot)
    if key == layout.CAPTURE:
        return state, _capture_midi(snapshot)
    if key == layout.SCENE_PAGE:
        return replace(state, scene_page=True), []
    if key == layout.METRONOME:
        return state, controls.metronome(snapshot)
    if key == layout.PLAY_STOP:
        return state, _play_stop(snapshot)
    if key == layout.RECORD:
        return state, controls.record(snapshot)
    if key == layout.MODE_PAD:
        return modes.enter(state, Mode.SESSION), [EnterMode(Mode.SESSION)]
    return state, []


def _scene_page(state, key, snapshot):
    if key == layout.MODE_PAD:
        return replace(state, scene_page=False), []
    scene = state.window.scene + key[1] - 1
    if scene >= snapshot.scene_count:
        return state, []  # past the end of the Set: nothing launched, the page stays
    return replace(state, scene_page=False), [FireScene(scene, legato=False)]


def _record_clip(state, snapshot):
    track = snapshot.selected_track
    if track is None:
        return [ShowMessage("No selected track")]
    if track.is_foldable:
        return [ShowMessage("Cannot record on a group track")]
    if not track.armed:
        return [ShowMessage("Track not armed")]
    length = controls.record_length(state.fixed_length, snapshot)
    # From the highlighted scene down, then wrapping to the top.
    count = snapshot.scene_count
    for step in range(count):
        scene = (snapshot.selected_scene + step) % count
        if not track.clips[scene]:
            return [
                FireSlot(track.index, scene, legato=False, record_length=length),
                ShowClip(track.index, scene),
                ShowMessage("Record Clip"),
            ]
    # No empty slot: the new scene is added at the end, so it takes the next index.
    return [
        AddScene(),
        FireSlot(track.index, count, legato=False, record_length=length),
        ShowClip(track.index, count),
        ShowMessage("Record Clip: new scene"),
    ]


def _capture_midi(snapshot):
    if not snapshot.can_capture_midi:
        return [ShowMessage("Nothing to capture")]
    return [CaptureMidi(), ShowMessage("Capture MIDI")]


def _play_stop(snapshot):
    if not snapshot.session_view:
        return [TogglePlay()]
    track = snapshot.selected_track
    if track is None:
        return [ShowMessage("No selected track")]
    return [StopTrackClips(track.index), ShowMessage(f"Stop clips: {track.name}")]


def render(state, snapshot):
    # Column 1 only: the rest of the surface is the instrument.
    if state.scene_page:
        frame = {
            (1, pad): controls.scene_light(snapshot, state.window.scene, pad - 1)
            for pad in range(1, layout.ROWS)
        }
        frame[layout.MODE_PAD] = Light(WHITE)
        return frame
    return {
        layout.UNDO: Light(WHITE),
        layout.RECORD_CLIP: Light(MAGENTA),
        layout.CAPTURE: Light(LIME),
        layout.SCENE_PAGE: Light(PINK),
        layout.METRONOME: controls.metronome_light(snapshot),
        layout.PLAY_STOP: (
            Light(GREEN) if snapshot.session_view else controls.play_light(snapshot)
        ),
        layout.RECORD: controls.record_light(snapshot),
        layout.MODE_PAD: Light(WHITE),
    }
