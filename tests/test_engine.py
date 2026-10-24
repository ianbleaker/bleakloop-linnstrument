import pytest

from BleakLoop.core import engine, layout
from BleakLoop.core.leds import BLUE, GREEN, OFF, ORANGE, WHITE, Blink, Light
from BleakLoop.core.model import (
    ControlCC,
    EnterMode,
    PadPress,
    Snapshot,
    ToggleMetronome,
    TogglePlay,
)
from BleakLoop.core.modes import Mode, State

STOPPED = Snapshot(
    is_playing=False, song_beats=3.25, tempo=120.0, metronome=False, session_view=True
)
PLAYING = Snapshot(
    is_playing=True, song_beats=3.25, tempo=120.0, metronome=True, session_view=True
)

SESSION = State(Mode.SESSION)
NOTE = State(Mode.NOTE)


def press(key, pressed=True):
    return PadPress(column=key[0], pad=key[1], pressed=pressed)


# Session Mode input


def test_default_state_is_session():
    assert State().mode is Mode.SESSION


def test_mode_pad_enters_note():
    state, actions = engine.handle(SESSION, press(layout.MODE_PAD), STOPPED)
    assert state.mode is Mode.NOTE
    assert actions == [EnterMode(Mode.NOTE)]


def test_metronome_pad():
    assert engine.handle(SESSION, press(layout.METRONOME), STOPPED) == (
        SESSION,
        [ToggleMetronome()],
    )


def test_play_stop_pad():
    assert engine.handle(SESSION, press(layout.PLAY_STOP), STOPPED) == (
        SESSION,
        [TogglePlay()],
    )


@pytest.mark.parametrize("key", [layout.MODE_PAD, layout.METRONOME, layout.PLAY_STOP])
def test_session_release_does_nothing(key):
    assert engine.handle(SESSION, press(key, pressed=False), STOPPED) == (SESSION, [])


@pytest.mark.parametrize("pad", range(1, 9))
def test_column_0_does_nothing(pad):
    assert engine.handle(SESSION, press((0, pad)), STOPPED) == (SESSION, [])


@pytest.mark.parametrize("key", [(1, 1), (1, 7), (2, 1), (8, 8), (16, 8)])
def test_other_pads_do_nothing(key):
    assert engine.handle(SESSION, press(key), STOPPED) == (SESSION, [])


@pytest.mark.parametrize("cc", range(1, 9))
def test_session_ignores_control_cc(cc):
    assert engine.handle(SESSION, ControlCC(cc, 127), STOPPED) == (SESSION, [])


# Note Mode input


@pytest.mark.parametrize("value", [127, 0])
def test_cc1_any_value_enters_session(value):
    state, actions = engine.handle(NOTE, ControlCC(1, value), STOPPED)
    assert state.mode is Mode.SESSION
    assert actions == [EnterMode(Mode.SESSION)]


@pytest.mark.parametrize("cc", range(2, 9))
@pytest.mark.parametrize("value", [127, 0])
def test_other_ccs_do_nothing(cc, value):
    assert engine.handle(NOTE, ControlCC(cc, value), STOPPED) == (NOTE, [])


@pytest.mark.parametrize("key", [layout.MODE_PAD, layout.METRONOME, (5, 5)])
def test_note_ignores_pads(key):
    assert engine.handle(NOTE, press(key), STOPPED) == (NOTE, [])


# Rendering


def test_session_frame_keys():
    frame = engine.render(SESSION, STOPPED)
    assert set(frame) == {(c, p) for c in range(1, 17) for p in range(1, 9)}


def test_session_frame_stopped():
    frame = engine.render(SESSION, STOPPED)
    assert frame[layout.METRONOME] == Light(ORANGE)
    assert frame[layout.PLAY_STOP] == Light(BLUE)
    assert frame[layout.MODE_PAD] == Light(WHITE)
    lit = {layout.METRONOME, layout.PLAY_STOP, layout.MODE_PAD}
    assert all(light == Light(OFF) for key, light in frame.items() if key not in lit)


def test_session_frame_playing_with_metronome():
    frame = engine.render(SESSION, PLAYING)
    assert frame[layout.METRONOME] == Light(ORANGE, Blink.FAST)
    assert frame[layout.PLAY_STOP] == Light(GREEN, Blink.TEMPO)


def test_note_frame():
    frame = engine.render(NOTE, PLAYING)
    assert set(frame) == {(1, p) for p in range(1, 9)}
    assert frame[(1, 8)] == Light(WHITE)
    assert all(frame[(1, p)] == Light(OFF) for p in range(1, 8))


# Blink clock


def test_blink_beats_follows_song_while_playing():
    assert engine.blink_beats(PLAYING, now_ms=12345) == 3.25


def test_blink_beats_uses_tempo_while_stopped():
    # 120 BPM: two beats per second.
    assert engine.blink_beats(STOPPED, now_ms=1500) == 3.0
