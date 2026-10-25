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
NOTE = State(Mode.NOTE)


def press(key, pressed=True):
    return PadPress(column=key[0], pad=key[1], pressed=pressed)


# Session Mode input


def test_default_state_is_session():
    assert State().mode is Mode.SESSION


def test_session_input_goes_to_session_module():
    state, actions = engine.handle(SESSION, press(layout.MODE_PAD), STOPPED)
    assert state.mode is Mode.NOTE
    assert actions == [EnterMode(Mode.NOTE)]


# Note Mode input


def test_pad_8_press_enters_session():
    state, actions = engine.handle(NOTE, PadPress(1, 8, True), STOPPED)
    assert state == State(mode=Mode.SESSION)
    assert actions == [EnterMode(Mode.SESSION)]


def test_pad_8_release_is_ignored():
    assert engine.handle(NOTE, PadPress(1, 8, False), STOPPED) == (NOTE, [])


def test_note_input_goes_to_note_module():
    state, actions = engine.handle(NOTE, PadPress(1, 4, True), STOPPED)
    assert state.scene_page
    assert actions == []


@pytest.mark.parametrize("key", [(2, 8), (5, 5), layout.SHIFT])
def test_note_ignores_pads_outside_column_1(key):
    assert engine.handle(NOTE, press(key), STOPPED) == (NOTE, [])


# Rendering


def test_session_render_goes_to_session_module():
    assert set(engine.render(SESSION, STOPPED)) == {
        (c, p) for c in range(1, 17) for p in range(1, 9)
    }


def test_note_render_goes_to_note_module():
    assert set(engine.render(NOTE, PLAYING)) == {(1, p) for p in range(1, 9)}


# Blink clock


def test_blink_beats_follows_song_while_playing():
    assert engine.blink_beats(PLAYING, now_ms=12345) == 3.25


def test_blink_beats_uses_tempo_while_stopped():
    # 120 BPM: two beats per second.
    assert engine.blink_beats(STOPPED, now_ms=1500) == 3.0
