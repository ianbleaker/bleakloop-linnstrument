"""handle() and render(): all behaviour, no side effects."""

from . import faders, fx, mixer, linnstrument_mode, session
from .model import FaderBound, PadPress, RacksRead
from .modes import Mode


def handle(state, event, snapshot):
    if isinstance(event, RacksRead):
        # A morph runs in every mode.
        return fx.racks_read(state, event, snapshot)
    if isinstance(event, FaderBound):
        return faders.bound(state, event)
    if state.mode is Mode.SESSION:
        return session.handle(state, event, snapshot)
    return linnstrument_mode.handle(state, event, snapshot)


def y_axis(state, event):
    # A Y report only moves a glide target: no snapshot, no actions and nothing to redraw.
    if state.mode is not Mode.SESSION:
        return state
    return mixer.y_axis(state, event)


def x_rows(state):
    # The device rows that want X and slide mode: every row while the faders show.
    return tuple(range(8)) if faders.visible(state) else ()


def x_axis(state, event):
    # An X report: no snapshot, and a redraw flag.
    if state.mode is not Mode.SESSION:
        return state, [], False
    return faders.x_axis(state, event)


def slide(state, event, snapshot):
    # A slide no fader owns releases the pad it left.
    state, owned = faders.slide(state, event)
    if owned:
        return state, []
    return handle(state, PadPress(event.from_column, event.pad, False), snapshot)


def tick(state, now_ms):
    # The fader glide on the 10 ms timer: no snapshot, and a redraw flag.
    if not state.glides and not state.lifts and not state.dead:
        return state, [], False
    return mixer.tick(state, now_ms)


def fx_tick(state, transport, values):
    # The morph on the 10 ms timer, in every mode: values per morphing macro, and a redraw flag.
    if state.morph is None:
        return state, [], False
    return fx.tick(state, transport, values)


def render(state, snapshot):
    if state.mode is Mode.SESSION:
        return session.render(state, snapshot)
    return linnstrument_mode.render(state, snapshot)


def blink_beats(snapshot, now_ms):
    # Follow the song while playing, otherwise pulse at the Set's tempo.
    if snapshot.is_playing:
        return snapshot.song_beats
    return now_ms / 1000 * snapshot.tempo / 60
