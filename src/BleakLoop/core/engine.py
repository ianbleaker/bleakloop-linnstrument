"""handle() and render(): all behaviour, no side effects."""

from dataclasses import replace

from . import layout
from .leds import BLUE, GREEN, OFF, ORANGE, WHITE, Blink, Light
from .model import ControlCC, EnterMode, PadPress, ToggleMetronome, TogglePlay
from .modes import Mode

# Note Mode column 1 CC numbers (spec section 2, Note Mode layout).
SESSION_MODE_CC = 1


def handle(state, event, snapshot):
    if state.mode is Mode.SESSION:
        return _handle_session(state, event)
    return _handle_note(state, event)


def _handle_session(state, event):
    # Column 1 CCs are ignored in Session Mode (S-76).
    if not isinstance(event, PadPress) or not event.pressed:
        return state, []
    key = (event.column, event.pad)
    if key == layout.MODE_PAD:
        return replace(state, mode=Mode.NOTE), [EnterMode(Mode.NOTE)]  # S-56
    if key == layout.METRONOME:
        return state, [ToggleMetronome()]  # S-50
    if key == layout.PLAY_STOP:
        return state, [TogglePlay()]  # S-52
    return state, []


def _handle_note(state, event):
    # Any value is a press: column 1 pads are toggles and send nothing on release (S-76).
    if not isinstance(event, ControlCC):
        return state, []
    if event.cc == SESSION_MODE_CC:
        return replace(state, mode=Mode.SESSION), [EnterMode(Mode.SESSION)]  # S-85
    return state, []


def render(state, snapshot):
    if state.mode is Mode.SESSION:
        return _render_session(snapshot)
    return _render_note()


def _render_session(snapshot):
    frame = {
        (column, pad): Light(OFF)
        for column in range(1, layout.COLUMNS)
        for pad in range(1, layout.ROWS + 1)
    }
    frame[layout.METRONOME] = Light(
        ORANGE, Blink.FAST if snapshot.metronome else Blink.STEADY
    )  # S-50
    frame[layout.PLAY_STOP] = (
        Light(GREEN, Blink.TEMPO) if snapshot.is_playing else Light(BLUE)
    )  # S-52
    frame[layout.MODE_PAD] = Light(WHITE)  # S-56
    return frame


def _render_note():
    frame = {
        (column, pad): Light(OFF)
        for column in layout.NOTE_CONTROL_COLUMNS
        for pad in range(1, layout.ROWS + 1)
    }
    frame[layout.MODE_PAD] = Light(WHITE)  # S-85
    return frame


def blink_beats(snapshot, now_ms):
    # S-90: follow the song while playing, otherwise pulse at the Set's tempo.
    if snapshot.is_playing:
        return snapshot.song_beats
    return now_ms / 1000 * snapshot.tempo / 60
