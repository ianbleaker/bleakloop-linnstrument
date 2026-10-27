"""Column 1: the control column, the same in every mode, and Linnstrument Mode's scene page.

In Linnstrument Mode the player is playing the selected track, so Record, Capture and
Shift + Play/Stop act on it.
"""

from dataclasses import replace

from . import controls, faders, fx, layout, mixer, modes
from .leds import (
    BLUE,
    CYAN,
    GREEN,
    LIME,
    MAGENTA,
    OFF,
    PINK,
    RED,
    WHITE,
    Blink,
    Light,
)
from .model import (
    AddScene,
    CaptureAndInsertScene,
    CaptureMidi,
    ClipTarget,
    EnterMode,
    FireScene,
    FireSlot,
    QuantizeClip,
    SetLaunchQuantization,
    ShowClip,
    ShowMessage,
    StopAllClips,
    StopTrackClips,
    TogglePlay,
)
from .modes import Mode, Origin

# Live's launch quantization names, indexed by its value.
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

# One pad cycles through the lengths, so its colour shows the current one.
FIXED_LENGTH_COLOURS = {None: OFF, 1: CYAN, 2: BLUE, 4: MAGENTA, 8: PINK}


def handle(state, event, snapshot):
    # A column-1 PadPress, pressed or released.
    key = (event.column, event.pad)
    if state.scene_page:
        return _scene_page(state, key, event.pressed, snapshot)
    if key == layout.SHIFT:
        return replace(state, shift=event.pressed), []
    if not event.pressed:
        return state, []
    if state.shift:
        return _shift(state, key, snapshot)
    return _normal(state, key, snapshot)


def _normal(state, key, snapshot):
    linnstrument = state.mode is Mode.LINNSTRUMENT
    if key == layout.PLAY_STOP:
        return state, [TogglePlay()]
    if key == layout.RECORD:
        return state, _record_clip(state, snapshot) if linnstrument else controls.record(snapshot)
    if key == layout.CAPTURE:
        if linnstrument:
            return state, _capture_midi(snapshot)
        return state, [CaptureAndInsertScene(), ShowMessage("Capture and Insert Scene")]
    if key == layout.METRONOME:
        return state, controls.metronome(snapshot)
    if key == layout.FIXED_LENGTH:
        return _fixed_length(state)
    if key == layout.UNDO:
        return state, controls.undo(snapshot)
    if key == layout.MODE_PAD:
        if linnstrument:
            return _back(state)
        state, actions = mixer.reset(state)
        state, more = faders.reset(state)
        return (
            modes.enter(state, Mode.LINNSTRUMENT),
            actions + more + [EnterMode(Mode.LINNSTRUMENT)],
        )
    return state, []


def _shift(state, key, snapshot):
    # Session Shift + Record, Session Shift + Mode and Shift + Fixed Length do nothing.
    linnstrument = state.mode is Mode.LINNSTRUMENT
    if key == layout.PLAY_STOP:
        if linnstrument:
            return state, _stop_track(snapshot)
        return state, [StopAllClips(), ShowMessage("Stop all clips")]
    if key == layout.RECORD and linnstrument:
        return state, controls.record(snapshot)
    if key == layout.QUANTIZE:
        return state, _quantize(snapshot)
    if key == layout.LAUNCH_QUANTIZATION:
        return _launch_quantization(state, snapshot)
    if key == layout.UNDO:
        return state, controls.redo(snapshot)
    if key == layout.SCENE_PAGE and linnstrument:
        return replace(state, scene_page=True), []
    return state, []


def _back(state):
    # Back to the layer Linnstrument Mode was entered from, through its own entry path.
    state = modes.enter(state, Mode.SESSION)
    actions = [EnterMode(Mode.SESSION)]
    if state.came_from is Origin.MIXER:
        state, more = mixer.toggle(state)
    elif state.came_from is Origin.FX:
        state, more = fx.toggle(state)
    else:
        more = []
    return state, actions + more


def _scene_page(state, key, pressed, snapshot):
    # Opened while Shift is held: that hold's release mustn't close it, a new press does.
    if not pressed:
        if key == layout.SHIFT:
            return replace(state, shift=False), []
        return state, []
    if key == layout.SHIFT:
        return replace(state, scene_page=False), []
    if key[1] > layout.WINDOW_SCENES:
        return state, []  # dark: the page shows the window's scenes only
    scene = state.window.scene + key[1] - 1
    if scene >= snapshot.scene_count:
        return state, []  # past the end of the Set: nothing launched, the page stays
    return replace(state, scene_page=False), [FireScene(scene, legato=False)]


def _fixed_length(state):
    cycle = (None, *layout.FIXED_LENGTHS)
    bars = cycle[(cycle.index(state.fixed_length) + 1) % len(cycle)]
    if bars is None:
        return replace(state, fixed_length=None), [ShowMessage("Fixed Length OFF")]
    message = ShowMessage(f"Fixed Length {bars} bar" + ("s" if bars > 1 else ""))
    return replace(state, fixed_length=bars), [message]


def _stop_track(snapshot):
    track = snapshot.selected_track
    if track is None:
        return [ShowMessage("No selected track")]
    return [StopTrackClips(track.index), ShowMessage(f"Stop clips: {track.name}")]


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


def _quantize(snapshot):
    candidates = [
        (ClipTarget.HIGHLIGHTED, snapshot.highlighted_clip),
        (ClipTarget.DETAIL, snapshot.detail_clip),
        (ClipTarget.PLAYING, snapshot.playing_clip),
    ]
    found = [(target, clip) for target, clip in candidates if clip is not None]
    if not found:
        return [ShowMessage("No clip to quantize")]
    target, clip = found[0]
    if not clip.is_midi:
        return [ShowMessage("Cannot quantize an audio clip")]
    return [QuantizeClip(target), ShowMessage("Quantize 1/16")]


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


def render(state, snapshot):
    # Column 1 only. Copy and Delete hide the Shift layer.
    shift_held = Light(WHITE, Blink.FAST if state.shift else Blink.STEADY)
    if state.scene_page:
        frame = {
            (1, pad): controls.scene_light(snapshot, state.window.scene, pad - 1)
            for pad in range(1, layout.WINDOW_SCENES + 1)
        }
        frame[layout.MODE_PAD] = Light(OFF)
        frame[layout.SHIFT] = shift_held
        return frame
    linnstrument = state.mode is Mode.LINNSTRUMENT
    if state.shift and not state.copy and not state.delete:
        frame = {
            layout.PLAY_STOP: Light(RED),
            layout.RECORD: controls.record_light(snapshot) if linnstrument else Light(OFF),
            layout.QUANTIZE: Light(MAGENTA),
            layout.LAUNCH_QUANTIZATION: Light(GREEN if snapshot.launch_quantization != 0 else RED),
            layout.FIXED_LENGTH: Light(OFF),
            layout.UNDO: Light(WHITE),
            layout.SCENE_PAGE: Light(PINK if linnstrument else OFF),
        }
    else:
        frame = {
            layout.PLAY_STOP: controls.play_light(snapshot),
            layout.RECORD: Light(RED) if linnstrument else controls.record_light(snapshot),
            layout.CAPTURE: Light(LIME),
            layout.METRONOME: controls.metronome_light(snapshot),
            layout.FIXED_LENGTH: Light(FIXED_LENGTH_COLOURS[state.fixed_length]),
            layout.UNDO: Light(WHITE),
            layout.MODE_PAD: Light(MAGENTA),
        }
    frame[layout.SHIFT] = shift_held
    return frame
