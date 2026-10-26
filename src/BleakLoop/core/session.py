"""Session Mode: clip slots, the bottom row, columns 15 and 16, and the Shift layer."""

from dataclasses import replace

from . import column_1, controls, layout, mixer, modes
from .leds import (
    BLUE,
    GREEN,
    LIME,
    MAGENTA,
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
    CopyClip,
    CopyScene,
    DeleteClip,
    DeleteScene,
    EnterMode,
    FireScene,
    FireSlot,
    PadPress,
    SceneSelected,
    SelectTrack,
    SetTempo,
    ShowClip,
    ShowMessage,
    StopTrackClips,
    ToggleMute,
    ToggleSolo,
)
from .modes import ClipSource, Mode, SceneSource, TrackControl
from .values import TEMPO_MAX, TEMPO_MIN

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
    if isinstance(event, SceneSelected):
        # Keep the scene Capture selected in view.
        window = layout.scroll_to_scene(
            state.window, event.scene, snapshot.track_count, snapshot.scene_count
        )
        return replace(state, window=window), []
    if not isinstance(event, PadPress):
        return state, []
    key = (event.column, event.pad)
    if key == layout.SHIFT:
        return column_1.handle(state, event, snapshot)
    # Under Shift, Copy and Delete's pads are window moves.
    shift_layer = state.shift and not state.copy and not state.delete
    if key == layout.COPY and not (shift_layer and event.pressed):
        if not event.pressed:
            return replace(state, copy=False, copy_source=None), []
        if state.mixer:
            return state, []
        return replace(state, copy=True), [ShowMessage("Copy: pick a clip or scene")]
    if key == layout.DELETE and not (shift_layer and event.pressed):
        if not event.pressed:
            return replace(state, delete=False), []
        if state.mixer:
            return state, []
        return replace(state, delete=True), [ShowMessage("Delete Mode ON")]
    if state.mixer and event.column in layout.GRID_COLUMNS:
        # Every pad is the fader, pad 8 included; releases matter too.
        return mixer.press(state, event, snapshot)
    if not event.pressed:
        return state, []
    # Copy over Delete over Shift.
    if state.copy:
        return _copy(state, event, snapshot)
    if state.delete:
        return _delete(state, event, snapshot)
    if event.column == 1:
        return column_1.handle(state, event, snapshot)
    if event.column in layout.GRID_COLUMNS:
        if event.pad == layout.ROWS:
            return state, _track_switch(state, _track(event.column, snapshot))
        return _slot(state, event, snapshot)
    if event.column == 15:
        return _column_15(state, key, snapshot)
    if _is_scene(event):  # pad 8 is reserved
        scene = state.window.scene + event.pad - 1
        if scene < snapshot.scene_count:
            return state, [FireScene(scene, legato=state.shift)]
    return state, []


def _track(column, snapshot):
    i = column - layout.GRID_COLUMNS[0]
    return snapshot.tracks[i] if i < len(snapshot.tracks) else None


def _slot_at(state, event, snapshot):
    # The track and scene of a clip-slot press, or None outside the session.
    track = _track(event.column, snapshot)
    scene = state.window.scene + event.pad - 1
    if track is None or scene >= snapshot.scene_count:
        return None
    return track, scene


def _is_slot(event):
    return event.column in layout.GRID_COLUMNS and event.pad < layout.ROWS


def _is_scene(event):
    return event.column == layout.SCENE_COLUMN and event.pad < layout.ROWS


def _slot(state, event, snapshot):
    target = _slot_at(state, event, snapshot)
    if target is None:
        return state, []
    track, scene = target
    slot = track.slots[event.pad - 1]
    armed = track.arm or track.implicit_arm
    starts = armed and not slot.has_clip
    # A press that starts or continues a recording.
    records = (
        starts or slot.is_recording or (slot.is_playing and armed and snapshot.session_record)
    )
    # Live only starts a new recording in an empty slot on an armed track.
    length = controls.record_length(state.fixed_length, snapshot) if starts else None
    actions = [FireSlot(track.index, scene, legato=state.shift, record_length=length)]
    if records:
        actions.append(ShowClip(track.index, scene))
        if track.has_midi_input:
            state = modes.enter(state, Mode.LINNSTRUMENT)
            actions.append(EnterMode(Mode.LINNSTRUMENT))
    return state, actions


def _copy(state, event, snapshot):
    if _is_slot(event):
        return _copy_slot(state, event, snapshot)
    if _is_scene(event):
        return _copy_scene(state, event, snapshot)
    return state, []


def _copy_slot(state, event, snapshot):
    target = _slot_at(state, event, snapshot)
    if target is None:
        return state, []
    track, scene = target
    slot = track.slots[event.pad - 1]
    source = state.copy_source
    if source is None:
        if slot.has_clip:
            source = ClipSource(track.index, scene, track.has_midi_input)
            return replace(state, copy_source=source), [ShowMessage("Copy: pick an empty slot")]
        return state, [ShowMessage("Copy: pick a clip or scene")]
    if isinstance(source, SceneSource):
        return state, [ShowMessage("Pick a scene target")]
    dropped = replace(state, copy_source=None)
    if slot.has_clip:
        return dropped, [ShowMessage("Target not empty")]
    if track.is_foldable or track.has_midi_input != source.midi:
        return dropped, [ShowMessage("Cannot copy between MIDI and audio tracks")]
    copy = CopyClip(source.track, source.scene, track.index, scene)
    return dropped, [copy, ShowMessage("Clip copied")]


def _copy_scene(state, event, snapshot):
    scene = state.window.scene + event.pad - 1
    if scene >= snapshot.scene_count:
        return state, []
    row = event.pad - 1
    has = snapshot.scene_clips[row] if row < len(snapshot.scene_clips) else False
    source = state.copy_source
    if source is None:
        if has:
            state = replace(state, copy_source=SceneSource(scene))
            return state, [ShowMessage("Copy: pick an empty scene")]
        return state, [ShowMessage("Scene is empty")]
    if isinstance(source, ClipSource):
        return state, [ShowMessage("Pick a clip target")]
    dropped = replace(state, copy_source=None)
    if has:
        return dropped, [ShowMessage("Target scene not empty")]
    return dropped, [CopyScene(source.scene, scene), ShowMessage("Scene copied")]


def _delete(state, event, snapshot):
    if _is_slot(event):
        target = _slot_at(state, event, snapshot)
        if target is not None and target[0].slots[event.pad - 1].has_clip:
            track, scene = target
            return state, [DeleteClip(track.index, scene)]
        return state, []
    if _is_scene(event):
        scene = state.window.scene + event.pad - 1
        if scene >= snapshot.scene_count:
            return state, []
        if snapshot.scene_count == 1:
            return state, [ShowMessage("Cannot delete last scene")]
        window = layout.move_window(
            state.window, 0, 0, snapshot.track_count, snapshot.scene_count - 1
        )
        return replace(state, window=window), [DeleteScene(scene)]
    return state, []


def _track_switch(state, track):
    if track is None:
        return []
    if state.track_control is TrackControl.MUTE:
        if state.shift:
            return [StopTrackClips(track.index), ShowMessage(f"Stop clips: {track.name}")]
        return [ToggleMute(track.index)]
    if state.shift:
        return []
    if state.track_control is TrackControl.SOLO:
        return [ToggleSolo(track.index)]
    actions = [SelectTrack(track.index)]
    if track.can_be_armed:
        actions.append(ArmExclusive(track.index, not track.arm))
    return actions


def _column_15(state, key, snapshot):
    if state.shift:
        if key in layout.WINDOW_MOVES:
            return _move_window(state, layout.WINDOW_MOVES[key], snapshot)
        if key in layout.TEMPO_STEPS:
            bpm = min(TEMPO_MAX, max(TEMPO_MIN, snapshot.tempo + layout.TEMPO_STEPS[key]))
            return state, [SetTempo(bpm), ShowMessage(f"Tempo {bpm:.1f} BPM")]
        return state, []
    # Normal-layer 15/4 and 15/5 are reserved: no match here.
    if key == layout.MIXER:
        return mixer.toggle(state)
    if key in layout.TRACK_CONTROL_PADS:
        mode = TrackControl[layout.TRACK_CONTROL_PADS[key]]
        message = ShowMessage(f"Track Control: {TRACK_CONTROL_NAMES[mode]}")
        return replace(state, track_control=mode), [message]
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
    # Copy and Delete hide the Shift layer.
    shift_layer = state.shift and not state.copy and not state.delete
    frame = {
        (column, pad): Light(OFF)
        for column in range(1, layout.COLUMNS)
        for pad in range(1, layout.ROWS + 1)
    }
    for column in layout.GRID_COLUMNS:
        track = _track(column, snapshot)
        if state.mixer:
            if not shift_layer:
                _render_fader(frame, column, track)  # dark under Shift
            continue
        for pad in range(1, layout.ROWS):
            frame[(column, pad)] = _slot_light(track, pad - 1)
        frame[(column, layout.ROWS)] = _track_switch_light(state, shift_layer, track)
    for pad in range(1, layout.ROWS):
        frame[(layout.SCENE_COLUMN, pad)] = controls.scene_light(
            snapshot, state.window.scene, pad - 1
        )
    if shift_layer:
        _render_shift_layer(frame)
    else:
        _render_normal_layer(frame, state)
    frame.update(column_1.render(state, snapshot))
    _render_copy_source(frame, state)
    return frame


def _render_copy_source(frame, state):
    # The copy source: on top of everything else, and only while in the window.
    source = state.copy_source
    window = state.window
    if isinstance(source, ClipSource):
        column = source.track - window.track + layout.GRID_COLUMNS[0]
        pad = source.scene - window.scene + 1
        if column in layout.GRID_COLUMNS and 1 <= pad < layout.ROWS:
            frame[(column, pad)] = Light(RED, Blink.FAST)
    elif isinstance(source, SceneSource):
        pad = source.scene - window.scene + 1
        if 1 <= pad < layout.ROWS:
            frame[(layout.SCENE_COLUMN, pad)] = Light(RED, Blink.FAST)


def _render_fader(frame, column, track):
    # A bar in the track's colour from pad 8 up to the pad nearest Live's volume.
    if track is None:
        return
    for pad in range(mixer.lit_pad(track.volume), layout.ROWS + 1):
        frame[(column, pad)] = Light(track_colour(track.colour))


def _slot_light(track, row):
    # Highest priority first; the same on both layers.
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


def _track_switch_light(state, shift_layer, track):
    if track is None:
        return Light(OFF)
    if shift_layer:
        return Light(RED if state.track_control is TrackControl.MUTE else OFF)
    if state.track_control is TrackControl.MUTE:
        return Light(LIME if track.mute else ORANGE)
    if state.track_control is TrackControl.SOLO:
        return Light(BLUE if track.solo else LIME)
    return Light(RED if track.arm or track.implicit_arm else LIME)


def _render_normal_layer(frame, state):
    # Held Copy and Delete blink.
    frame[layout.COPY] = Light(RED, Blink.FAST) if state.copy else Light(MAGENTA)
    frame[layout.DELETE] = Light(RED, Blink.FAST if state.delete else Blink.STEADY)
    frame[layout.MIXER] = Light(WHITE, Blink.FAST if state.mixer else Blink.STEADY)
    for key, name in layout.TRACK_CONTROL_PADS.items():
        mode = TrackControl[name]
        blink = Blink.TEMPO if mode is state.track_control else Blink.STEADY
        frame[key] = Light(TRACK_CONTROL_COLOURS[mode], blink)


def _render_shift_layer(frame):
    for key in layout.WINDOW_MOVES:
        frame[key] = Light(YELLOW)
    for key in layout.TEMPO_STEPS:
        frame[key] = Light(GREEN)
