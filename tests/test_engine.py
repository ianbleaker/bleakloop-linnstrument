import pytest

from BleakLoop.core import engine, layout
from BleakLoop.core.model import EnterMode, PadPress, Snapshot
from BleakLoop.core.modes import Mode, State

STOPPED = Snapshot(
    is_playing=False, song_beats=3.25, tempo=120.0, metronome=False, session_view=True
)
PLAYING = Snapshot(
    is_playing=True, song_beats=3.25, tempo=120.0, metronome=True, session_view=True
)

SESSION = State(Mode.SESSION)
LINNSTRUMENT = State(Mode.LINNSTRUMENT)


def press(key, pressed=True):
    return PadPress(column=key[0], pad=key[1], pressed=pressed)


# Session Mode input


def test_default_state_is_session():
    assert State().mode is Mode.SESSION


def test_session_input_goes_to_session_module():
    state, actions = engine.handle(SESSION, press(layout.MODE_PAD), STOPPED)
    assert state.mode is Mode.LINNSTRUMENT
    assert actions == [EnterMode(Mode.LINNSTRUMENT)]


# Linnstrument Mode input


def test_mode_pad_press_enters_session():
    state, actions = engine.handle(LINNSTRUMENT, press(layout.MODE_PAD), STOPPED)
    assert state == State(mode=Mode.SESSION)
    assert actions == [EnterMode(Mode.SESSION)]


def test_mode_pad_release_is_ignored():
    assert engine.handle(LINNSTRUMENT, press(layout.MODE_PAD, False), STOPPED) == (LINNSTRUMENT, [])


def test_linnstrument_input_goes_to_linnstrument_module():
    state, actions = engine.handle(LINNSTRUMENT, press(layout.SHIFT), STOPPED)
    assert state.shift
    assert actions == []


@pytest.mark.parametrize("key", [(2, 8), (5, 5), (16, 8)])
def test_linnstrument_ignores_pads_outside_column_1(key):
    assert engine.handle(LINNSTRUMENT, press(key), STOPPED) == (LINNSTRUMENT, [])


# Rendering


def test_session_render_goes_to_session_module():
    assert set(engine.render(SESSION, STOPPED)) == {
        (c, p) for c in range(1, 17) for p in range(1, 9)
    }


def test_linnstrument_render_goes_to_linnstrument_module():
    assert set(engine.render(LINNSTRUMENT, PLAYING)) == {(1, p) for p in range(1, 9)}


# Blink clock


def test_blink_beats_follows_song_while_playing():
    assert engine.blink_beats(PLAYING, now_ms=12345) == 3.25


def test_blink_beats_uses_tempo_while_stopped():
    # 120 BPM: two beats per second.
    assert engine.blink_beats(STOPPED, now_ms=1500) == 3.0
