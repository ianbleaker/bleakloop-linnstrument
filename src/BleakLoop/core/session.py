"""Session Mode: clip slots, the bottom row, columns 1, 15 and 16, and the Shift layer (S-18–S-69)."""

from dataclasses import replace

from . import controls, layout, modes
from .leds import (
    BLUE,
    GREEN,
    LIME,
    OFF,
    ORANGE,
    RED,
    WHITE,
    YELLOW,
    Blink,
    Light,
    track_colour,
)
from .model import (
    ArmExclusive,
    EnterMode,
    FireScene,
    FireSlot,
    PadPress,
    SelectTrack,
    SetLaunchQuantization,
    SetTempo,
    ShowMessage,
    StopAllClips,
    StopTrackClips,
    ToggleMute,
    TogglePlay,
    ToggleSolo,
)
from .modes import Mode, TrackControl
from .values import TEMPO_MAX, TEMPO_MIN

# Live's launch quantization names, indexed by its value (S-51).
QUANTIZATION_NAMES = (
    "None",
    "8 Bars",
    "4 Bars",
    "2 Bars",
    "1 Bar",
    "1/2",
    "1/2T",
    "1/4",
    "1/4T",
    "1/8",
    "1/8T",
    "1/16",
    "1/16T",
    "1/32",
)
DEFAULT_QUANTIZATION = 4  # 1 Bar

# Column 15 pads 6-8 colours (S-61).
TRACK_CONTROL_COLOURS = {
    TrackControl.MUTE: ORANGE,
    TrackControl.SOLO: BLUE,
    TrackControl.ARM: RED,
}

TRACK_CONTROL_NAMES = {
    TrackControl.MUTE: "Mute",
    TrackControl.SOLO: "Solo",
    TrackControl.ARM: "Arm",
}


def handle(state, event, snapshot):
    # Column 1 CCs are ignored in Session Mode (S-76).
    if not isinstance(event, PadPress):
        return state, []
    key = (event.column, event.pad)
    if key == layout.SHIFT:
        return replace(state, shift=event.pressed), []  # S-100
    if not event.pressed:
        return state, []
    if event.column == 1:
        return _column_1(state, event.pad, snapshot)
    if event.column in layout.GRID_COLUMNS:
        if event.pad == layout.ROWS:
            return state, _track_switch(state, _track(event.column, snapshot))
        return state, _slot(state, event, snapshot)
    if event.column == 15:
        return _column_15(state, key, snapshot)
    if event.column == layout.SCENE_COLUMN:
        scene = state.window.scene + event.pad - 1
        if scene < snapshot.scene_count:
            return state, [FireScene(scene, legato=state.shift)]  # S-63, S-64
    return state, []


def _track(column, snapshot):
    i = column - layout.GRID_COLUMNS[0]
    return snapshot.tracks[i] if i < len(snapshot.tracks) else None


def _column_1(state, pad, snapshot):
    key = (1, pad)
    if key == layout.UNDO:
        return state, controls.redo(snapshot) if state.shift else controls.undo(snapshot)  # S-45
    if key == layout.METRONOME:
        if state.shift:
            return _launch_quantization(state, snapshot)  # S-51
        return state, controls.metronome(snapshot)  # S-50
    if state.shift:
        return state, []  # S-101
    if key == layout.PLAY_STOP:
        return state, [TogglePlay()]  # S-52
    if key == layout.MODE_PAD:
        return modes.enter(state, Mode.NOTE), [EnterMode(Mode.NOTE)]  # S-56
    return state, []


def _launch_quantization(state, snapshot):
    if snapshot.launch_quantization != 0:
        state = replace(state, quantization_memory=snapshot.launch_quantization)
        return state, [SetLaunchQuantization(0), ShowMessage("Launch Quantization: None")]
    value = state.quantization_memory
    if value is None:
        value = DEFAULT_QUANTIZATION
    return state, [
        SetLaunchQuantization(value),
        ShowMessage(f"Launch Quantization: {QUANTIZATION_NAMES[value]}"),
    ]


def _slot(state, event, snapshot):
    # S-18, S-19, S-28
    track = _track(event.column, snapshot)
    scene = state.window.scene + event.pad - 1
    if track is None or scene >= snapshot.scene_count:
        return []
    return [FireSlot(track.index, scene, legato=state.shift)]


def _track_switch(state, track):
    if track is None:
        return []  # S-44
    if state.track_control is TrackControl.MUTE:
        if state.shift:
            return [StopTrackClips(track.index), ShowMessage(f"Stop clips: {track.name}")]  # S-41
        return [ToggleMute(track.index)]  # S-40
    if state.shift:
        return []
    if state.track_control is TrackControl.SOLO:
        return [ToggleSolo(track.index)]  # S-42
    actions = [SelectTrack(track.index)]  # S-43
    if track.can_be_armed:
        actions.append(ArmExclusive(track.index, not track.arm))
    return actions


def _column_15(state, key, snapshot):
    if state.shift:
        if key in layout.WINDOW_MOVES:
            return _move_window(state, layout.WINDOW_MOVES[key], snapshot)  # S-58
        if key == layout.STOP_ALL:
            return state, [StopAllClips(), ShowMessage("Stop all clips")]  # S-60
        if key in layout.TEMPO_STEPS:
            bpm = min(TEMPO_MAX, max(TEMPO_MIN, snapshot.tempo + layout.TEMPO_STEPS[key]))
            return state, [SetTempo(bpm), ShowMessage(f"Tempo {bpm:.1f} BPM")]  # S-62
        return state, []
    if key in layout.TRACK_CONTROL_PADS:
        mode = TrackControl[layout.TRACK_CONTROL_PADS[key]]
        message = ShowMessage(f"Track Control: {TRACK_CONTROL_NAMES[mode]}")
        return replace(state, track_control=mode), [message]  # S-61
    return state, []


def _move_window(state, steps, snapshot):
    window = layout.move_window(state.window, *steps, snapshot.track_count, snapshot.scene_count)
    if window == state.window:
        return state, []
    last_track = min(window.track + layout.WINDOW_TRACKS, snapshot.track_count)
    last_scene = min(window.scene + layout.WINDOW_SCENES, snapshot.scene_count)
    message = (
        f"Tracks {window.track + 1}–{last_track}, "
        f"Scenes {window.scene + 1}–{last_scene}"
    )
    return replace(state, window=window), [ShowMessage(message)]


def render(state, snapshot):
    frame = {
        (column, pad): Light(OFF)
        for column in range(1, layout.COLUMNS)
        for pad in range(1, layout.ROWS + 1)
    }
    for column in layout.GRID_COLUMNS:
        track = _track(column, snapshot)
        for pad in range(1, layout.ROWS):
            frame[(column, pad)] = _slot_light(track, pad - 1)
        frame[(column, layout.ROWS)] = _track_switch_light(state, track)
    for pad in range(1, layout.ROWS):
        frame[(layout.SCENE_COLUMN, pad)] = controls.scene_light(
            snapshot, state.window.scene, pad - 1
        )  # S-68
    if state.shift:
        _render_shift_layer(frame, snapshot)
    else:
        _render_normal_layer(frame, state, snapshot)
    return frame


def _slot_light(track, row):
    # S-34-S-39, highest priority first; the same on both layers (S-102).
    if track is None or row >= len(track.slots):
        return Light(OFF)
    slot = track.slots[row]
    if slot.is_recording:
        return Light(RED)
    if slot.is_triggered:
        return Light(YELLOW)
    if slot.is_playing:
        return Light(track_colour(track.colour), Blink.TEMPO)
    if slot.has_clip:
        return Light(track_colour(track.colour))
    if track.arm or track.implicit_arm:
        return Light(WHITE)
    return Light(OFF)


def _track_switch_light(state, track):
    if track is None:
        return Light(OFF)  # S-44
    if state.shift:
        return Light(RED if state.track_control is TrackControl.MUTE else OFF)  # S-41
    if state.track_control is TrackControl.MUTE:
        return Light(LIME if track.mute else ORANGE)  # S-40
    if state.track_control is TrackControl.SOLO:
        return Light(BLUE if track.solo else LIME)  # S-42
    return Light(RED if track.arm or track.implicit_arm else LIME)  # S-43


def _render_normal_layer(frame, state, snapshot):
    frame[layout.UNDO] = Light(WHITE)  # S-45
    frame[layout.METRONOME] = controls.metronome_light(snapshot)  # S-50
    frame[layout.PLAY_STOP] = controls.play_light(snapshot)  # S-52
    frame[layout.MODE_PAD] = Light(WHITE)  # S-56
    for key, name in layout.TRACK_CONTROL_PADS.items():
        mode = TrackControl[name]
        blink = Blink.TEMPO if mode is state.track_control else Blink.STEADY
        frame[key] = Light(TRACK_CONTROL_COLOURS[mode], blink)  # S-61
    frame[layout.SHIFT] = Light(WHITE)  # S-69


def _render_shift_layer(frame, snapshot):
    # S-102
    frame[layout.UNDO] = Light(WHITE)  # S-45
    frame[layout.LAUNCH_QUANTIZATION] = Light(
        GREEN if snapshot.launch_quantization != 0 else RED
    )  # S-51
    for key in layout.WINDOW_MOVES:
        frame[key] = Light(YELLOW)  # S-58
    frame[layout.STOP_ALL] = Light(RED)  # S-60
    for key in layout.TEMPO_STEPS:
        frame[key] = Light(GREEN)  # S-62
    frame[layout.SHIFT] = Light(WHITE, Blink.FAST)  # S-69
