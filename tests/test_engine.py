from dataclasses import replace

import pytest

from BleakLoop.core import engine, layout
from BleakLoop.core.model import (
    EnterMode,
    PadPress,
    SequencerView,
    SetArms,
    SlideMoved,
    Snapshot,
)
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


def test_unowned_slide_releases_the_pad_it_left():
    # Sliding off Stop ends the hold, as releasing it does.
    stopping = State(Mode.SESSION, stop=True)
    slide = SlideMoved(pad=layout.STOP[1], from_column=layout.STOP[0], to_column=16)
    assert engine.slide(stopping, slide, STOPPED) == engine.handle(
        stopping, press(layout.STOP, False), STOPPED
    )
    assert not engine.slide(stopping, slide, STOPPED)[0].stop


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


# Sequencer Mode

SEQUENCER = State(Mode.SEQUENCER, seq_track=0)


def test_sequencer_input_goes_to_the_sequencer_module():
    state, actions = engine.handle(SEQUENCER, press(layout.SEQ), STOPPED)
    assert state.mode is Mode.SESSION
    assert actions == [EnterMode(Mode.SESSION)]


def test_sequencer_renders_its_own_frame():
    frame = engine.render(SEQUENCER, STOPPED)
    assert frame[layout.SEQ] == engine.sequencer.render(SEQUENCER, STOPPED)[layout.SEQ]
    assert (layout.SEQ_VIEW) in frame


def test_seq_sync_runs_only_in_sequencer_mode():
    view = SequencerView(track=1, is_midi=True)
    snapshot = Snapshot(
        is_playing=False,
        song_beats=0.0,
        tempo=120.0,
        metronome=False,
        session_view=True,
        arms=(True, False),
        sequencer=view,
    )
    assert engine.seq_sync(SESSION, snapshot) == (SESSION, [])
    state, actions = engine.seq_sync(SEQUENCER, snapshot)
    assert state.seq_track == 1
    assert actions == [SetArms(((0, False), (1, True)))]


def test_seq_phase_is_the_playhead():
    view = SequencerView(is_playing=True, position=1.0)
    assert engine.seq_phase(SEQUENCER, view) == 4
    assert engine.seq_phase(SEQUENCER, SequencerView()) is None


def test_sequencer_x_rows_are_its_held_rows():
    view = SequencerView(track=0, is_midi=True, has_clip=True, loop_end=16.0)
    held, _ = engine.handle(SEQUENCER, press((4, 2)), replace(STOPPED, sequencer=view))
    assert engine.x_rows(held) == (6,)


def test_an_unowned_slide_in_sequencer_mode_releases_the_pad_it_left():
    slide = SlideMoved(pad=1, from_column=4, to_column=5)
    held, _ = engine.handle(SEQUENCER, press((12, 1)), STOPPED)
    assert engine.slide(held, slide, STOPPED) == engine.handle(
        held, press((4, 1), False), STOPPED
    )
