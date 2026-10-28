"""Behaviour shared by Session and Linnstrument Mode: undo, metronome, Play/Stop, record, Fixed Length
and scene lights; shared by Session and Sequencer Mode: the window moves, the tempo steps and the
Device/Clip layer."""

from dataclasses import replace

from . import layout
from .leds import BLUE, GREEN, LIME, MAGENTA, OFF, ORANGE, RED, WHITE, Blink, Light
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
    Undo,
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
    # The split view shows 8 tracks; Mixer and FX Mode always 13. Sequencer Mode keeps the
    # split view's width, as the ring does.
    if state.split and not state.mixer and not state.fx:
        return layout.SPLIT_TRACKS
    return layout.WINDOW_TRACKS


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
    if key in layout.DEVICE_CLIP_TRACK_STEPS:
        return state, [StepTrack(layout.DEVICE_CLIP_TRACK_STEPS[key])]
    if key in layout.DEVICE_CLIP_DEVICE_STEPS:
        return state, [StepDevice(layout.DEVICE_CLIP_DEVICE_STEPS[key])]
    return state, []


def toggle_fader_source(state):
    # Shift + FX: Device FX <-> Mapped FX.
    mapped = state.fader_source == "device"
    state = replace(state, fader_source="mapped" if mapped else "device")
    return state, [ShowMessage("Mapped FX" if mapped else "Device FX")]


def render_device_clip_layer(frame):
    # Over either layer: the whole of column 16.
    for pad in range(1, layout.ROWS + 1):
        frame[(layout.NAV_COLUMN, pad)] = Light(OFF)
    for key in layout.DEVICE_CLIP_TRACK_STEPS:
        frame[key] = Light(LIME)
    for key in layout.DEVICE_CLIP_DEVICE_STEPS:
        frame[key] = Light(MAGENTA)
    frame[layout.DEVICE_CLIP] = Light(ORANGE, Blink.FAST)


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


def scene_light(snapshot, scene_offset, row):
    # The scene light without the copy-source state; row is the window row 0-5.
    if scene_offset + row >= snapshot.scene_count:
        return Light(OFF)
    triggered = snapshot.scene_triggered
    if row < len(triggered) and triggered[row]:
        # Launched, waiting for the quantization boundary: steady, unlike a playing scene.
        return Light(LIME)
    slots = [track.slots[row] for track in snapshot.tracks if len(track.slots) > row]
    if any(slot.is_playing for slot in slots):
        return Light(LIME, Blink.TEMPO)
    if any(slot.has_clip for slot in slots):
        return Light(WHITE)
    return Light(OFF)
