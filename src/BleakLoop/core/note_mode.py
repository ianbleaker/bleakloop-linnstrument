"""Note Mode: column 1's controls page and scene page (S-76–S-86, S-106–S-108)."""

from dataclasses import replace

from . import controls, layout, modes, values
from .leds import GREEN, LIME, MAGENTA, PINK, WHITE, Light
from .model import (
    AddScene,
    CaptureMidi,
    ControlCC,
    EnterMode,
    FireScene,
    FireSlot,
    ShowClip,
    ShowMessage,
    StopTrackClips,
    TogglePlay,
)
from .modes import Mode


def handle(state, event, snapshot):
    if not isinstance(event, ControlCC) or not (
        values.CONTROL_CC_BASE <= event.cc < values.CONTROL_CC_BASE + layout.ROWS
    ):
        return state, []
    # Any value is a press: column 1 pads are toggles and send nothing on release (S-76).
    key = (1, layout.control_pad(event.cc))
    if state.scene_page:
        return _scene_page(state, key, snapshot)
    if key == layout.UNDO:
        return state, controls.undo(snapshot)  # S-77
    if key == layout.RECORD_CLIP:
        return state, _record_clip(state, snapshot)  # S-78
    if key == layout.CAPTURE:
        return state, _capture_midi(snapshot)  # S-79
    if key == layout.SCENE_PAGE:
        return replace(state, scene_page=True), []  # S-106
    if key == layout.METRONOME:
        return state, controls.metronome(snapshot)  # S-81
    if key == layout.PLAY_STOP:
        return state, _play_stop(snapshot)  # S-82, S-83
    if key == layout.RECORD:
        return state, controls.record(snapshot)  # S-84
    if key == layout.MODE_PAD:
        return modes.enter(state, Mode.SESSION), [EnterMode(Mode.SESSION)]  # S-85
    return state, []


def _scene_page(state, key, snapshot):
    if key == layout.MODE_PAD:
        return replace(state, scene_page=False), []  # S-108
    scene = state.window.scene + key[1] - 1
    if scene >= snapshot.scene_count:
        return state, []  # past the end of the Set: nothing launched, the page stays
    return replace(state, scene_page=False), [FireScene(scene, legato=False)]  # S-107


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
        return [TogglePlay()]  # S-83
    track = snapshot.selected_track
    if track is None:
        return [ShowMessage("No selected track")]
    return [StopTrackClips(track.index), ShowMessage(f"Stop clips: {track.name}")]  # S-82


def render(state, snapshot):
    # Column 1 only: the rest of the surface is the instrument (S-5).
    if state.scene_page:
        frame = {
            (1, pad): controls.scene_light(snapshot, state.window.scene, pad - 1)
            for pad in range(1, layout.ROWS)
        }  # S-107
        frame[layout.MODE_PAD] = Light(WHITE)  # S-108
        return frame
    return {
        layout.UNDO: Light(WHITE),  # S-77
        layout.RECORD_CLIP: Light(MAGENTA),  # S-78
        layout.CAPTURE: Light(LIME),  # S-79
        layout.SCENE_PAGE: Light(PINK),  # S-106
        layout.METRONOME: controls.metronome_light(snapshot),  # S-81
        layout.PLAY_STOP: (
            Light(GREEN) if snapshot.session_view else controls.play_light(snapshot)
        ),  # S-82, S-83
        layout.RECORD: controls.record_light(snapshot),  # S-84
        layout.MODE_PAD: Light(WHITE),  # S-85
    }
