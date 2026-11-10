"""Behaviour shared by Session and Linnstrument Mode: undo, metronome, Play/Stop, record, Fixed Length
and scene lights; shared by Session and Sequencer Mode: the window moves, the tempo steps and the
Device/Clip hold and its Track and Device steps."""

from dataclasses import replace

from . import buttons, faders, functions, layout
from .modes import Mode
from .leds import BLUE, GREEN, LIME, MAGENTA, OFF, ORANGE, RED, WHITE, YELLOW, Blink, Light
from .model import (
    ClearBackToArrangement,
    Redo,
    SetArrangementRecord,
    SetSessionRecord,
    SetTempo,
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
        *buttons.say("metronome", "off" if snapshot.metronome else "on"),
    ]


def undo(snapshot):
    if snapshot.can_undo:
        return [Undo(), *buttons.say("undo")]
    return buttons.refuse("undo", "nothing")


def redo(snapshot):
    if snapshot.can_redo:
        return [Redo(), *buttons.say("redo")]
    return buttons.refuse("redo", "nothing")


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
    message = buttons.say(
        "window",
        first_track=window.track + 1,
        last_track=last_track,
        first_scene=window.scene + 1,
        last_scene=last_scene,
    )
    return replace(state, window=window), message


def tempo_step(snapshot, step):
    # Shift + column 16 pads 7 and 8.
    bpm = min(TEMPO_MAX, max(TEMPO_MIN, snapshot.tempo + step))
    return [SetTempo(bpm), *buttons.say("tempo", bpm=bpm)]


@functions.register("tempo", light=lambda state, snapshot, value: Light(GREEN))
def _tempo(state, snapshot, step):
    return state, tempo_step(snapshot, step)


@functions.register(
    "unmute_all", light=lambda state, snapshot, value: Light(ORANGE if snapshot.any_muted else OFF)
)
def unmute_all(state, snapshot, value=None):
    return state, [UnmuteAll(), *buttons.say("unmute_all")]


@functions.register(
    "unsolo_all", light=lambda state, snapshot, value: Light(BLUE if snapshot.any_soloed else OFF)
)
def unsolo_all(state, snapshot, value=None):
    return state, [UnsoloAll(), *buttons.say("unsolo_all")]


@functions.register(
    "unarm_all", light=lambda state, snapshot, value: Light(RED if snapshot.any_armed else OFF)
)
def unarm_all(state, snapshot, value=None):
    return state, [UnarmAll(), *buttons.say("unarm_all")]


@functions.register("window", light=lambda state, snapshot, value: Light(YELLOW))
def _window(state, snapshot, steps):
    return move_window(state, steps, snapshot)


@functions.register("fader_source", light=lambda state, snapshot, value: Light(ORANGE))
def _fader_source(state, snapshot, value):
    return toggle_fader_source(state)




def device_clip(state, event, snapshot):
    # A hold pad: held, the Device/Clip layer; a tap with no other press during it flips
    # Live's Detail view, and names the view it flips to.
    if event.pressed:
        return replace(state, device_clip=True, device_clip_used=False), buttons.say("device_clip")
    tapped = state.device_clip and not state.device_clip_used
    state = replace(state, device_clip=False, device_clip_used=False)
    if not tapped:
        return state, []
    return state, [ToggleDetailView(), *buttons.say("device_clip", "device" if snapshot.clip_view else "clip")]


functions.register_hold(
    "device_clip",
    light=lambda state, snapshot, value: Light(ORANGE, Blink.FAST if state.device_clip else Blink.STEADY),
    handle=device_clip,
    down=lambda state: state.device_clip,
    layer="device_clip",
    takes=True,
)


@functions.register("tracks", light=lambda state, snapshot, step: Light(LIME))
def _track_step(state, snapshot, step):
    return state, [StepTrack(step)]


@functions.register("devices", light=lambda state, snapshot, step: Light(MAGENTA))
def _device_step(state, snapshot, step):
    return state, [StepDevice(step)]


def toggle_fader_source(state):
    # Shift + FX: the Session and Mixer split views' panel, Device FX <-> the snapshots. FX and
    # Sequencer Mode have no panel.
    if state.fx or state.mode is not Mode.SESSION:
        return state, []
    # The layer under a held fader or slot changes: it lets go.
    state, actions = faders.reset(state)
    if state.split_snapshots:
        state = replace(state, split_snapshots=False, fx_length=None)
        return state, actions + buttons.say("fader_source", "device")
    return replace(state, split_snapshots=True), actions + buttons.say("fader_source", "snapshots")


def record_length(bars, snapshot):
    # A bar is the current time signature's bar, in beats (quarter notes).
    if bars is None:
        return None
    return bars * snapshot.bar_beats


def record(snapshot):
    if snapshot.session_view:
        return [SetSessionRecord(not snapshot.session_record)]
    actions = [ClearBackToArrangement()] if snapshot.back_to_arranger else []
    return actions + [SetArrangementRecord(not snapshot.arrangement_record)]


def record_message(snapshot):
    # What record() just turned on or off.
    if snapshot.session_view:
        return buttons.say("record", "session_off" if snapshot.session_record else "session_on")
    return buttons.say("record", "arrangement_off" if snapshot.arrangement_record else "arrangement_on")


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
