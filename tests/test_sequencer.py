from dataclasses import replace

import pytest

from BleakLoop.core import column_1, engine, layout, modes, sequencer
from BleakLoop.core.leds import (
    BLUE,
    CYAN,
    GREEN,
    LIME,
    MAGENTA,
    OFF,
    ORANGE,
    PINK,
    RED,
    WHITE,
    YELLOW,
    Blink,
    Light,
)
from BleakLoop.core.model import (
    ToggleDetailView,
    DrumView,
    DuplicateLoop,
    EditNotes,
    BeginUndoStep,
    EndUndoStep,
    EnterMode,
    FireSlot,
    ModifyNotes,
    NoteView,
    PadPress,
    RemovePitch,
    SelectDrumPad,
    ScaleView,
    SelectedTrack,
    SelectSetTrack,
    SequencerView,
    SetArms,
    SetDrumScroll,
    SetLoop,
    SetMixer,
    SetTempo,
    ShowClip,
    StepDevice,
    StepTrack,
    SlideMoved,
    ShowMessage,
    Snapshot,
    XAxis,
)
from BleakLoop.core.modes import Mode, Origin, State, StepHold

SEQ = State(mode=Mode.SEQUENCER)
MIDI = SequencerView(track=0, is_midi=True, has_clip=True, loop_end=16.0)


def note(start, pitch=48, duration=0.25, velocity=100, note_id=1):
    return NoteView(note_id, pitch, start, duration, velocity)


# Step maths


@pytest.mark.parametrize(
    "rate, triplet, length",
    [(1.0, False, 1.0), (0.5, False, 0.5), (0.25, False, 0.25), (0.125, False, 0.125)]
    + [(1.0, True, 2 / 3), (0.5, True, 1 / 3), (0.25, True, 1 / 6), (0.125, True, 1 / 12)],
)
def test_page_span_is_64_steps(rate, triplet, length):
    state = State(seq_rate=rate, seq_triplet=triplet)
    assert sequencer.step_length(state) == pytest.approx(length)
    assert sequencer.page_span(state) == pytest.approx(64 * length)


@pytest.mark.parametrize("s", range(64))
def test_step_key_round_trip(s):
    assert sequencer.step_of(sequencer.step_key(s)) == s


def test_step_keys_fill_columns_3_to_10_top_row_first():
    assert sequencer.step_key(0) == (3, 1)
    assert sequencer.step_key(7) == (10, 1)
    assert sequencer.step_key(8) == (3, 2)
    assert sequencer.step_key(63) == (10, 8)


def test_a_note_at_the_midpoint_belongs_to_the_next_step():
    assert sequencer.step_of_time(0.125, 0.25) == 1


def test_a_note_just_before_the_midpoint_stays():
    assert sequencer.step_of_time(0.1249, 0.25) == 0


def test_a_note_just_before_its_step_belongs_to_it():
    assert sequencer.step_of_time(0.249, 0.25) == 1


def test_float_noise_at_a_step_start_is_ignored():
    # 3 triplet sixteenths, summed in float.
    start = 1 / 6 + 1 / 6 + 1 / 6
    assert sequencer.step_of_time(start, 1 / 6) == 3
    assert sequencer.step_of_time(start - 1e-9, 1 / 6) == 3


def test_float_noise_at_the_midpoint_goes_to_the_next_step():
    length = 1 / 6
    assert sequencer.step_of_time(2.5 * length - 1e-9, length) == 3


def test_notes_in_step():
    a, b, c = note(0.0, note_id=1), note(0.25, note_id=2), note(0.3, pitch=50, note_id=3)
    view = SequencerView(notes=(a, b, c))
    assert sequencer.notes_in_step(view, 1, 0.25) == (b, c)


def test_playhead_floors_the_position():
    view = SequencerView(is_playing=True, position=0.49)
    assert sequencer.playhead(SEQ, view) == 1


def test_playhead_ignores_float_noise():
    view = SequencerView(is_playing=True, position=1 / 6 + 1 / 6 + 1 / 6 - 1e-9)
    assert sequencer.playhead(State(seq_triplet=True), view) == 3


def test_no_playhead_while_stopped():
    assert sequencer.playhead(SEQ, SequencerView(position=1.0)) is None


def test_follow_shows_the_playing_page():
    view = SequencerView(is_playing=True, position=17.0)
    assert sequencer.view_page(State(seq_page=0), view) == 1


def test_pinned_page():
    view = SequencerView(is_playing=True, position=17.0)
    assert sequencer.view_page(State(seq_follow=False, seq_page=3), view) == 3


def test_follow_while_stopped_shows_the_pinned_page():
    assert sequencer.view_page(State(seq_page=2), SequencerView(position=17.0)) == 2


# Note pads


def test_c2_is_the_bottom_left():
    assert sequencer.pad_note(SEQ, MIDI, 11, 8) == 48


def test_a_row_up_is_a_major_third():
    assert sequencer.pad_note(SEQ, MIDI, 11, 7) == 52
    assert sequencer.pad_note(SEQ, MIDI, 12, 8) == 49


def test_top_right():
    assert sequencer.pad_note(SEQ, MIDI, 14, 1) == 79


def test_the_highest_base_reaches_127():
    assert sequencer.pad_note(State(seq_base=96), MIDI, 14, 1) == 127


def test_notes_above_127_have_no_pad():
    # The last rack row puts the upper bank past 127.
    view = SequencerView(is_midi=True, drum=DrumView(28, None, frozenset()))
    assert sequencer.pad_note(SEQ, view, 14, 5) == 127
    assert sequencer.pad_note(SEQ, view, 11, 4) is None


def test_no_note_while_the_settings_show():
    assert sequencer.pad_note(State(seq_settings=True), MIDI, 11, 8) is None


def test_no_note_off_a_midi_track():
    assert sequencer.pad_note(SEQ, SequencerView(track=0), 11, 8) is None


def test_no_note_outside_the_note_columns():
    assert sequencer.pad_note(SEQ, MIDI, 10, 8) is None


def test_drum_pads_start_at_the_rack_scroll():
    view = SequencerView(is_midi=True, drum=DrumView(9, None, frozenset()))
    assert sequencer.pad_note(SEQ, view, 11, 8) == 36
    assert sequencer.pad_note(SEQ, view, 14, 5) == 51
    assert sequencer.pad_note(SEQ, view, 11, 4) == 52


# Side columns, leaving and the arm

# Tracks 0, 2 and 5 are MIDI; the target is track 2, scene 1.
TARGET = replace(MIDI, track=2, scene=1, midi_tracks=(0, 2, 5))
ARMS = (False, True, True, None, False, False)


def snap(view=TARGET, arms=ARMS, **k):
    return Snapshot(
        is_playing=False,
        song_beats=0.0,
        tempo=120.0,
        metronome=False,
        session_view=True,
        track_count=6,
        scene_count=4,
        arms=arms,
        sequencer=view,
        **k,
    )


# Entered on track 2 with track 1 armed before: BleakLoop disarmed 1 and armed 2.
ENTERED = State(
    mode=Mode.SEQUENCER,
    seq_saved_arms=(False, True, False, None, False, False),
    seq_set_arms=(False, False, True, None, False, False),
    seq_track=2,
)
SNAP_IN = snap(arms=(False, False, True, None, False, False))


def press(key, pressed=True, velocity=100):
    return PadPress(key[0], key[1], pressed, velocity)


def handle(state, key, snapshot=SNAP_IN, pressed=True, velocity=100):
    return sequencer.handle(state, press(key, pressed, velocity), snapshot)


def test_seq_returns_to_session_restoring_the_arm():
    state, actions = handle(ENTERED, layout.SEQ)
    assert state.mode is Mode.SESSION
    assert state.seq_saved_arms is None and state.seq_set_arms is None
    assert state.seq_track is None
    assert actions == [SetArms(((1, True), (2, False))), EnterMode(Mode.SESSION)]


def test_session_returns_to_session():
    state, actions = handle(ENTERED, layout.SESSION)
    assert state.mode is Mode.SESSION and not state.mixer and not state.fx
    assert actions[-1] == EnterMode(Mode.SESSION)


def test_mixer_leaves_for_mixer_mode():
    state, actions = handle(ENTERED, layout.MIXER)
    assert state.mode is Mode.SESSION and state.mixer
    assert actions[-2:] == [SetMixer(True), ShowMessage("Mixer Mode ON")]


def test_fx_leaves_for_fx_mode():
    state, actions = handle(ENTERED, layout.FX)
    assert state.mode is Mode.SESSION and state.fx
    assert actions[-1] == ShowMessage("FX Mode ON")


def test_leaving_for_mixer_widens_the_split_window():
    state = replace(ENTERED, split=True, window=layout.Window(10, 0))
    left, _ = handle(state, layout.MIXER, replace(SNAP_IN, track_count=20, scene_count=4))
    assert left.window == layout.Window(7, 0)


def test_every_seq_release_does_nothing():
    assert handle(ENTERED, layout.SEQ, pressed=False) == (ENTERED, [])


def test_a_track_changed_by_hand_keeps_its_arm():
    # Track 4 armed by hand, track 2 disarmed by hand.
    snapshot = snap(arms=(False, False, False, None, True, False))
    _, actions = handle(ENTERED, layout.SEQ, snapshot)
    assert actions == [SetArms(((1, True),)), EnterMode(Mode.SESSION)]


def test_no_restore_when_the_track_count_changed():
    snapshot = snap(arms=(False, False, True, None, False, False, False))
    _, actions = handle(ENTERED, layout.SEQ, snapshot)
    assert actions == [EnterMode(Mode.SESSION)]


def test_leaving_closes_a_slide():
    state, actions = handle(replace(ENTERED, seq_undo_open=True), layout.SEQ)
    assert not state.seq_undo_open
    assert actions[0] == EndUndoStep()


@pytest.mark.parametrize("key", [layout.COPY, layout.DELETE])
def test_copy_and_delete_hold(key):
    held, actions = handle(ENTERED, key)
    assert (held.copy if key == layout.COPY else held.delete)
    assert actions == [
        ShowMessage("Copy: pick a step" if key == layout.COPY else "Delete Mode ON")
    ]
    assert handle(held, key, pressed=False) == (ENTERED, [])


def test_chord_does_nothing():
    assert handle(ENTERED, (16, 6)) == (ENTERED, [])


def test_device_clip_layer_steps_tracks_and_devices():
    held, actions = handle(ENTERED, layout.DEVICE_CLIP)
    assert held.device_clip and actions == []
    assert handle(held, (16, 1)) == (held, [StepTrack(-1)])
    assert handle(held, (16, 4)) == (held, [StepDevice(1)])
    # Not Seq: Device/Clip's layer has nothing on pad 7.
    assert handle(held, layout.SEQ) == (held, [])
    assert handle(held, layout.DEVICE_CLIP, pressed=False)[0] == ENTERED


def engine_presses(state, *presses):
    actions = []
    for key, pressed in presses:
        state, more = engine.handle(state, press(key, pressed), SNAP_IN)
        actions += more
    return state, actions


def test_device_clip_tap_flips_the_detail_view():
    state, actions = engine_presses(
        ENTERED, (layout.DEVICE_CLIP, True), (layout.DEVICE_CLIP, False)
    )
    assert actions == [ToggleDetailView()] and state == ENTERED


@pytest.mark.parametrize("key", [(16, 2), layout.SHIFT])
def test_device_clip_with_another_press_does_not_flip(key):
    _, actions = engine_presses(
        ENTERED, (layout.DEVICE_CLIP, True), (key, True), (key, False), (layout.DEVICE_CLIP, False)
    )
    assert ToggleDetailView() not in actions


def test_device_clip_on_shifts_layer_never_flips():
    _, actions = engine_presses(
        replace(ENTERED, shift=True), (layout.DEVICE_CLIP, True), (layout.DEVICE_CLIP, False)
    )
    assert ToggleDetailView() not in actions


def test_device_clip_layer_lights():
    held, _ = handle(ENTERED, layout.DEVICE_CLIP)
    frame = sequencer.render(held, SNAP_IN)
    assert [frame[(16, pad)] for pad in range(1, 9)] == [
        Light(LIME), Light(LIME), Light(MAGENTA), Light(MAGENTA),
        Light(ORANGE), Light(OFF), Light(OFF), Light(ORANGE, Blink.FAST),
    ]


SHIFTED = replace(ENTERED, shift=True)


@pytest.mark.parametrize("key", [(16, 1), (16, 2), (16, 5), (16, 6)])
def test_shift_layer_dark_pads_do_nothing(key):
    assert handle(SHIFTED, key) == (SHIFTED, [])


def test_shift_tempo_steps():
    assert handle(SHIFTED, (16, 7))[1][0] == SetTempo(121.0)
    assert handle(SHIFTED, (16, 8))[1][0] == SetTempo(119.0)


def test_shift_track_steps_skip_other_tracks():
    assert handle(SHIFTED, (16, 3)) == (SHIFTED, [SelectSetTrack(0)])
    assert handle(SHIFTED, (16, 4)) == (SHIFTED, [SelectSetTrack(5)])


def test_shift_track_step_at_each_end():
    first = snap(replace(TARGET, track=0))
    last = snap(replace(TARGET, track=5))
    assert handle(SHIFTED, (16, 3), first) == (SHIFTED, [ShowMessage("No more MIDI tracks")])
    assert handle(SHIFTED, (16, 4), last) == (SHIFTED, [ShowMessage("No more MIDI tracks")])


def test_sync_without_a_change_does_nothing():
    assert sequencer.sync(ENTERED, SNAP_IN) == (ENTERED, [])


def test_sync_moves_the_arm_to_a_track_clicked_in_live():
    state = replace(ENTERED, seq_holds=(StepHold(0, 3, 1, 100),), seq_copy_source=(0, ()))
    synced, actions = sequencer.sync(state, snap(replace(TARGET, track=5), arms=SNAP_IN.arms))
    assert actions == [SetArms(((2, False), (5, True)))]
    assert synced.seq_track == 5
    assert synced.seq_set_arms == (False, False, False, None, False, True)
    assert synced.seq_holds == () and synced.seq_copy_source is None


def test_the_moved_arm_restores_on_leaving():
    synced, _ = sequencer.sync(ENTERED, snap(replace(TARGET, track=5), arms=SNAP_IN.arms))
    after = snap(replace(TARGET, track=5), arms=(False, False, False, None, False, True))
    _, actions = handle(synced, layout.SEQ, after)
    assert actions == [SetArms(((1, True), (5, False))), EnterMode(Mode.SESSION)]


def test_sync_leaves_the_arm_on_a_non_midi_track_and_says_so_once():
    audio = snap(SequencerView(track=1, scene=1), arms=SNAP_IN.arms)
    state, actions = sequencer.sync(ENTERED, audio)
    assert actions == [ShowMessage("Sequencer needs a MIDI track")]
    assert state.seq_track == 2
    assert sequencer.sync(state, audio) == (state, [])


def test_sync_on_master_says_so_once():
    master = snap(SequencerView(), arms=SNAP_IN.arms)
    state, actions = sequencer.sync(ENTERED, master)
    assert actions == [ShowMessage("Sequencer needs a MIDI track")]
    assert sequencer.sync(state, master) == (state, [])


def test_sync_closes_a_slide():
    state = replace(ENTERED, seq_undo_open=True)
    synced, actions = sequencer.sync(state, snap(replace(TARGET, track=5), arms=SNAP_IN.arms))
    assert not synced.seq_undo_open
    assert actions[0] == EndUndoStep()


def test_linnstrument_and_back_keep_the_arm():
    state, actions = handle(ENTERED, layout.MODE_PAD)
    assert state.mode is Mode.LINNSTRUMENT
    assert state.came_from is Origin.SEQUENCER
    assert actions == [EnterMode(Mode.LINNSTRUMENT)]
    back, actions = column_1.handle(state, press(layout.MODE_PAD), SNAP_IN)
    assert back.mode is Mode.SEQUENCER
    assert actions == [EnterMode(Mode.SEQUENCER)]
    assert back.seq_saved_arms == ENTERED.seq_saved_arms
    assert back.seq_set_arms == ENTERED.seq_set_arms
    assert back.seq_track == 2


def test_linnstrument_closes_a_slide():
    state, actions = handle(replace(ENTERED, seq_undo_open=True), layout.MODE_PAD)
    assert actions == [EndUndoStep(), EnterMode(Mode.LINNSTRUMENT)]


def test_record_clip_records_on_the_selected_track():
    selected = SelectedTrack(index=2, name="Keys", armed=True, clips=(True, False, False, False))
    snapshot = replace(SNAP_IN, selected_track=selected, selected_scene=0)
    _, actions = handle(ENTERED, layout.RECORD, snapshot)
    assert actions == [
        FireSlot(2, 1, legato=False, record_length=None),
        ShowClip(2, 1),
        ShowMessage("Record Clip"),
    ]


def test_shift_pad_7_opens_the_scene_page():
    state, _ = handle(SHIFTED, layout.MODE_PAD)
    assert state.scene_page


# Step editing


def with_notes(*notes, **k):
    return snap(replace(TARGET, notes=notes, **k), arms=SNAP_IN.arms)


def tap(state, key, snapshot=SNAP_IN, velocity=100):
    held, actions = handle(state, key, snapshot, velocity=velocity)
    assert actions == []
    return handle(held, key, snapshot, pressed=False)


def test_a_tap_adds_a_note_on_release():
    state, actions = tap(ENTERED, (4, 1), velocity=90)
    assert state.seq_holds == ()
    assert actions == [EditNotes(2, 1, add=((48, 0.25, 0.25, 90),))]


def test_a_tap_removes_the_pitch():
    snapshot = with_notes(note(0.25, note_id=7), note(0.25, pitch=50, note_id=8))
    _, actions = tap(ENTERED, (4, 1), snapshot)
    assert actions == [EditNotes(2, 1, remove=(7,))]


def test_a_tap_adds_beside_other_pitches():
    snapshot = with_notes(note(0.25, pitch=50, note_id=8))
    _, actions = tap(ENTERED, (4, 1), snapshot)
    assert actions == [EditNotes(2, 1, add=((48, 0.25, 0.25, 100),))]


def test_the_press_holds_the_step_and_its_notes():
    snapshot = with_notes(note(0.25, note_id=7))
    held, _ = handle(replace(ENTERED, shift=True), (4, 1), snapshot, velocity=80)
    assert held.seq_holds == (
        StepHold(
            1,
            4,
            1,
            80,
            shift=True,
            notes=(note(0.25, note_id=7),),
            target=(2, 1),
            length=0.25,
        ),
    )


def test_a_span_replaces_the_pitch_between_both_steps():
    snapshot = with_notes(
        note(0.5, note_id=1), note(0.75, pitch=50, note_id=2), note(1.5, note_id=3)
    )
    held, _ = handle(ENTERED, (4, 1), snapshot, velocity=70)
    spanned, actions = handle(held, (8, 1), snapshot, velocity=120)
    assert actions == [EditNotes(2, 1, remove=(1,), add=((48, 0.25, 1.25, 70),))]
    assert all(h.used for h in spanned.seq_holds)
    # Neither release toggles.
    released, actions = handle(spanned, (8, 1), snapshot, pressed=False)
    assert actions == []
    assert handle(released, (4, 1), snapshot, pressed=False) == (
        replace(released, seq_holds=()),
        [],
    )


def test_an_earlier_step_after_a_later_one_is_no_span():
    held, _ = handle(ENTERED, (8, 1))
    both, actions = handle(held, (4, 1))
    assert actions == [] and len(both.seq_holds) == 2


def test_hold_and_a_note_pad_toggles_that_pitch_on_each_held_step():
    snapshot = with_notes(note(0.0, pitch=52, note_id=4))
    held, _ = handle(ENTERED, (3, 1), snapshot)
    held, _ = handle(held, (4, 1), snapshot)
    state, actions = handle(held, (11, 7), snapshot, velocity=60)
    assert actions == [EditNotes(2, 1, remove=(4,), add=((52, 0.25, 0.25, 60),))]
    assert state.seq_pitch == 48
    assert all(h.used for h in state.seq_holds)


def test_a_note_pad_selects_its_note():
    state, actions = handle(ENTERED, (12, 7))
    assert state.seq_pitch == 53 and actions == []
    assert handle(state, (12, 7), pressed=False) == (state, [])


def test_copy_then_paste_across_pages():
    long = with_notes(
        note(0.3, pitch=50, duration=0.5, velocity=80, note_id=1),
        note(16.25, note_id=2),
        loop_end=32.0,
    )
    copying = replace(ENTERED, copy=True)
    state, actions = handle(copying, (4, 1), long)
    assert state.seq_copy_source == (1, ((50, pytest.approx(0.05), 0.5, 80),))
    assert actions == [ShowMessage("Copy: pick steps")]
    paged = replace(state, seq_follow=False, seq_page=1)
    pasted, actions = handle(paged, (4, 1), long)
    assert pasted == paged
    [edit] = actions
    assert edit.remove == (2,)
    assert edit.add == ((50, pytest.approx(16.3), 0.5, 80),)
    # Copy's release drops the source.
    assert handle(pasted, layout.COPY, long, pressed=False)[0].seq_copy_source is None


def test_copy_needs_notes_in_the_source():
    copying = replace(ENTERED, copy=True)
    assert handle(copying, (4, 1)) == (copying, [ShowMessage("Step is empty")])


def test_delete_clears_a_step():
    snapshot = with_notes(note(0.25, note_id=7), note(0.3, pitch=50, note_id=8))
    deleting = replace(ENTERED, delete=True)
    assert handle(deleting, (4, 1), snapshot) == (
        deleting,
        [EditNotes(2, 1, remove=(7, 8))],
    )
    assert handle(deleting, (5, 1), snapshot) == (deleting, [])


def test_delete_and_a_note_pad_removes_the_pitch():
    deleting = replace(ENTERED, delete=True)
    assert handle(deleting, (11, 8)) == (deleting, [RemovePitch(2, 1, 48)])


def test_copy_beats_delete():
    snapshot = with_notes(note(0.25, note_id=7))
    both = replace(ENTERED, copy=True, delete=True)
    state, actions = handle(both, (4, 1), snapshot)
    assert state.seq_copy_source is not None


EMPTY = replace(TARGET, has_clip=False, loop_end=0.0)


def test_the_first_edit_on_an_empty_slot_creates_a_bar():
    _, actions = tap(ENTERED, (3, 1), snap(EMPTY, arms=SNAP_IN.arms))
    assert actions == [EditNotes(2, 1, add=((48, 0.0, 0.25, 100),), create_length=4.0)]


def test_a_new_clip_follows_fixed_length():
    state = replace(ENTERED, fixed_length=2)
    snapshot = snap(EMPTY, arms=SNAP_IN.arms, signature_numerator=6, signature_denominator=8)
    _, actions = tap(state, (3, 1), snapshot)
    assert actions[0].create_length == 6.0
    # Step 24 starts at 6 beats: past the new clip.
    assert handle(state, (3, 4), snapshot) == (state, [])


def test_steps_past_the_loop_end_are_inert():
    short = with_notes(loop_end=4.0)
    assert handle(ENTERED, (3, 3), short) == (ENTERED, [])
    held, _ = handle(ENTERED, (10, 2), short)
    assert held.seq_holds


def test_steps_off_a_midi_track_are_inert():
    audio = snap(SequencerView(track=1), arms=SNAP_IN.arms)
    assert handle(ENTERED, (3, 1), audio) == (ENTERED, [])


def test_an_edit_closes_a_morph_step_first():
    state, actions = tap(replace(ENTERED, fx_undo_open=True), (3, 1))
    assert not state.fx_undo_open
    assert actions == [EndUndoStep(), EditNotes(2, 1, add=((48, 0.0, 0.25, 100),))]


def test_edits_are_dropped_during_a_slide():
    sliding = replace(ENTERED, seq_undo_open=True)
    assert tap(sliding, (3, 1)) == (sliding, [])
    deleting = replace(sliding, delete=True)
    assert handle(deleting, (11, 8)) == (deleting, [])


# Settings view and column 15

SETTINGS = replace(ENTERED, seq_settings=True)


def test_the_view_pad_switches_between_notes_and_settings():
    state, actions = handle(ENTERED, layout.SEQ_VIEW)
    assert state.seq_settings and actions == []
    assert handle(state, layout.SEQ_VIEW)[0] == ENTERED


@pytest.mark.parametrize(
    "pad, rate, name", [(1, 1.0, "1/4"), (2, 0.5, "1/8"), (3, 0.25, "1/16"), (4, 0.125, "1/32")]
)
def test_rates(pad, rate, name):
    snapshot = with_notes(note(0.25, note_id=7))
    state, actions = handle(SETTINGS, (11, pad), snapshot)
    assert state.seq_rate == rate
    assert actions == [ShowMessage(f"Rate {name}")]


def test_triplet():
    state, actions = handle(SETTINGS, layout.SEQ_TRIPLET)
    assert state.seq_triplet and actions == [ShowMessage("Rate 1/16 triplet")]
    state, actions = handle(state, layout.SEQ_TRIPLET)
    assert not state.seq_triplet and actions == [ShowMessage("Rate 1/16")]


@pytest.mark.parametrize("start", [ENTERED, SETTINGS])
def test_up_and_down_move_an_octave_in_either_view(start):
    state, actions = handle(start, layout.SEQ_UP)
    assert state.seq_base == 60 and actions == [ShowMessage("Notes from C3")]
    state, actions = handle(start, layout.SEQ_DOWN)
    assert state.seq_base == 36 and actions == [ShowMessage("Notes from C1")]


@pytest.mark.parametrize("base, key", [(96, layout.SEQ_UP), (0, layout.SEQ_DOWN)])
def test_up_and_down_stop_at_the_ends(base, key):
    state = replace(SETTINGS, seq_base=base)
    assert handle(state, key) == (state, [])


@pytest.mark.parametrize("key", [(11, 6), (11, 7), (11, 8), (14, 1), (14, 8)])
def test_dark_settings_pads_do_nothing(key):
    assert handle(SETTINGS, key) == (SETTINGS, [])


def test_settings_pads_never_select_a_note():
    state, _ = handle(SETTINGS, (11, 8))
    assert state.seq_pitch == 48


LONG = with_notes(loop_end=64.0)  # pages 1-4 at 1/16


def test_a_page_pins_the_view():
    state, actions = handle(SETTINGS, layout.SEQ_PAGES[2], LONG)
    assert (state.seq_follow, state.seq_page, state.seq_page_held) == (False, 2, 2)
    assert actions == []
    assert handle(state, layout.SEQ_PAGES[2], LONG, pressed=False)[0].seq_page_held is None


def test_the_playing_page_resumes_follow():
    playing = with_notes(loop_end=64.0, is_playing=True, position=20.0)
    pinned = replace(SETTINGS, seq_follow=False, seq_page=3)
    state, _ = handle(pinned, layout.SEQ_PAGES[1], playing)
    assert state.seq_follow


@pytest.mark.parametrize("first, second", [(1, 3), (3, 1)])
def test_hold_a_page_and_press_another_sets_the_loop(first, second):
    held, _ = handle(SETTINGS, layout.SEQ_PAGES[first], LONG)
    state, actions = handle(held, layout.SEQ_PAGES[second], LONG)
    assert actions == [SetLoop(2, 1, 16.0, 64.0)]
    assert state.seq_page_held == first
    # The second page's release keeps the first held.
    assert handle(state, layout.SEQ_PAGES[second], LONG, pressed=False)[0] == state


def test_a_page_past_the_end_extends_the_loop():
    state, actions = handle(SETTINGS, layout.SEQ_PAGES[5], with_notes(loop_start=4.0))
    assert actions == [SetLoop(2, 1, 4.0, 96.0)]
    assert (state.seq_follow, state.seq_page) == (False, 5)


def test_pages_do_nothing_without_a_clip():
    snapshot = snap(EMPTY, arms=SNAP_IN.arms)
    assert handle(SETTINGS, layout.SEQ_PAGES[1], snapshot) == (SETTINGS, [])


def test_loop_writes_are_dropped_during_a_slide():
    sliding = replace(SETTINGS, seq_undo_open=True)
    assert handle(sliding, layout.SEQ_PAGES[5])[1] == []
    assert handle(sliding, layout.SEQ_DOUBLE)[1] == []


def test_loop_writes_close_a_morph_step():
    state, actions = handle(replace(SETTINGS, fx_undo_open=True), layout.SEQ_PAGES[5])
    assert actions[0] == EndUndoStep() and not state.fx_undo_open


def test_follow_toggles():
    playing = with_notes(loop_end=64.0, is_playing=True, position=20.0)
    state, actions = handle(ENTERED, layout.SEQ_FOLLOW, playing)
    assert (state.seq_follow, state.seq_page) == (False, 1)
    assert actions == [ShowMessage("Follow OFF")]
    state, actions = handle(state, layout.SEQ_FOLLOW, playing)
    assert state.seq_follow and actions == [ShowMessage("Follow ON")]


def test_double():
    assert handle(ENTERED, layout.SEQ_DOUBLE) == (
        ENTERED,
        [DuplicateLoop(2, 1), ShowMessage("Loop doubled")],
    )


def test_halve():
    snapshot = with_notes(loop_start=2.0, loop_end=10.0)
    assert handle(ENTERED, layout.SEQ_HALVE, snapshot) == (
        ENTERED,
        [SetLoop(2, 1, 2.0, 6.0), ShowMessage("Loop halved")],
    )


def test_halve_refuses_below_a_step():
    snapshot = with_notes(loop_end=0.25)
    assert handle(ENTERED, layout.SEQ_HALVE, snapshot) == (
        ENTERED,
        [ShowMessage("Loop can't be shorter than a step")],
    )


@pytest.mark.parametrize("key", [layout.SEQ_DOUBLE, layout.SEQ_HALVE])
def test_double_and_halve_need_a_clip(key):
    snapshot = snap(EMPTY, arms=SNAP_IN.arms)
    assert handle(ENTERED, key, snapshot) == (ENTERED, [ShowMessage("No clip")])


@pytest.mark.parametrize("pad", [3, 5])
def test_dark_column_15_pads_do_nothing(pad):
    assert handle(ENTERED, (15, pad)) == (ENTERED, [])


# Render


def render(state=ENTERED, **k):
    return sequencer.render(state, snap(replace(TARGET, **k), arms=SNAP_IN.arms))


def test_steps_with_the_selected_pitch_are_orange_others_blue():
    frame = render(notes=(note(0.0), note(0.25, pitch=50, note_id=2), note(0.5, pitch=52)))
    assert frame[(3, 1)] == Light(ORANGE)
    assert frame[(4, 1)] == Light(BLUE)
    assert frame[(5, 1)] == Light(BLUE)
    assert frame[(6, 1)] == Light(OFF)


def test_a_step_holding_the_pitch_and_others_is_orange():
    frame = render(notes=(note(0.25, pitch=50), note(0.25, note_id=2)))
    assert frame[(4, 1)] == Light(ORANGE)


def test_the_playhead_is_white_over_a_lit_step():
    frame = render(notes=(note(2.0),), is_playing=True, position=2.1)
    assert frame[(3, 2)] == Light(WHITE)


def test_the_copy_source_blinks_red_over_the_playhead():
    state = replace(ENTERED, copy=True, seq_copy_source=(8, ()))
    frame = render(state, is_playing=True, position=2.1)
    assert frame[(3, 2)] == Light(RED, Blink.FAST)


def test_steps_past_the_loop_end_are_off():
    frame = render(notes=(note(4.0),), loop_end=4.0)
    assert frame[(3, 3)] == Light(OFF)


def test_the_view_page_shows_its_steps():
    state = replace(ENTERED, seq_follow=False, seq_page=1)
    frame = render(state, notes=(note(16.25),), loop_end=32.0)
    assert frame[(4, 1)] == Light(ORANGE)


def test_follow_draws_the_playing_page():
    frame = render(notes=(note(16.25),), loop_end=32.0, is_playing=True, position=20.0)
    assert frame[(4, 1)] == Light(ORANGE)


def test_melodic_note_pads_are_keyboard_coloured():
    frame = render(replace(ENTERED, seq_pitch=60))
    assert frame[(11, 8)] == Light(WHITE)  # C2
    assert frame[(12, 8)] == Light(MAGENTA)  # C#2
    assert frame[(11, 5)] == Light(GREEN, Blink.FAST)  # C3, selected


def test_scale_mode_colours():
    # D minor: D root, E in, F in, F# out.
    scale = ScaleView(True, 2, (0, 2, 3, 5, 7, 8, 10))
    frame = render(scale=scale)
    assert frame[(13, 8)] == Light(CYAN)  # D2
    assert frame[(11, 7)] == Light(WHITE)  # E2
    assert frame[(12, 7)] == Light(WHITE)  # F2
    assert frame[(13, 7)] == Light(MAGENTA)  # F#2


def test_a_sounding_note_is_yellow_over_selected():
    frame = render(notes=(note(1.0, duration=1.0),), is_playing=True, position=1.5)
    assert frame[(11, 8)] == Light(YELLOW)


def test_a_note_not_sounding_yet_stays():
    frame = render(notes=(note(1.0, duration=1.0),), is_playing=True, position=0.5)
    assert frame[(11, 8)] == Light(GREEN, Blink.FAST)


def test_a_non_midi_target_draws_steps_and_note_pads_off():
    frame = sequencer.render(ENTERED, snap(SequencerView(track=1), arms=SNAP_IN.arms))
    for column in range(3, 15):
        for pad in range(1, 9):
            assert frame[(column, pad)] == Light(OFF)


def test_settings_lights():
    state = replace(SETTINGS, seq_rate=0.5)
    frame = render(state, loop_end=48.0, is_playing=True, position=20.0)
    assert [frame[(11, pad)] for pad in range(1, 9)] == [
        Light(CYAN), Light(BLUE), Light(CYAN), Light(CYAN),
        Light(PINK), Light(OFF), Light(OFF), Light(OFF),
    ]
    # 1/8: a page is 32 beats; the loop covers pages 1-2, the playing page 1 is in view.
    assert frame[layout.SEQ_PAGES[0]] == Light(BLUE, Blink.TEMPO)
    assert frame[layout.SEQ_PAGES[1]] == Light(CYAN)
    assert frame[layout.SEQ_PAGES[2]] == Light(OFF)
    assert all(frame[(14, pad)] == Light(OFF) for pad in range(1, 9))


def test_triplet_on_is_orange():
    assert render(replace(SETTINGS, seq_triplet=True))[layout.SEQ_TRIPLET] == Light(ORANGE)


def test_a_pinned_page_is_blue_and_the_playing_page_blinks():
    state = replace(SETTINGS, seq_follow=False, seq_page=2)
    frame = render(state, loop_end=64.0, is_playing=True, position=20.0)
    assert frame[layout.SEQ_PAGES[2]] == Light(BLUE)
    assert frame[layout.SEQ_PAGES[1]] == Light(CYAN, Blink.TEMPO)


def test_column_15():
    frame = render()
    assert [frame[(15, pad)] for pad in range(1, 9)] == [
        Light(RED), Light(PINK), Light(OFF), Light(BLUE),
        Light(OFF), Light(WHITE), Light(WHITE), Light(CYAN),
    ]
    assert render(replace(ENTERED, seq_follow=False))[layout.SEQ_FOLLOW] == Light(CYAN)
    assert render(SETTINGS)[layout.SEQ_VIEW] == Light(BLUE)


def test_column_16():
    frame = render()
    assert [frame[(16, pad)] for pad in range(1, 9)] == [
        Light(MAGENTA), Light(RED), Light(CYAN), Light(CYAN),
        Light(CYAN), Light(OFF), Light(BLUE), Light(ORANGE),
    ]


def test_column_16_shift_layer():
    frame = render(SHIFTED)
    assert [frame[(16, pad)] for pad in range(1, 9)] == [
        Light(OFF), Light(OFF), Light(YELLOW), Light(YELLOW),
        Light(OFF), Light(OFF), Light(GREEN), Light(GREEN),
    ]


def test_column_1_and_2():
    frame = render()
    assert frame[layout.MODE_PAD] == Light(MAGENTA)
    assert frame[layout.RECORD] == Light(RED)
    assert all(frame[(2, pad)] == Light(OFF) for pad in range(1, 9))


def test_a_release_after_follow_turns_the_page_toggles_the_held_step():
    snapshot = with_notes(loop_end=32.0, is_playing=True, position=15.0)
    held, _ = handle(ENTERED, (4, 1), snapshot)
    later = with_notes(loop_end=32.0, is_playing=True, position=17.0)
    state, actions = handle(held, (4, 1), later, pressed=False)
    assert state.seq_holds == ()
    assert actions == [EditNotes(2, 1, add=((48, 0.25, 0.25, 100),))]


def test_a_release_after_a_page_pin_toggles_the_held_step():
    long = with_notes(loop_end=32.0)
    held, _ = handle(ENTERED, (4, 1), long)
    pinned = replace(held, seq_follow=False, seq_page=1)
    state, actions = handle(pinned, (4, 1), long, pressed=False)
    assert state.seq_holds == ()
    assert actions == [EditNotes(2, 1, add=((48, 0.25, 0.25, 100),))]


def test_a_page_pinned_on_another_clip_doesnt_make_a_new_clip_inert():
    # Pinned on page 2 of a long clip, then back in on an empty slot.
    pinned = replace(ENTERED, seq_follow=False, seq_page=2)
    left, _ = handle(pinned, layout.SEQ)
    entered = modes.enter(left, Mode.SEQUENCER)
    _, actions = tap(entered, (3, 1), snap(EMPTY, arms=SNAP_IN.arms))
    assert actions == [EditNotes(2, 1, add=((48, 0.0, 0.25, 100),), create_length=4.0)]


def test_moving_to_another_track_shows_page_1_with_follow():
    pinned = replace(ENTERED, seq_follow=False, seq_page=2)
    synced, _ = sequencer.sync(pinned, snap(replace(TARGET, track=5), arms=SNAP_IN.arms))
    assert synced.seq_page == 0 and synced.seq_follow


# Slides (stage 2)

W = 170.625  # X_COLUMN_WIDTH
SLIDING = with_notes(
    note(0.25, velocity=100, note_id=7), note(0.3, pitch=50, velocity=60, note_id=8)
)


def hold(state=ENTERED, key=(4, 1), snapshot=SLIDING, x0=600):
    held, _ = handle(state, key, snapshot)
    held, actions, redraw = sequencer.x_axis(held, XAxis(key[0], key[1], x0))
    assert actions == [] and not redraw
    return held


def x(state, value, key=(4, 1)):
    return sequencer.x_axis(state, XAxis(key[0], key[1], value))


def test_x_rows_are_the_rows_holding_a_step():
    assert sequencer.x_rows(ENTERED) == ()
    held, _ = handle(ENTERED, (4, 1))
    held, _ = handle(held, (5, 8))
    assert sequencer.x_rows(held) == (0, 7)


def test_a_still_hold_stays_a_tap():
    held = hold()
    held, actions, redraw = x(held, 600 + 0.2 * W)
    assert actions == [] and not redraw
    _, actions = handle(held, (4, 1), SLIDING, pressed=False)
    assert actions == [EditNotes(2, 1, remove=(7,))]


def test_a_velocity_slide_up():
    held = hold()
    state, actions, redraw = x(held, 600 + W)
    assert redraw and state.seq_undo_open
    assert actions == [BeginUndoStep(), ModifyNotes(2, 1, ((7, 0.25, 116), (8, 0.3, 76)))]
    [h] = state.seq_holds
    assert h.sliding and h.used


def test_a_velocity_slide_down_clamps_at_1():
    state, actions, _ = x(hold(), 600 - 7 * W)
    assert actions[-1] == ModifyNotes(2, 1, ((7, 0.25, 1), (8, 0.3, 1)))


def test_a_velocity_slide_up_clamps_at_127():
    state, actions, _ = x(hold(), 600 + 3 * W)
    assert actions[-1] == ModifyNotes(2, 1, ((7, 0.25, 127), (8, 0.3, 108)))


def test_writes_only_on_a_change():
    state, _, _ = x(hold(), 600 + W)
    state, actions, redraw = x(state, 600 + W + 2)
    assert actions == [] and not redraw
    # Both clamped: the change of slide writes nothing.
    state, _, _ = x(state, 600 + 9 * W)
    state, actions, redraw = x(state, 600 + 10 * W)
    assert actions == [] and redraw


def test_one_undo_step_per_slide():
    state, actions, _ = x(hold(), 600 + W)
    assert actions.count(BeginUndoStep()) == 1
    state, actions, _ = x(state, 600 + 2 * W)
    assert BeginUndoStep() not in actions
    state, actions = handle(state, (4, 1), SLIDING, pressed=False)
    assert actions == [EndUndoStep()]
    assert not state.seq_undo_open and state.seq_holds == ()


def test_two_slides_share_one_undo_step():
    snapshot = with_notes(note(0.25, note_id=7), note(2.75, note_id=9))
    # The first slide starts before the second press, so that press isn't a span.
    state, actions, _ = x(hold(snapshot=snapshot), 600 + W)
    assert actions[0] == BeginUndoStep()
    state = hold(state, key=(6, 2), snapshot=snapshot, x0=900)
    state, actions, _ = x(state, 900 + W, key=(6, 2))
    assert actions == [ModifyNotes(2, 1, ((9, 2.75, 116),))]
    state, actions = handle(state, (4, 1), snapshot, pressed=False)
    assert actions == []
    state, actions = handle(state, (6, 2), snapshot, pressed=False)
    assert actions == [EndUndoStep()]


def test_a_slide_closes_a_morph_step_first():
    state, actions, _ = x(hold(replace(ENTERED, fx_undo_open=True)), 600 + W)
    assert actions[:2] == [EndUndoStep(), BeginUndoStep()]
    assert not state.fx_undo_open


def test_a_nudge_moves_the_start():
    shifted = hold(replace(ENTERED, shift=True))
    state, actions, _ = x(shifted, 600 + 3 * W)
    assert actions[-1] == ModifyNotes(
        2, 1, ((7, 0.25 + 3 * 0.25 / 8, 100), (8, 0.3 + 3 * 0.25 / 8, 60))
    )


def test_a_nudge_left_stops_at_0():
    snapshot = with_notes(note(0.03, note_id=7))
    shifted = hold(replace(ENTERED, shift=True), key=(3, 1), snapshot=snapshot)
    state, actions, _ = x(shifted, 600 - 3 * W, key=(3, 1))
    assert actions[-1] == ModifyNotes(2, 1, ((7, 0.0, 100),))
    # Further left changes nothing more.
    _, actions, _ = x(state, 600 - 4 * W, key=(3, 1))
    assert actions == []


def test_a_nudge_past_the_midpoint_moves_the_lights_to_the_next_step():
    shifted = hold(replace(ENTERED, shift=True), snapshot=with_notes(note(0.25, note_id=7)))
    _, actions, _ = x(shifted, 600 + 5 * W)
    [(note_id, start, velocity)] = actions[-1].changes
    moved = with_notes(note(start, note_id=7))
    frame = sequencer.render(ENTERED, moved)
    assert frame[(4, 1)] == Light(OFF) and frame[(5, 1)] == Light(ORANGE)


def test_a_slide_with_no_notes_stays_a_tap():
    state = hold(snapshot=SNAP_IN)
    state, actions, _ = x(state, 600 + 2 * W)
    assert actions == []
    _, actions = handle(state, (4, 1), SNAP_IN, pressed=False)
    assert actions == [EditNotes(2, 1, add=((48, 0.25, 0.25, 100),))]


def test_a_transfer_moves_the_hold_and_never_toggles():
    state, _, _ = x(hold(), 600 + W)
    state, owned = sequencer.slide(state, SlideMoved(1, 4, 5))
    assert owned and state.seq_holds[0].column == 5
    # X now comes on the new cell.
    state, actions, _ = x(state, 600 + 2 * W, key=(5, 1))
    assert actions == [ModifyNotes(2, 1, ((7, 0.25, 127), (8, 0.3, 92)))]
    state, actions = handle(state, (5, 1), SLIDING, pressed=False)
    assert actions == [EndUndoStep()]


def test_an_unowned_transfer_is_not_owned():
    assert sequencer.slide(ENTERED, SlideMoved(1, 4, 5)) == (ENTERED, False)


def test_a_span_still_works_before_a_slide():
    state = hold()
    state, actions = handle(state, (6, 1), SLIDING)
    assert actions[0].add == ((48, 0.25, 0.75, 100),)
    # The used hold no longer slides.
    state, actions, _ = x(state, 600 + 2 * W)
    assert actions == []


def test_edits_are_dropped_during_a_slide_but_the_slide_writes():
    state, _, _ = x(hold(), 600 + W)
    other, actions = tap(state, (8, 3), SLIDING)
    assert actions == []


def test_the_meter_shows_the_selected_notes_velocity():
    state, _, _ = x(hold(), 600 + W)  # 100 -> 116: 8 columns
    frame = sequencer.render(state, SLIDING)
    assert [frame[(c, 1)] for c in range(3, 11)] == [Light(ORANGE)] * 8
    state, _, _ = x(state, 600 - 2 * W)  # 100 -> 68: 5 columns
    frame = sequencer.render(state, SLIDING)
    assert [frame[(c, 1)] for c in range(3, 11)] == [Light(ORANGE)] * 5 + [Light(OFF)] * 3


def test_the_meter_shows_the_highest_other_velocity_in_blue():
    snapshot = with_notes(note(0.25, pitch=50, velocity=60, note_id=8))
    state, _, _ = x(hold(snapshot=snapshot), 600 - W)  # 60 -> 44: 3 columns
    frame = sequencer.render(state, snapshot)
    assert [frame[(c, 1)] for c in range(3, 11)] == [Light(BLUE)] * 3 + [Light(OFF)] * 5


def test_no_meter_for_a_nudge():
    shifted, _, _ = x(hold(replace(ENTERED, shift=True)), 600 + W)
    frame = sequencer.render(shifted, SLIDING)
    assert frame[(4, 1)] == Light(ORANGE) and frame[(10, 1)] == Light(OFF)


def test_leaving_mid_slide_closes_the_step():
    state, _, _ = x(hold(), 600 + W)
    left, actions = handle(state, layout.SEQ, SLIDING)
    assert actions[0] == EndUndoStep() and not left.seq_undo_open


@pytest.mark.parametrize("column", [2, 11, 14, 15])
def test_a_slide_ends_wherever_the_finger_is_lifted(column):
    # Slid off the steps: onto column 2, the note pads or column 15.
    state, _, _ = x(hold(), 600 + W)
    state, owned = sequencer.slide(state, SlideMoved(1, 4, column))
    assert owned
    state, actions = handle(state, (column, 1), SLIDING, pressed=False)
    assert actions == [EndUndoStep()]
    assert state.seq_holds == () and not state.seq_undo_open
    assert sequencer.render(state, SLIDING)[(10, 1)] == Light(OFF)


def test_a_hold_slid_onto_a_note_pad_keeps_the_selected_note():
    state, _, _ = x(hold(), 600 + W)
    state, _ = sequencer.slide(state, SlideMoved(1, 4, 11))
    state, _ = handle(state, (11, 1), SLIDING, pressed=False)
    assert state.seq_pitch == 48


# Drum Rack (stage 3)

DRUMS = replace(TARGET, drum=DrumView(9, 38, frozenset({36, 38, 42, 52})))


def drums(**k):
    return snap(replace(DRUMS, **k), arms=SNAP_IN.arms)


def test_drum_note_pads_are_live_s_rack_view():
    frame = sequencer.render(ENTERED, drums())
    assert frame[(11, 8)] == Light(WHITE)  # 36, lower bank, filled
    assert frame[(12, 8)] == Light(OFF)  # 37, empty
    assert frame[(13, 8)] == Light(GREEN, Blink.FAST)  # 38, selected in Live
    assert frame[(11, 4)] == Light(CYAN)  # 52, upper bank, filled
    assert frame[(12, 4)] == Light(OFF)


def test_a_sounding_drum_is_yellow():
    snapshot = drums(notes=(note(1.0, pitch=42),), is_playing=True, position=1.1)
    frame = sequencer.render(ENTERED, snapshot)
    assert frame[(13, 7)] == Light(YELLOW)


def test_a_drum_pad_selects_the_drum_in_live():
    state, actions = handle(ENTERED, (12, 8), drums())
    assert actions == [SelectDrumPad(2, 37)]
    assert state.seq_pitch == ENTERED.seq_pitch


def test_up_and_down_scroll_the_rack_a_row():
    assert handle(ENTERED, layout.SEQ_UP, drums())[1] == [
        SetDrumScroll(2, 10),
        ShowMessage("Pads from E1"),
    ]
    assert handle(SETTINGS, layout.SEQ_DOWN, drums())[1][0] == SetDrumScroll(2, 8)


@pytest.mark.parametrize("scroll, key", [(28, layout.SEQ_UP), (0, layout.SEQ_DOWN)])
def test_the_rack_scroll_stops_at_the_ends(scroll, key):
    snapshot = drums(drum=DrumView(scroll, 36, frozenset()))
    assert handle(ENTERED, key, snapshot) == (ENTERED, [])


def test_drum_edits_use_live_s_selected_pad():
    _, actions = tap(ENTERED, (3, 1), drums())
    assert actions == [EditNotes(2, 1, add=((38, 0.0, 0.25, 100),))]
    frame = sequencer.render(ENTERED, drums(notes=(note(0.0, pitch=38),)))
    assert frame[(3, 1)] == Light(ORANGE)


def test_a_rack_with_no_selected_pad_edits_seq_pitch():
    snapshot = drums(drum=DrumView(9, None, frozenset()))
    _, actions = tap(ENTERED, (3, 1), snapshot)
    assert actions[0].add[0][0] == ENTERED.seq_pitch


def test_unload_restores_the_saved_arms():
    arms = (False, False, True, None, False, False)
    assert sequencer.restore_arms(ENTERED, arms) == [SetArms(((1, True), (2, False)))]


def test_unload_restores_the_arms_from_linnstrument_mode():
    linnstrument, _ = handle(ENTERED, layout.MODE_PAD)
    arms = (False, False, True, None, False, False)
    assert sequencer.restore_arms(linnstrument, arms) == [SetArms(((1, True), (2, False)))]


def test_unload_outside_sequencer_mode_restores_nothing():
    assert sequencer.restore_arms(State(), (True, False)) == []
