"""handle() and render(): all behaviour, no side effects."""

from . import layout, modes, session
from .leds import OFF, WHITE, Light
from .model import ControlCC, EnterMode
from .modes import Mode

# Note Mode column 1 CC numbers (spec section 2, Note Mode layout).
SESSION_MODE_CC = 1


def handle(state, event, snapshot):
    if state.mode is Mode.SESSION:
        return session.handle(state, event, snapshot)
    return _handle_note(state, event)


def _handle_note(state, event):
    # Any value is a press: column 1 pads are toggles and send nothing on release (S-76).
    if not isinstance(event, ControlCC):
        return state, []
    if event.cc == SESSION_MODE_CC:
        return modes.enter(state, Mode.SESSION), [EnterMode(Mode.SESSION)]  # S-85
    return state, []


def render(state, snapshot):
    if state.mode is Mode.SESSION:
        return session.render(state, snapshot)
    return _render_note()


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
