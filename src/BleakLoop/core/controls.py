"""Behaviour shared by Session and Note Mode: undo, metronome, Play/Stop and scene lights."""

from .leds import BLUE, GREEN, LIME, OFF, ORANGE, WHITE, Blink, Light
from .model import Redo, ShowMessage, ToggleMetronome, Undo


def metronome_light(snapshot):
    return Light(ORANGE, Blink.FAST if snapshot.metronome else Blink.STEADY)  # S-50, S-81


def play_light(snapshot):
    return Light(GREEN, Blink.TEMPO) if snapshot.is_playing else Light(BLUE)  # S-52, S-83


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


def scene_light(snapshot, scene_offset, row):
    # S-68 without the copy-source state; row is the window row 0-6.
    if scene_offset + row >= snapshot.scene_count:
        return Light(OFF)
    slots = [track.slots[row] for track in snapshot.tracks if len(track.slots) > row]
    if any(slot.is_playing for slot in slots):
        return Light(LIME, Blink.TEMPO)
    if any(slot.has_clip for slot in slots):
        return Light(WHITE)
    return Light(OFF)
