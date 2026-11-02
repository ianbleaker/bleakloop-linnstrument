"""The Global column: the control column, the same in every mode, and Linnstrument Mode's scene page.

In Linnstrument and Sequencer Mode the player is on the selected track, so Record, Capture
and Shift + Play/Stop act on it.
"""

from dataclasses import replace

from . import buttons, catalogue, controls, faders, functions, fx, layout, mixer, modes
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
    normal, shift = layers(state)
    if key in _shift_pads(normal):
        return replace(state, shift=event.pressed), shift_message(event)
    if not event.pressed:
        return state, []
    # Pads the layer has no button on do nothing.
    button = (shift if state.shift else normal).at(key)
    if button is None:
        return state, []
    return functions.press(button, state, snapshot)


functions.register_hold(
    "shift", light=lambda state, snapshot, value: Light(WHITE, Blink.FAST if state.shift else Blink.STEADY)
)


def _lit(colour):
    return lambda state, snapshot, value: Light(colour)


@functions.register("play_stop", light=lambda state, snapshot, value: controls.play_light(snapshot))
def _play_stop(state, snapshot, value):
    return state, [TogglePlay(), *buttons.say("play_stop", "stop" if snapshot.is_playing else "play")]


@functions.register("record", light=lambda state, snapshot, value: controls.record_light(snapshot))
def _record(state, snapshot, value):
    return state, controls.record(snapshot) + controls.record_message(snapshot)


@functions.register("capture", light=_lit(LIME))
def _capture(state, snapshot, value):
    return state, [CaptureAndInsertScene(), *buttons.say("capture")]


@functions.register("record_clip", light=_lit(RED))
def _record_clip_press(state, snapshot, value):
    return state, _record_clip(state, snapshot)


@functions.register("capture_midi", light=_lit(LIME))
def _capture_midi_press(state, snapshot, value):
    return state, _capture_midi(snapshot)


@functions.register("metronome", light=lambda state, snapshot, value: controls.metronome_light(snapshot))
def _metronome(state, snapshot, value):
    return state, controls.metronome(snapshot)


@functions.register(
    "fixed_length", light=lambda state, snapshot, value: Light(FIXED_LENGTH_COLOURS[state.fixed_length])
)
def _fixed_length_press(state, snapshot, value):
    return _fixed_length(state)


@functions.register("undo", light=_lit(WHITE))
def _undo(state, snapshot, value):
    return state, controls.undo(snapshot)


@functions.register("redo", light=_lit(WHITE))
def _redo(state, snapshot, value):
    return state, controls.redo(snapshot)


@functions.register("back", light=_lit(MAGENTA))
def _back_press(state, snapshot, value):
    return _back(state)


@functions.register("linnstrument_mode", [catalogue.SEQUENCER], light=_lit(MAGENTA))
def _linnstrument_from_sequencer(state, snapshot, value):
    # The arm stays: the player plays the track they were sequencing.
    actions = []
    if state.seq_undo_open:
        state = replace(state, seq_undo_open=False)
        actions.append(EndUndoStep())
    actions += [EnterMode(Mode.LINNSTRUMENT), *buttons.say("linnstrument_mode")]
    return modes.enter(state, Mode.LINNSTRUMENT), actions


@functions.register("linnstrument_mode", [catalogue.SESSION], light=_lit(MAGENTA))
def _linnstrument_from_session(state, snapshot, value):
    state, actions = mixer.reset(state)
    state, more = faders.reset(state)
    entered = [EnterMode(Mode.LINNSTRUMENT), *buttons.say("linnstrument_mode")]
    return modes.enter(state, Mode.LINNSTRUMENT), actions + more + entered


@functions.register("stop_all", light=_lit(RED))
def _stop_all(state, snapshot, value):
    return state, [StopAllClips(), *buttons.say("stop_all")]


@functions.register("stop_track", light=_lit(RED))
def _stop_track_press(state, snapshot, value):
    return state, _stop_track(snapshot)


@functions.register("quantize", light=_lit(MAGENTA))
def _quantize_press(state, snapshot, value):
    return state, _quantize(snapshot)


@functions.register(
    "launch_quantization",
    light=lambda state, snapshot, value: Light(GREEN if snapshot.launch_quantization != 0 else RED),
)
def _launch_quantization_press(state, snapshot, value):
    return _launch_quantization(state, snapshot)


@functions.register("scene_page", light=_lit(PINK))
def _scene_page_press(state, snapshot, value):
    return replace(state, scene_page=True), buttons.say("scene_page")


@functions.register("close_scenes", light=_lit(WHITE))
def _close_scenes(state, snapshot, value):
    return replace(state, scene_page=False), buttons.say("close_scenes")


def _back(state):
    # Back to the layer Linnstrument Mode was entered from, through its own entry path.
    if state.came_from is Origin.SEQUENCER:
        back = buttons.say("back", "sequencer")
        return modes.enter(state, Mode.SEQUENCER), [EnterMode(Mode.SEQUENCER), *back]
    state = modes.enter(state, Mode.SESSION)
    actions = [EnterMode(Mode.SESSION)]
    if state.came_from is Origin.MIXER:
        state, more = mixer.toggle(state)
        back = buttons.say("back", "mixer")
    elif state.came_from is Origin.FX:
        state, more = fx.toggle(state)
        back = buttons.say("back", "fx")
    else:
        more, back = [], buttons.say("back", "session")
    return state, actions + more + back


def _scene_page(state, key, pressed, snapshot):
    # Opened while Shift is held: that hold's release mustn't close it, Back's press does.
    shift = _shift_pads(layers(state)[0])
    if not pressed:
        if key in shift:
            return replace(state, shift=False), []
        return state, []
    button = layout.LINNSTRUMENT_SCENES.at(key)
    if button is not None:
        return functions.press(button, state, snapshot)
    if key[0] != layout.GLOBAL_COLUMN or key in shift:
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
        return replace(state, fixed_length=None), buttons.say("fixed_length", "off")
    unit = "bars" if bars > 1 else "bar"
    return replace(state, fixed_length=bars), buttons.say("fixed_length", bars=bars, unit=unit)


def _stop_track(snapshot):
    track = snapshot.selected_track
    if track is None:
        return buttons.refuse("stop_track", "no_track")
    return [StopTrackClips(track.index), *buttons.say("stop_track", track=track.name)]


def _record_clip(state, snapshot):
    track = snapshot.selected_track
    if track is None:
        return buttons.refuse("record_clip", "no_track")
    if track.is_foldable:
        return buttons.refuse("record_clip", "group_track")
    if not track.armed:
        return buttons.refuse("record_clip", "not_armed")
    length = controls.record_length(state.fixed_length, snapshot)
    # From the highlighted scene down, then wrapping to the top.
    count = snapshot.scene_count
    for step in range(count):
        scene = (snapshot.selected_scene + step) % count
        if not track.clips[scene]:
            return [
                FireSlot(track.index, scene, legato=False, record_length=length),
                ShowClip(track.index, scene),
                *buttons.say("record_clip"),
            ]
    # No empty slot: the new scene is added at the end, so it takes the next index.
    return [
        AddScene(),
        FireSlot(track.index, count, legato=False, record_length=length),
        ShowClip(track.index, count),
        *buttons.say("record_clip", "new_scene"),
    ]


def _capture_midi(snapshot):
    if not snapshot.can_capture_midi:
        return buttons.refuse("capture_midi", "nothing")
    return [CaptureMidi(), *buttons.say("capture_midi")]


def _quantize(snapshot):
    candidates = [
        (ClipTarget.HIGHLIGHTED, snapshot.highlighted_clip),
        (ClipTarget.DETAIL, snapshot.detail_clip),
        (ClipTarget.PLAYING, snapshot.playing_clip),
    ]
    found = [(target, clip) for target, clip in candidates if clip is not None]
    if not found:
        return buttons.refuse("quantize", "no_clip")
    target, clip = found[0]
    if not clip.is_midi:
        return buttons.refuse("quantize", "audio")
    return [QuantizeClip(target), *buttons.say("quantize")]


def _launch_quantization(state, snapshot):
    if snapshot.launch_quantization != 0:
        state = replace(state, quantization_memory=snapshot.launch_quantization)
        return state, [SetLaunchQuantization(0), *buttons.say("launch_quantization", name="None")]
    value = state.quantization_memory
    if value is None:
        value = DEFAULT_QUANTIZATION
    return state, [
        SetLaunchQuantization(value),
        *buttons.say("launch_quantization", name=QUANTIZATION_NAMES[value]),
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
        for button in layout.LINNSTRUMENT_SCENES.buttons():
            frame[button[2]] = functions.light(button, state, snapshot)
        frame.update(dict.fromkeys(_shift_pads(normal), shift_held))
        return frame
    # Every pad the column's layers use goes dark, then the live layer lights its own.
    frame = {button[2]: Light(OFF) for button in normal.buttons() + shift.buttons()}
    live = shift if state.shift and not state.copy and not state.delete else normal
    for button in live.buttons():
        frame[button[2]] = functions.light(button, state, snapshot)
    frame.update(dict.fromkeys(_shift_pads(normal), shift_held))
    return frame


def shift_message(event):
    return buttons.say("shift") if event.pressed else []


def _shift_pads(section):
    # Shift lights and works on both layers.
    return {button[2] for button in section.buttons() if button[1] == "shift"}
