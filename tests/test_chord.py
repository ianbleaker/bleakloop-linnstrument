from dataclasses import replace

import pytest

from BleakLoop.core import chord, engine, layout, session
from BleakLoop.core.model import (
    ChordView,
    EndUndoStep,
    EnterMode,
    InsertChord,
    PadPress,
    RemoveChord,
    ScaleView,
    SetArms,
    SetChordDevice,
    SetMixer,
    ShowMessage,
    Snapshot,
)
from BleakLoop.core.modes import Mode, State

C_MAJOR = ScaleView(True, 0, (0, 2, 4, 5, 7, 9, 11), "Major")
TARGET = ChordView(track=2, is_midi=True, scale=C_MAJOR, device_present=True)
# The diatonic triad in scale degrees, with Use Current Scale on.
TRIADS = SetChordDevice(2, (2, 4, 0, 0, 0, 0), True)
REST = SetChordDevice(2, (0, 0, 0, 0, 0, 0), False)


def snap(view=TARGET, arms=(False, True, False, None, False, False), **k):
    return Snapshot(
        is_playing=False,
        song_beats=0.0,
        tempo=120.0,
        metronome=False,
        session_view=True,
        track_count=6,
        scene_count=4,
        arms=arms,
        chord=view,
        **k,
    )


SNAP = snap()
# Entered on track 2 with track 1 armed before: BleakLoop disarmed 1 and armed 2.
ENTERED = State(
    mode=Mode.CHORD,
    saved_arms=(False, True, False, None, False, False),
    set_arms=(False, False, True, None, False, False),
    arm_track=2,
    chord_device_track=2,
    chord_setting=(2, (2, 4, 0, 0, 0, 0), True),
)
SNAP_IN = snap(arms=(False, False, True, None, False, False))


def press(key, pressed=True, velocity=100):
    return PadPress(key[0], key[1], pressed, velocity)


def test_chord_enters_on_a_midi_track():
    state, actions = session.handle(State(), press(layout.CHORD), SNAP)
    assert state.mode is Mode.CHORD
    assert (state.arm_track, state.chord_device_track) == (2, 2)
    assert actions == [
        SetArms(((1, False), (2, True))),
        InsertChord(2),
        TRIADS,
        EnterMode(Mode.CHORD),
        ShowMessage("Chord: C major"),
    ]


def test_chord_refuses_an_audio_track():
    snapshot = snap(replace(TARGET, is_midi=False))
    assert session.handle(State(), press(layout.CHORD), snapshot) == (
        State(),
        [ShowMessage("Chord needs a MIDI track")],
    )


def test_chord_refuses_master():
    assert session.handle(State(), press(layout.CHORD), snap(ChordView()))[1] == [
        ShowMessage("Chord needs a MIDI track")
    ]


def test_shift_chord_does_nothing():
    state = State(shift=True)
    assert session.handle(state, press(layout.CHORD), SNAP) == (state, [])


def test_entry_closes_a_morph_step_first():
    _, actions = session.handle(State(fx_undo_open=True), press(layout.CHORD), SNAP)
    assert actions[0] == EndUndoStep()


def test_leaving_for_session_removes_the_device_and_restores_the_arm():
    state, actions = chord.leave(ENTERED, SNAP_IN)
    assert state.mode is Mode.SESSION and not state.mixer and not state.fx
    assert (state.arm_track, state.chord_device_track) == (None, None)
    assert actions == [REST, RemoveChord(2), SetArms(((1, True), (2, False))), EnterMode(Mode.SESSION)]


def test_leaving_for_mixer():
    state, actions = chord.leave(ENTERED, SNAP_IN, layout.MIXER)
    assert state.mode is Mode.SESSION and state.mixer
    assert actions[-3:] == [EnterMode(Mode.SESSION), SetMixer(True), ShowMessage("Mixer Mode ON")]


def test_leaving_for_fx():
    state, actions = chord.leave(ENTERED, SNAP_IN, layout.FX)
    assert state.mode is Mode.SESSION and state.fx
    assert actions[-1] == ShowMessage("FX Mode ON")


HELD = replace(ENTERED, chord_holds=((6, 8, (60, 64, 67)),))


def test_leaving_with_a_pad_held_defers_the_removal():
    state, actions = chord.leave(HELD, SNAP_IN)
    assert state.chord_remove_pending and state.chord_device_track == 2
    assert RemoveChord(2) not in actions
    assert engine.chord_sync(state, SNAP_IN) == (state, [])


def test_the_deferred_removal_runs_once_the_pad_is_released():
    state, _ = chord.leave(HELD, SNAP_IN)
    state, actions = engine.handle(state, press((6, 8), False), SNAP_IN)
    assert (state.chord_holds, actions) == ((), [])
    state, actions = engine.chord_sync(state, SNAP_IN)
    assert actions == [RemoveChord(2)]
    assert not state.chord_remove_pending and state.chord_device_track is None


def test_reentering_the_same_track_keeps_the_waiting_device():
    state, _ = chord.leave(HELD, SNAP_IN)
    state, actions = session.handle(state, press(layout.CHORD), SNAP)
    assert not state.chord_remove_pending and state.chord_device_track == 2
    assert InsertChord(2) not in actions and RemoveChord(2) not in actions


@pytest.mark.parametrize("target", [Mode.SESSION, Mode.SEQUENCER])
def test_chord_sync_does_nothing_outside_chord_mode(target):
    state = State(mode=target)
    assert engine.chord_sync(state, SNAP) == (state, [])


# The display tick


def test_sync_without_a_change_does_nothing():
    assert chord.sync(ENTERED, SNAP_IN) == (ENTERED, [])


def test_sync_moves_the_arm_and_the_device_to_a_track_clicked_in_live():
    moved = snap(replace(TARGET, track=5, device_present=False), arms=SNAP_IN.arms)
    state, actions = chord.sync(ENTERED, moved)
    assert actions == [
        SetArms(((2, False), (5, True))),
        RemoveChord(2),
        InsertChord(5),
        SetChordDevice(5, (2, 4, 0, 0, 0, 0), True),
    ]
    assert (state.arm_track, state.chord_device_track) == (5, 5)


def test_sync_waits_for_held_pads_before_moving():
    moved = snap(replace(TARGET, track=5), arms=SNAP_IN.arms)
    assert chord.sync(HELD, moved) == (HELD, [])


def test_sync_on_an_audio_track_says_so_once_and_keeps_the_device():
    audio = snap(replace(TARGET, track=1, is_midi=False), arms=SNAP_IN.arms)
    state, actions = chord.sync(ENTERED, audio)
    assert actions == [ShowMessage("Chord needs a MIDI track")]
    assert state.chord_device_track == 2
    assert chord.sync(state, audio) == (state, [])


def test_sync_reinserts_a_device_undo_took_back():
    undone = snap(replace(TARGET, device_present=False), arms=SNAP_IN.arms)
    state, actions = chord.sync(ENTERED, undone)
    assert actions == [InsertChord(2, again=True), TRIADS]


def test_sync_in_linnstrument_mode_rests_the_device():
    state, actions = engine.handle(ENTERED, press(layout.MODE_PAD), SNAP_IN)
    state, actions = engine.chord_sync(state, SNAP_IN)
    assert actions == [REST]
    back, _ = engine.handle(state, press(layout.MODE_PAD), SNAP_IN)
    assert engine.chord_sync(back, SNAP_IN)[1] == [TRIADS]


def test_sync_follows_the_selection_in_linnstrument_mode():
    state, _ = engine.handle(ENTERED, press(layout.MODE_PAD), SNAP_IN)
    moved = snap(replace(TARGET, track=5), arms=SNAP_IN.arms)
    _, actions = engine.chord_sync(state, moved)
    assert actions[1:] == [RemoveChord(2), InsertChord(5), SetChordDevice(5, (0,) * 6, False)]
