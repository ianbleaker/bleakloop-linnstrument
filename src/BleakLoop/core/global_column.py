"""The Global column: the control column, the same in every mode, and Linnstrument Mode's scene page.

In Linnstrument and Sequencer Mode the player is on the selected track, so Record, Capture
and Shift + Play/Stop act on it.
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
    EndUndoStep,
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


def layers(state):
    # The mode's Global column: its normal layer and its Shift layer, each its own buttons.
    if state.mode is Mode.LINNSTRUMENT:
        return layout.LINNSTRUMENT, layout.LINNSTRUMENT_SHIFT
    if state.mode is Mode.SEQUENCER:
        return layout.SEQUENCER_GLOBAL, layout.SEQUENCER_GLOBAL_SHIFT
    return layout.GLOBAL, layout.GLOBAL_SHIFT


def handle(state, event, snapshot):
    # A Global column PadPress, pressed or released.
    key = (event.column, event.pad)
    if state.scene_page:
        return _scene_page(state, key, event.pressed, snapshot)
    if key == layers(state)[0].shift:
        return replace(state, shift=event.pressed), []
    if not event.pressed:
        return state, []
    if state.shift:
        return _shift(state, key, snapshot)
    return _normal(state, key, snapshot)


def _normal(state, key, snapshot):
    pads = layers(state)[0]
    if key == pads.play_stop:
        return state, [TogglePlay()]
    if state.mode is Mode.SESSION:
        if key == pads.record:
            return state, controls.record(snapshot)
        if key == pads.capture:
            return state, [CaptureAndInsertScene(), ShowMessage("Capture and Insert Scene")]
    else:
        if key == pads.record_clip:
            return state, _record_clip(state, snapshot)
        if key == pads.capture_midi:
            return state, _capture_midi(snapshot)
    if key == pads.metronome:
        return state, controls.metronome(snapshot)
    if key == pads.fixed_length:
        return _fixed_length(state)
    if key == pads.undo:
        return state, controls.undo(snapshot)
    if state.mode is Mode.LINNSTRUMENT:
        if key == pads.back:
            return _back(state)
        return state, []
    if key == pads.linnstrument_mode:
        if state.mode is Mode.SEQUENCER:
            # The arm stays: the player plays the track they were sequencing.
            actions = []
            if state.seq_undo_open:
                state = replace(state, seq_undo_open=False)
                actions.append(EndUndoStep())
            return (
                modes.enter(state, Mode.LINNSTRUMENT),
                actions + [EnterMode(Mode.LINNSTRUMENT)],
            )
        state, actions = mixer.reset(state)
        state, more = faders.reset(state)
        return (
            modes.enter(state, Mode.LINNSTRUMENT),
            actions + more + [EnterMode(Mode.LINNSTRUMENT)],
        )
    return state, []


def _shift(state, key, snapshot):
    # Pads the Shift layer has no button on do nothing.
    pads = layers(state)[1]
    if state.mode is Mode.SESSION:
        if key == pads.stop_all:
            return state, [StopAllClips(), ShowMessage("Stop all clips")]
    else:
        if key == pads.stop_track:
            return state, _stop_track(snapshot)
        if key == pads.record:
            return state, controls.record(snapshot)
        if key == pads.scene_page:
            return replace(state, scene_page=True), []
    if key == pads.quantize:
        return state, _quantize(snapshot)
    if key == pads.launch_quantization:
        return _launch_quantization(state, snapshot)
    if key == pads.redo:
        return state, controls.redo(snapshot)
    return state, []


def _back(state):
    # Back to the layer Linnstrument Mode was entered from, through its own entry path.
    if state.came_from is Origin.SEQUENCER:
        return modes.enter(state, Mode.SEQUENCER), [EnterMode(Mode.SEQUENCER)]
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
    # Opened while Shift is held: that hold's release mustn't close it, Back's press does.
    shift = layers(state)[0].shift
    if not pressed:
        if key == shift:
            return replace(state, shift=False), []
        return state, []
    if key == layout.LINNSTRUMENT_SCENES.back:
        return replace(state, scene_page=False), []
    if key[0] != layout.GLOBAL_COLUMN or key == shift:
        return state, []
    if key[1] > layout.WINDOW_SCENES:
        return state, []  # dark: the page shows the window's scenes only
    scene = state.window.scene + key[1] - 1
    if scene >= snapshot.scene_count:
        return state, []  # past the end of the Set: nothing launched, the page stays
    # The newest launch replaces a pending one.
    actions = [FireScene(scene, legato=False), *fx.scene_launch(state, scene, snapshot)]
    return replace(state, scene_page=False, pending_launch=None), actions


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
    # The Global column only. Copy and Delete hide the Shift layer.
    normal, shift = layers(state)
    shift_held = Light(WHITE, Blink.FAST if state.shift else Blink.STEADY)
    if state.scene_page:
        frame = {(layout.GLOBAL_COLUMN, pad): Light(OFF) for pad in range(1, layout.ROWS + 1)}
        for pad in range(1, layout.WINDOW_SCENES + 1):
            frame[layout.GLOBAL_COLUMN, pad] = controls.scene_light(
                snapshot, state.window.scene, pad - 1, controls.waiting_scene(state)
            )
        frame[layout.LINNSTRUMENT_SCENES.back] = Light(WHITE)
        frame[normal.shift] = shift_held
        return frame
    if state.shift and not state.copy and not state.delete:
        # The normal layer's pads go dark under the Shift layer's.
        frame = {key: Light(OFF) for key in vars(normal).values()}
        launch_quantization = Light(GREEN if snapshot.launch_quantization != 0 else RED)
        frame[shift.quantize] = Light(MAGENTA)
        frame[shift.launch_quantization] = launch_quantization
        frame[shift.redo] = Light(WHITE)
        if state.mode is Mode.SESSION:
            frame[shift.stop_all] = Light(RED)
        else:
            frame[shift.stop_track] = Light(RED)
            frame[shift.record] = controls.record_light(snapshot)
            frame[shift.scene_page] = Light(PINK)
    else:
        frame = {
            normal.play_stop: controls.play_light(snapshot),
            normal.metronome: controls.metronome_light(snapshot),
            normal.fixed_length: Light(FIXED_LENGTH_COLOURS[state.fixed_length]),
            normal.undo: Light(WHITE),
        }
        if state.mode is Mode.SESSION:
            frame[normal.record] = controls.record_light(snapshot)
            frame[normal.capture] = Light(LIME)
            frame[normal.linnstrument_mode] = Light(MAGENTA)
        else:
            frame[normal.record_clip] = Light(RED)
            frame[normal.capture_midi] = Light(LIME)
            frame[normal.back if state.mode is Mode.LINNSTRUMENT else normal.linnstrument_mode] = Light(MAGENTA)
    frame[normal.shift] = shift_held
    return frame
