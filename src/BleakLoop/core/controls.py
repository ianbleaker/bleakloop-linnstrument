"""Behaviour shared by Session and Linnstrument Mode: undo, metronome, Play/Stop, record, Fixed Length
and scene lights; shared by Session and Sequencer Mode: the window moves, the tempo steps and the
Device/Clip layer."""

from dataclasses import replace

from . import faders, functions, layout
from .modes import Mode
from .leds import BLUE, GREEN, LIME, MAGENTA, OFF, ORANGE, RED, WHITE, YELLOW, Blink, Light
from .model import (
    ClearBackToArrangement,
    Redo,
    SetArrangementRecord,
    SetSessionRecord,
    SetTempo,
    ShowMessage,
    StepDevice,
    StepTrack,
    ToggleDetailView,
    ToggleMetronome,
    UnarmAll,
    Undo,
    UnmuteAll,
    UnsoloAll,
)
from .values import TEMPO_MAX, TEMPO_MIN


def metronome_light(snapshot):
    return Light(ORANGE, Blink.FAST if snapshot.metronome else Blink.STEADY)


def play_light(snapshot):
    return Light(GREEN, Blink.TEMPO) if snapshot.is_playing else Light(BLUE)


def metronome(snapshot):
    return [
        ToggleMetronome(),
        ShowMessage("Metronome OFF" if snapshot.metronome else "Metronome ON"),
    ]


def undo(snapshot):
    if snapshot.can_undo:
        return [Undo(), ShowMessage("Undo")]
    return [ShowMessage("Nothing to undo")]


def redo(snapshot):
    if snapshot.can_redo:
        return [Redo(), ShowMessage("Redo")]
    return [ShowMessage("Nothing to redo")]


def window_tracks(state):
    # The split views show 8 tracks, FX Mode always 13. Sequencer Mode keeps Session's
    # split view width, as the ring does.
    return layout.SPLIT_TRACKS if faders.split_view(state) else layout.WINDOW_TRACKS


def move_window(state, steps, snapshot):
    # Shift + column 16 pads 1-4, in Session, Mixer, FX and Sequencer Mode.
    width = window_tracks(state)
    window = layout.move_window(
        state.window, *steps, snapshot.track_count, snapshot.scene_count, width
    )
    if window == state.window:
        return state, []
    last_track = min(window.track + width, snapshot.track_count)
    last_scene = min(window.scene + layout.WINDOW_SCENES, snapshot.scene_count)
    message = (
        f"Tracks {window.track + 1}–{last_track}, "
        f"Scenes {window.scene + 1}–{last_scene}"
    )
    return replace(state, window=window), [ShowMessage(message)]


def tempo_step(snapshot, step):
    # Shift + column 16 pads 7 and 8.
    bpm = min(TEMPO_MAX, max(TEMPO_MIN, snapshot.tempo + step))
    return [SetTempo(bpm), ShowMessage(f"Tempo {bpm:.1f} BPM")]


@functions.register("tempo", light=lambda state, snapshot, value: Light(GREEN))
def _tempo(state, snapshot, step):
    return state, tempo_step(snapshot, step)


@functions.register(
    "unmute_all", light=lambda state, snapshot, value: Light(ORANGE if snapshot.any_muted else OFF)
)
def unmute_all(state, snapshot, value=None):
    return state, [UnmuteAll(), ShowMessage("Unmute all")]


@functions.register(
    "unsolo_all", light=lambda state, snapshot, value: Light(BLUE if snapshot.any_soloed else OFF)
)
def unsolo_all(state, snapshot, value=None):
    return state, [UnsoloAll(), ShowMessage("Unsolo all")]


@functions.register(
    "unarm_all", light=lambda state, snapshot, value: Light(RED if snapshot.any_armed else OFF)
)
def unarm_all(state, snapshot, value=None):
    return state, [UnarmAll(), ShowMessage("Unarm all")]


@functions.register("window", light=lambda state, snapshot, value: Light(YELLOW))
def _window(state, snapshot, steps):
    return move_window(state, steps, snapshot)


@functions.register("fader_source", light=lambda state, snapshot, value: Light(ORANGE))
def _fader_source(state, snapshot, value):
    return toggle_fader_source(state)


functions.register_hold("device_clip", light=lambda state, snapshot, value: Light(ORANGE))


def sections(state, shift=False):
    # The mode's button sections, normal or Shift layer, in lookup order. Fixed regions and
    # Device/Clip's layer aren't sections here.
    if state.mode is Mode.LINNSTRUMENT:
        return (layout.LINNSTRUMENT_SHIFT,) if shift else (layout.LINNSTRUMENT,)
    if state.mode is Mode.SEQUENCER:
        if shift:
            return (layout.SEQUENCER_GLOBAL_SHIFT, layout.SEQUENCER_NAV_SHIFT)
        return (layout.SEQUENCER_GLOBAL, layout.SEQUENCER_NAV)
    if shift:
        return (layout.GLOBAL_SHIFT, layout.VIEW_SHIFT, layout.NAVIGATION_SHIFT)
    return (layout.GLOBAL, layout.VIEW, layout.NAVIGATION)


def at(sections, key):
    # The button live on a pad in the first section that has one, or None.
    for section in sections:
        button = section.at(key)
        if button is not None:
            return button
    return None


def pads(state, name):
    # The pads of a function's buttons on the mode's normal layer.
    return {button[2] for section in sections(state) for button in section.buttons() if button[1] == name}


def device_clip(state, event):
    # A hold pad: held, the Device/Clip layer; a tap with no other press during it flips
    # Live's Detail view.
    if event.pressed:
        return replace(state, device_clip=True, device_clip_used=False), []
    tapped = state.device_clip and not state.device_clip_used
    state = replace(state, device_clip=False, device_clip_used=False)
    return state, [ToggleDetailView()] if tapped else []


def device_clip_layer(state, key):
    # Device/Clip held + a column 16 pad.
    if key in layout.DEVICE_CLIP.tracks:
        return state, [StepTrack(layout.DEVICE_CLIP.tracks[key])]
    if key in layout.DEVICE_CLIP.devices:
        return state, [StepDevice(layout.DEVICE_CLIP.devices[key])]
    return state, []


def toggle_fader_source(state):
    # Shift + FX: Device FX <-> Mapped FX. Session and Mixer Mode's split panel adds the
    # snapshots: Device FX -> Mapped FX -> FX snapshots -> Device FX.
    panel = state.mode is Mode.SESSION and not state.fx
    if state.split_snapshots and panel:
        state = replace(state, split_snapshots=False, fader_source="device", fx_length=None)
        return state, [ShowMessage("Device FX")]
    if state.fader_source == "mapped" and panel:
        # The faders stop showing.
        state, actions = faders.reset(state)
        return replace(state, split_snapshots=True), actions + [ShowMessage("FX snapshots")]
    mapped = state.fader_source == "device"
    state = replace(state, fader_source="mapped" if mapped else "device")
    return state, [ShowMessage("Mapped FX" if mapped else "Device FX")]


def render_device_clip_layer(frame, state):
    # Over either layer: the whole of column 16.
    for pad in range(1, layout.ROWS + 1):
        frame[(layout.NAV_COLUMN, pad)] = Light(OFF)
    for key in layout.DEVICE_CLIP.tracks:
        frame[key] = Light(LIME)
    for key in layout.DEVICE_CLIP.devices:
        frame[key] = Light(MAGENTA)
    frame.update(dict.fromkeys(pads(state, "device_clip"), Light(ORANGE, Blink.FAST)))


def record_length(bars, snapshot):
    # A bar is the current time signature's bar, in beats (quarter notes).
    if bars is None:
        return None
    return bars * snapshot.signature_numerator * 4 / snapshot.signature_denominator


def record(snapshot):
    if snapshot.session_view:
        return [SetSessionRecord(not snapshot.session_record)]
    actions = [ClearBackToArrangement()] if snapshot.back_to_arranger else []
    return actions + [SetArrangementRecord(not snapshot.arrangement_record)]


def record_light(snapshot):
    if snapshot.session_view:
        on = snapshot.session_record or snapshot.arrangement_overdub
        return Light(RED, Blink.TEMPO if on else Blink.STEADY)
    if snapshot.arrangement_record:
        return Light(RED, Blink.TEMPO)
    if snapshot.back_to_arranger:
        return Light(ORANGE, Blink.TEMPO)
    return Light(RED)


# A scene pad's light by the scene's state, first match wins; the manual's line is generated
# from this.
SCENE_LIGHTS = {
    # held back to a Bars pad's bar line; it blinks with the beat, as lime looks yellow on the
    # device
    "waiting": Light(YELLOW, Blink.TEMPO),
    "launching": Light(LIME, Blink.FAST),  # waiting for the quantization boundary
    "full": Light(LIME),  # every clip in the window's row plays
    "playing": Light(MAGENTA),  # some do
    "clips": Light(WHITE),
}


def waiting_scene(state):
    # The scene of a pending launch, for scene_light.
    pending = state.pending_launch
    return None if pending is None else pending.scene


def scene_light(snapshot, scene_offset, row, waiting=None):
    # The scene light without the copy-source state; row is the window row 0-5, waiting the
    # scene of a pending launch.
    if scene_offset + row >= snapshot.scene_count:
        return Light(OFF)
    if scene_offset + row == waiting:
        return SCENE_LIGHTS["waiting"]
    triggered = snapshot.scene_triggered
    if row < len(triggered) and triggered[row]:
        return SCENE_LIGHTS["launching"]
    slots = [track.slots[row] for track in snapshot.tracks if len(track.slots) > row]
    clips = [slot for slot in slots if slot.has_clip]
    if not clips:
        return Light(OFF)
    playing = sum(slot.is_playing for slot in clips)
    if playing == len(clips):
        return SCENE_LIGHTS["full"]
    return SCENE_LIGHTS["playing" if playing else "clips"]
