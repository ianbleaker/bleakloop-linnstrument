"""handle() and render(): all behaviour, no side effects."""

from . import mixer, linnstrument_mode, session
from .modes import Mode


def handle(state, event, snapshot):
    if state.mode is Mode.SESSION:
        return session.handle(state, event, snapshot)
    return linnstrument_mode.handle(state, event, snapshot)


def y_axis(state, event):
    # A Y report only moves a glide target: no snapshot, no actions and nothing to redraw.
    if state.mode is not Mode.SESSION:
        return state
    return mixer.y_axis(state, event)


def tick(state, now_ms):
    # The fader glide on the 10 ms timer: no snapshot, and a redraw flag.
    if not state.glides and not state.lifts:
        return state, [], False
    return mixer.tick(state, now_ms)


def render(state, snapshot):
    if state.mode is Mode.SESSION:
        return session.render(state, snapshot)
    return linnstrument_mode.render(state, snapshot)


def blink_beats(snapshot, now_ms):
    # Follow the song while playing, otherwise pulse at the Set's tempo.
    if snapshot.is_playing:
        return snapshot.song_beats
    return now_ms / 1000 * snapshot.tempo / 60
