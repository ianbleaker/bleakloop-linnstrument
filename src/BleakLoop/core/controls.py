"""Behaviour shared by Session and Linnstrument Mode: undo, metronome, Play/Stop, record, Fixed Length
and scene lights."""

from .leds import BLUE, GREEN, LIME, OFF, ORANGE, RED, WHITE, Blink, Light
from .model import (
    ClearBackToArrangement,
    Redo,
    SetArrangementRecord,
    SetSessionRecord,
    ShowMessage,
    ToggleMetronome,
    Undo,
)


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
