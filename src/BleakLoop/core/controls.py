"""Behaviour shared by Session and Linnstrument Mode: undo, metronome, Play/Stop, record, Fixed Length
and scene lights; shared by Session and Sequencer Mode: the tempo steps and the Device/Clip layer."""

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


def tempo_step(snapshot, step):
    # Shift + column 16 pads 7 and 8.
    bpm = min(TEMPO_MAX, max(TEMPO_MIN, snapshot.tempo + step))
    return [SetTempo(bpm), ShowMessage(f"Tempo {bpm:.1f} BPM")]


def device_clip_layer(state, key):
    # Device/Clip held + a column 16 pad.
    if key in layout.DEVICE_CLIP_TRACK_STEPS:
        return state, [StepTrack(layout.DEVICE_CLIP_TRACK_STEPS[key])]
    if key in layout.DEVICE_CLIP_DEVICE_STEPS:
        return state, [StepDevice(layout.DEVICE_CLIP_DEVICE_STEPS[key])]
    if key == layout.DEVICE_CLIP_SOURCE:
        mapped = state.fader_source == "device"
        state = replace(state, fader_source="mapped" if mapped else "device")
        return state, [ShowMessage("Mapped FX" if mapped else "Device FX")]
    return state, []


def render_device_clip_layer(frame):
    # Over either layer: the whole of column 16.
    for pad in range(1, layout.ROWS + 1):
        frame[(layout.NAV_COLUMN, pad)] = Light(OFF)
    for key in layout.DEVICE_CLIP_TRACK_STEPS:
        frame[key] = Light(LIME)
    for key in layout.DEVICE_CLIP_DEVICE_STEPS:
        frame[key] = Light(MAGENTA)
    frame[layout.DEVICE_CLIP_SOURCE] = Light(ORANGE)
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
