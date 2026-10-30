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
    SetScale,
    SetMixer,
    ShowMessage,
    Snapshot,
    WriteChord,
)
from BleakLoop.core.leds import BLUE, CYAN, GREEN, OFF, ORANGE, RED, WHITE, YELLOW, Blink, Light
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


HELD = replace(ENTERED, chord_holds=((6, 8, (60, 64, 67), None),))


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


# Presses

MAJ, MIN, SUS4 = (3, 8), (3, 7), (3, 6)
SEVEN, MAJ7 = (4, 8), (4, 7)


def handle(state, key, snapshot=SNAP_IN, pressed=True):
    return chord.handle(state, press(key, pressed), snapshot)


def hold(state, *keys):
    for key in keys:
        state, _ = handle(state, key)
    return state


def message(state, key, snapshot=SNAP_IN):
    _, actions = handle(state, key, snapshot)
    return actions[-1].text


def test_a_quality_press_switches_the_device_to_semitones():
    state, actions = handle(ENTERED, MAJ)
    assert state.chord_qualities == ("maj",)
    assert actions == [SetChordDevice(2, (4, 7, 0, 0, 0, 0), False)]


def test_a_quality_release_goes_back_to_the_key():
    state = hold(ENTERED, MAJ)
    state, actions = handle(state, MAJ, pressed=False)
    assert state.chord_qualities == () and actions == [TRIADS]


def test_the_last_pressed_quality_wins():
    state = hold(ENTERED, MAJ, MIN)
    assert state.chord_qualities == ("maj", "min")
    assert state.chord_setting[1] == (3, 7, 0, 0, 0, 0)
    state, _ = handle(state, MIN, pressed=False)
    assert state.chord_setting[1] == (4, 7, 0, 0, 0, 0)


def test_an_extension_with_no_quality_stays_in_scale_degrees():
    _, actions = handle(ENTERED, SEVEN)
    assert actions == [SetChordDevice(2, (2, 4, 6, 0, 0, 0), True)]


def test_maj7_alone_plays_maj_and_maj7_in_semitones():
    _, actions = handle(ENTERED, MAJ7)
    assert actions == [SetChordDevice(2, (4, 7, 11, 0, 0, 0), False)]


@pytest.mark.parametrize(
    "key, field, value, text",
    [
        (layout.CHORD_INV, "chord_inv", 1, "Inversion: 1st"),
        (layout.CHORD_SPREAD, "chord_spread", 1, "Spread: Open"),
        (layout.CHORD_BASS, "chord_bass", True, "Bass ON"),
    ],
)
def test_voicing_pads_latch(key, field, value, text):
    state, actions = handle(ENTERED, key)
    assert getattr(state, field) == value
    assert actions[-1] == ShowMessage(text)
    assert isinstance(actions[0], SetChordDevice)


def test_inv_wraps_after_2nd_on_a_triad_and_after_3rd_on_a_seventh():
    state = hold(ENTERED, layout.CHORD_INV, layout.CHORD_INV, layout.CHORD_INV)
    assert state.chord_inv == 0
    state = hold(replace(ENTERED, chord_extensions=frozenset({"7"})), *[layout.CHORD_INV] * 3)
    assert state.chord_inv == 3


def test_lead_is_inert():
    assert handle(ENTERED, layout.CHORD_LEAD) == (ENTERED, [])


def test_a_degree_press_plays_and_says_its_chord():
    state, actions = handle(ENTERED, (10, 1))  # G, V
    assert state.chord_holds == ((10, 1, (67, 71, 74), None),)
    assert actions == [ShowMessage("G · V in C major · G B D")]


def test_a_piano_key_with_maj_and_7():
    state = hold(ENTERED, MAJ, SEVEN)
    # Pads 8 and 7 are the bottom pair: G is column 6 + 4 on pad 8, 48 + 7.
    assert message(state, (10, 8)).startswith("G7 · V7 in C major · G B D F")


def test_a_release_ends_the_hold():
    state = hold(ENTERED, (10, 1))
    state, actions = handle(state, (10, 1), pressed=False)
    assert (state.chord_holds, actions) == ((), [])


def test_an_out_of_key_degree_with_nothing_held_is_silent_with_a_hint():
    state, actions = handle(ENTERED, (13, 1))  # semitone 10, B♭
    assert state.chord_holds == ()
    assert actions == [ShowMessage("Hold Maj for ♭VII")]


def test_a_borrowed_degree_with_a_quality_held():
    state = hold(ENTERED, MAJ)
    assert message(state, (13, 1)).startswith("B♭ · ♭VII, borrowed from C minor · B♭ D F")


def test_a_piano_gap_does_nothing():
    assert handle(ENTERED, (8, 7)) == (ENTERED, [])


def test_shift_and_a_piano_key_sets_the_root():
    state = replace(ENTERED, shift=True)
    assert handle(state, (7, 8))[1] == [SetScale(root=2), ShowMessage("Key: D major")]


@pytest.mark.parametrize("key, name, text", [(MAJ, "Major", "C major"), (MIN, "Minor", "C minor")])
def test_shift_and_maj_or_min_sets_the_scale(key, name, text):
    state = replace(ENTERED, shift=True)
    new, actions = handle(state, key)
    assert new.chord_qualities == ()
    assert actions == [SetScale(name=name, mode_on=True), ShowMessage(f"Key: {text}")]


def test_shift_and_another_quality_does_nothing():
    state = replace(ENTERED, shift=True)
    assert handle(state, SUS4) == (state, [])


def test_octave_steps_within_its_range():
    state, actions = handle(ENTERED, layout.CHORD_OCT_UP)
    assert (state.chord_octave, actions) == (1, [ShowMessage("Octave 1")])
    assert handle(state, layout.CHORD_OCT_UP) == (state, [])
    low = replace(ENTERED, chord_octave=-2)
    assert handle(low, layout.CHORD_OCT_DOWN) == (low, [])


def test_octave_is_refused_while_a_chord_pad_is_held():
    assert handle(HELD, layout.CHORD_OCT_UP) == (HELD, [])


def test_the_octave_moves_the_degree_row():
    state = replace(ENTERED, chord_octave=-1)
    assert handle(state, (3, 1))[0].chord_holds[0][2] == (48, 52, 55)


@pytest.mark.parametrize("key", [layout.CHORD, layout.SESSION])
def test_chord_or_session_returns_to_session(key):
    state, actions = handle(ENTERED, key)
    assert state.mode is Mode.SESSION and RemoveChord(2) in actions


def test_mixer_leaves_for_mixer_mode():
    state, _ = handle(ENTERED, layout.MIXER)
    assert state.mode is Mode.SESSION and state.mixer


@pytest.mark.parametrize("key", [layout.SEQ, layout.COPY, layout.DELETE])
def test_seq_copy_and_delete_are_inert(key):
    assert handle(ENTERED, key) == (ENTERED, [])


def test_pad_note_translates_in_key_pads_only():
    assert chord.pad_note(ENTERED, TARGET, 10, 1) == 67
    assert chord.pad_note(ENTERED, TARGET, 13, 1) is None
    assert chord.pad_note(hold(ENTERED, MAJ), TARGET, 13, 1) == 70
    assert chord.pad_note(replace(ENTERED, shift=True), TARGET, 10, 1) is None
    assert chord.pad_note(ENTERED, TARGET, 3, 8) is None


# Recording

# Session-recording into scene 1, the playhead at beat 3.5.
RECORDING = snap(
    replace(TARGET, recording=True, scene=1, position=3.5), arms=SNAP_IN.arms
)


def test_a_recorded_press_writes_its_chord_at_the_release():
    state, _ = handle(ENTERED, (10, 1), RECORDING)  # G, V
    assert state.chord_holds == ((10, 1, (67, 71, 74), (2, 1, 67, 3.5)),)
    state, actions = handle(state, (10, 1), RECORDING, pressed=False)
    assert state.chord_holds == ()
    assert actions == [WriteChord(2, 1, 67, 3.5, (67, 71, 74))]


def test_a_press_while_not_recording_writes_nothing():
    state = hold(ENTERED, (10, 1))
    assert handle(state, (10, 1), pressed=False)[1] == []


def test_a_recorded_press_released_after_leaving_still_writes():
    state, _ = handle(ENTERED, (10, 1), RECORDING)
    state, _ = chord.leave(state, SNAP_IN)
    _, actions = engine.handle(state, press((10, 1), False), SNAP_IN)
    assert actions == [WriteChord(2, 1, 67, 3.5, (67, 71, 74))]


def test_a_write_closes_a_morph_step_first():
    state, _ = handle(replace(ENTERED, fx_undo_open=True), (10, 1), RECORDING)
    _, actions = handle(state, (10, 1), RECORDING, pressed=False)
    assert actions == [EndUndoStep(), WriteChord(2, 1, 67, 3.5, (67, 71, 74))]


def test_arrangement_recording_says_once_per_take_that_it_writes_only_the_root():
    arranging = snap(replace(TARGET, arrangement=True), arms=SNAP_IN.arms)
    state, actions = handle(ENTERED, (10, 1), arranging)
    assert actions[-1] == ShowMessage(chord.SESSION_ONLY)
    state, _ = handle(state, (10, 1), arranging, pressed=False)
    state, actions = handle(state, (10, 1), arranging)
    assert ShowMessage(chord.SESSION_ONLY) not in actions
    state, _ = handle(state, (10, 1), arranging, pressed=False)
    state, _ = chord.sync(state, SNAP_IN)  # the take ended
    assert handle(state, (10, 1), arranging)[1][-1] == ShowMessage(chord.SESSION_ONLY)


# Lights


def test_c_major_at_rest():
    frame = chord.render(ENTERED, SNAP_IN)
    row = [frame[(column, 1)].colour for column in range(3, 15)]
    # C C♯ D E♭ E F F♯ G A♭ A B♭ B: in-key degrees by quality, borrowed ones by theirs.
    assert row == [
        ORANGE, ORANGE, BLUE, ORANGE, BLUE, ORANGE, RED, ORANGE, ORANGE, BLUE, ORANGE, RED
    ]
    # The piano's bottom pair: C cyan, naturals white, sharps off.
    assert [frame[(column, 8)].colour for column in range(6, 15)] == [CYAN] + [WHITE] * 6 + [
        CYAN,
        WHITE,
    ]
    assert frame[(6, 7)].colour == OFF and frame[(8, 7)] == Light(OFF)
    assert frame[MAJ] == Light(ORANGE) and frame[SEVEN] == Light(WHITE)
    assert frame[layout.CHORD] == Light(BLUE) and frame[layout.SEQ] == Light(OFF)


def test_g7_sounding_from_the_piano():
    state = hold(ENTERED, MAJ, SEVEN, (10, 8))
    frame = chord.render(state, SNAP_IN)
    # G3 B3 D4 F4 on the piano: G is column 10 pad 8, B column 12, D column 7 pad 6, F 9/6.
    assert frame[(10, 8)].colour == GREEN
    assert [frame[key].colour for key in ((12, 8), (7, 6), (9, 6))] == [YELLOW] * 3
    assert frame[(10, 1)].colour == GREEN
    assert frame[MAJ] == Light(ORANGE, Blink.FAST) and frame[SEVEN] == Light(WHITE, Blink.FAST)


def test_shift_layer_lights():
    frame = chord.render(replace(ENTERED, shift=True), SNAP_IN)
    assert (frame[MAJ], frame[MIN], frame[SUS4], frame[SEVEN]) == (
        Light(CYAN),
        Light(WHITE),
        Light(OFF),
        Light(OFF),
    )
    assert frame[(6, 8)].colour == CYAN and frame[(6, 7)].colour == WHITE


def test_octave_pads_go_dark_at_their_limit():
    frame = chord.render(replace(ENTERED, chord_octave=1), SNAP_IN)
    assert frame[layout.CHORD_OCT_UP] == Light(OFF) and frame[layout.CHORD_OCT_DOWN] == Light(WHITE)


def test_leaving_closes_a_morph_step_before_removing_the_device():
    _, actions = chord.leave(replace(ENTERED, fx_undo_open=True), SNAP_IN)
    assert actions.index(EndUndoStep()) < actions.index(RemoveChord(2))


def test_a_move_closes_a_morph_step_before_the_device_changes():
    moved = snap(replace(TARGET, track=5), arms=SNAP_IN.arms)
    _, actions = chord.sync(replace(ENTERED, fx_undo_open=True), moved)
    assert actions.index(EndUndoStep()) < actions.index(RemoveChord(2))
