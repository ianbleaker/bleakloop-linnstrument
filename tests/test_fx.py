import json
from dataclasses import replace

import pytest

from BleakLoop.core import engine, fx, layout, session
from BleakLoop.core.layout import Window
from BleakLoop.core.leds import CYAN, OFF, WHITE, YELLOW, Blink, Light
from BleakLoop.core.model import (
    BeginUndoStep,
    EndUndoStep,
    MacroView,
    PadPress,
    RacksRead,
    RackView,
    RecallFxSnapshot,
    SaveFxSnapshots,
    SetMacros,
    SetMixer,
    SetVolume,
    ShowMessage,
    Snapshot,
    StoreFxSnapshot,
    TrackView,
)
from BleakLoop.core.modes import FxRack, Glide, Morph, MorphMacro, State
from BleakLoop.core.values import FX_TOUCH_TOLERANCE


def rack(track, name, *values, path=("track", 0, 0)):
    macros = tuple(MacroView(value, 0.0, 127.0) for value in values)
    return RackView(path, track, name, macros)


# Storage and identity


def test_duplicate_names_count_up():
    racks = (
        rack("Bass", "FX"),
        rack("Bass", "FX"),
        rack("Bass", "Drive"),
        rack("Keys", "FX"),
    )
    assert fx.keys(racks) == [
        ("Bass", "FX", 0),
        ("Bass", "FX", 1),
        ("Bass", "Drive", 0),
        ("Keys", "FX", 0),
    ]


def test_capture():
    assert fx.capture((rack("Bass", "FX", 1.0, 2.0), rack("Bass", "FX", 3.0))) == (
        FxRack("Bass", "FX", 0, (1.0, 2.0)),
        FxRack("Bass", "FX", 1, (3.0,)),
    )


def test_dump_parse_round_trip():
    slots = (None,) * 2 + ((FxRack("A", "R", 0, (0.5, 1.0)), FxRack("A", "R", 1, ())),)
    slots += (None,) * 13
    text = fx.dump(slots)
    assert json.loads(text)["v"] == 1
    assert fx.parse(text) == slots


def test_an_all_empty_store_round_trips():
    text = fx.dump((None,) * 16)
    assert fx.dump(fx.parse(text)) == text


def test_dump_format():
    slots = ((FxRack("A", "R", 0, (0.5,)),),) + (None,) * 15
    assert json.loads(fx.dump(slots)) == {
        "v": 1,
        "slots": [[{"track": "A", "rack": "R", "n": 0, "macros": [0.5]}]] + [None] * 15,
    }


@pytest.mark.parametrize(
    "text",
    [
        "",
        "{",
        "null",
        "[]",
        '{"v": 2, "slots": [' + ",".join(["null"] * 16) + "]}",
        '{"v": 1, "slots": [' + ",".join(["null"] * 15) + "]}",
        '{"v": 1}',
        '{"v": 1, "slots": [[{"track": "A"}]' + ",null" * 15 + "]}",
        '{"v": 1, "slots": [[{"track": "A", "rack": "R", "n": 0, "macros": ["x"]}]'
        + ",null" * 15
        + "]}",
    ],
)
def test_invalid_store_gives_empty_slots(text):
    assert fx.parse(text) == (None,) * 16


# FX Mode toggle and input

SNAP = Snapshot(
    is_playing=False, song_beats=0.0, tempo=120.0, metronome=False, session_view=True
)
FX = State(fx=True)
STORED = (FxRack("A", "R", 0, (1.0,)),)
SLOT_3 = layout.FX_SLOTS[2]


def press(key, pressed=True):
    return PadPress(key[0], key[1], pressed)


def handle(state, key, pressed=True, snapshot=SNAP):
    return session.handle(state, press(key, pressed), snapshot)


def with_slot(state, slot, value=STORED):
    return replace(state, fx_slots=fx._put(state.fx_slots, slot, value))


def test_toggle_on():
    state, actions = handle(State(), layout.FX)
    assert state.fx
    assert actions == [ShowMessage("FX Mode ON")]


def test_toggle_off_clears_length():
    state, actions = handle(replace(FX, fx_length=4), layout.FX)
    assert not state.fx
    assert state.fx_length is None
    assert actions == [ShowMessage("FX Mode OFF")]


def test_fx_turns_mixer_off():
    state = State(mixer=True, undo_open=True, glides=(Glide(0, 0.5, 0.6),))
    state, actions = handle(state, layout.FX)
    assert state.fx
    assert not state.mixer
    assert not state.undo_open
    assert state.glides == ()
    assert actions == [EndUndoStep(), SetMixer(False), ShowMessage("FX Mode ON")]


def test_mixer_turns_fx_off():
    state, actions = handle(replace(FX, fx_length=2), layout.MIXER)
    assert state.mixer
    assert not state.fx
    assert state.fx_length is None
    assert actions == [SetMixer(True), ShowMessage("Mixer Mode ON")]


def test_shift_fx_pad_still_moves_the_window():
    snapshot = replace(SNAP, track_count=20, scene_count=10)
    state, actions = handle(replace(FX, shift=True), layout.FX, snapshot=snapshot)
    assert state.fx
    assert state.window == Window(1, 0)
    assert actions == [ShowMessage("Tracks 2–14, Scenes 1–7")]


@pytest.mark.parametrize("key, bars", list(layout.FX_LENGTHS.items()))
def test_length_pad_held(key, bars):
    state, actions = handle(FX, key)
    assert (state.fx_length, actions) == (bars, [])
    state, actions = handle(state, key, pressed=False)
    assert (state.fx_length, actions) == (None, [])


def test_length_release_keeps_a_newer_length():
    state, _ = handle(FX, (14, 1))
    state, _ = handle(state, (14, 3))
    state, _ = handle(state, (14, 1), pressed=False)
    assert state.fx_length == 4


def test_empty_slot_stores():
    assert handle(FX, SLOT_3) == (FX, [StoreFxSnapshot(2)])


def test_full_slot_recalls_with_held_length():
    state = with_slot(replace(FX, fx_length=8), 2)
    assert handle(state, SLOT_3) == (state, [RecallFxSnapshot(2, 8)])


def test_full_slot_recalls_as_a_jump_with_no_length():
    state = with_slot(FX, 2)
    assert handle(state, SLOT_3) == (state, [RecallFxSnapshot(2, None)])


@pytest.mark.parametrize("stored", [False, True])
def test_copy_stores_into_any_slot(stored):
    state = replace(FX, copy=True)
    if stored:
        state = with_slot(state, 2)
    assert handle(state, SLOT_3) == (state, [StoreFxSnapshot(2)])


def test_delete_clears_a_full_slot():
    state = with_slot(replace(FX, delete=True), 2)
    state, actions = handle(state, SLOT_3)
    assert state.fx_slots == (None,) * 16
    assert actions == [SaveFxSnapshots(fx.dump((None,) * 16)), ShowMessage("Snapshot 3 cleared")]


def test_delete_on_an_empty_slot_does_nothing():
    state = replace(FX, delete=True)
    assert handle(state, SLOT_3) == (state, [])


def test_slot_numbers():
    assert handle(FX, (12, 1))[1] == [StoreFxSnapshot(0)]
    assert handle(FX, (12, 8))[1] == [StoreFxSnapshot(7)]
    assert handle(FX, (13, 1))[1] == [StoreFxSnapshot(8)]
    assert handle(FX, (13, 8))[1] == [StoreFxSnapshot(15)]


@pytest.mark.parametrize("key", [(2, 1), (11, 8), (2, 8), (14, 6), (14, 8)])
def test_other_grid_pads_do_nothing(key):
    assert handle(FX, key) == (FX, [])
    assert handle(FX, key, pressed=False) == (FX, [])


def test_slot_release_does_nothing():
    assert handle(FX, SLOT_3, pressed=False) == (FX, [])


def test_shift_slot_does_nothing():
    state = replace(FX, shift=True)
    assert handle(state, SLOT_3) == (state, [])


def test_copy_message_in_fx():
    state, actions = handle(FX, layout.COPY)
    assert state.copy
    assert actions == [ShowMessage("Copy: press a slot to overwrite")]


def test_delete_message_in_fx():
    state, actions = handle(FX, layout.DELETE)
    assert state.delete
    assert actions == [ShowMessage("Delete Mode ON")]


# Store and recall from RacksRead

P0 = ("track", 0, 0)
P1 = ("return", 1, 2)


def racks_read(state, slot, racks, recall=False, bars=None, snapshot=SNAP):
    return engine.handle(state, RacksRead(slot, racks, recall, bars), snapshot)


def playing(beats, numerator=4, denominator=4):
    return replace(
        SNAP,
        is_playing=True,
        song_beats=beats,
        signature_numerator=numerator,
        signature_denominator=denominator,
    )


def test_store_with_no_racks():
    assert racks_read(FX, 2, ()) == (FX, [ShowMessage("No racks to store")])


@pytest.mark.parametrize("state", [FX, State()])
def test_store(state):
    racks = (rack("A", "R", 1.0, 2.0, path=P0), rack("B", "R", 3.0, path=P1))
    state, actions = racks_read(state, 2, racks)
    slots = (None, None, fx.capture(racks)) + (None,) * 13
    assert state.fx_slots == slots
    assert actions == [SaveFxSnapshots(fx.dump(slots)), ShowMessage("Snapshot 3 stored (2 racks)")]


STORED_AB = (FxRack("A", "R", 0, (10.0, 20.0)), FxRack("B", "R", 0, (30.0,)))
NOW_AB = (rack("A", "R", 0.0, 0.0, path=P0), rack("B", "R", 0.0, path=P1))


def test_recall_jump_while_playing_with_no_length():
    state = with_slot(FX, 4, STORED_AB)
    state, actions = racks_read(state, 4, NOW_AB, recall=True, snapshot=playing(3.0))
    writes = ((P0, "R", 0, 10.0), (P0, "R", 1, 20.0), (P1, "R", 0, 30.0))
    assert actions == [
        BeginUndoStep(),
        SetMacros(writes),
        EndUndoStep(),
        ShowMessage("Snapshot 5 recalled"),
    ]
    assert (state.morph, state.fx_undo_open, state.fx_landed) == (None, False, 4)


def test_recall_jumps_while_stopped_with_a_length():
    state = with_slot(FX, 4, STORED_AB)
    state, actions = racks_read(state, 4, NOW_AB, recall=True, bars=4)
    assert actions[:3] == [
        BeginUndoStep(),
        SetMacros(((P0, "R", 0, 10.0), (P0, "R", 1, 20.0), (P1, "R", 0, 30.0))),
        EndUndoStep(),
    ]
    assert state.morph is None
    assert state.fx_landed == 4


def test_recall_clamps_targets():
    state = with_slot(FX, 0, (FxRack("A", "R", 0, (200.0, -5.0)),))
    _, actions = racks_read(state, 0, (rack("A", "R", 0.0, 0.0),), recall=True)
    assert actions[1] == SetMacros(((P0, "R", 0, 127.0), (P0, "R", 1, 0.0)))


def test_morph_start():
    state = with_slot(replace(FX, fx_landed=1), 4, STORED_AB)
    now = (
        RackView(P0, "A", "R", (MacroView(5.0, 0.0, 127.0), MacroView(1.0, 0.0, 1.0, True))),
        rack("B", "R", 7.0, path=P1),
    )
    state, actions = racks_read(state, 4, now, recall=True, bars=4, snapshot=playing(1.0))
    assert actions == [BeginUndoStep(), ShowMessage("Snapshot 5 in 4 bars")]
    assert state.fx_undo_open
    assert state.fx_landed == 1
    assert state.morph == Morph(
        slot=4,
        start_beats=1.0,
        end_beats=16.0,
        last_beats=1.0,
        macros=(
            MorphMacro(P0, "R", 0, 5.0, 10.0, False, 5.0, 127.0),
            MorphMacro(P0, "R", 1, 1.0, 1.0, True, 1.0, 1.0),
            MorphMacro(P1, "R", 0, 7.0, 30.0, False, 7.0, 127.0),
        ),
    )


@pytest.mark.parametrize(
    "beats, signature, bars, end",
    [
        (1.0, (4, 4), 4, 16.0),  # bar 1 beat 2 lands at bar 5
        (4.0, (4, 4), 1, 8.0),  # on a bar line: the next one
        (0.0, (4, 4), 2, 8.0),
        (7.9, (4, 4), 1, 8.0),
        (2.0, (6, 8), 1, 3.0),  # a 6/8 bar is 3 beats
        (4.0, (6, 8), 4, 15.0),
    ],
)
def test_morph_end_beat(beats, signature, bars, end):
    state = with_slot(FX, 0, STORED_AB)
    state, _ = racks_read(state, 0, NOW_AB, recall=True, bars=bars, snapshot=playing(beats, *signature))
    assert state.morph.end_beats == end


def test_morph_one_bar_message():
    state = with_slot(FX, 0, STORED_AB)
    _, actions = racks_read(state, 0, NOW_AB, recall=True, bars=1, snapshot=playing(0.0))
    assert actions[-1] == ShowMessage("Snapshot 1 in 1 bar")


def test_recall_with_a_missing_rack():
    state = with_slot(FX, 0, STORED_AB)
    state, actions = racks_read(state, 0, NOW_AB[:1], recall=True)
    assert actions == [
        BeginUndoStep(),
        SetMacros(((P0, "R", 0, 10.0), (P0, "R", 1, 20.0))),
        EndUndoStep(),
        ShowMessage("Snapshot 1 recalled, 1 rack not found"),
    ]


def test_recall_with_every_rack_missing():
    state = with_slot(FX, 0, STORED_AB)
    assert racks_read(state, 0, (), recall=True) == (
        state,
        [ShowMessage("Snapshot 1: nothing to recall, 2 racks not found")],
    )


@pytest.mark.parametrize(
    "stored, now, writes",
    [
        ((1.0, 2.0, 3.0), (0.0,), ((P0, "R", 0, 1.0),)),
        ((1.0,), (0.0, 0.0, 0.0), ((P0, "R", 0, 1.0),)),
    ],
)
def test_recall_with_a_macro_count_mismatch(stored, now, writes):
    state = with_slot(FX, 0, (FxRack("A", "R", 0, stored),))
    _, actions = racks_read(state, 0, (rack("A", "R", *now),), recall=True)
    assert actions[1] == SetMacros(writes)


def test_recall_matches_by_name_not_position():
    state = with_slot(FX, 0, (FxRack("B", "R", 0, (30.0,)),))
    now = (rack("A", "R", 0.0, path=P0), rack("B", "R", 0.0, path=P1))
    _, actions = racks_read(state, 0, now, recall=True)
    assert actions[1] == SetMacros(((P1, "R", 0, 30.0),))


@pytest.mark.parametrize("bars", [None, 2])
def test_a_recall_replaces_a_running_morph(bars):
    morph = Morph(1, 0.0, 16.0, 2.0)
    state = with_slot(replace(FX, morph=morph, fx_undo_open=True), 0, STORED_AB)
    state, actions = racks_read(state, 0, NOW_AB, recall=True, bars=bars, snapshot=playing(3.0))
    assert actions[:2] == [EndUndoStep(), BeginUndoStep()]
    if bars is None:
        assert actions[-2:] == [EndUndoStep(), ShowMessage("Snapshot 1 recalled")]
        assert (state.morph, state.fx_undo_open) == (None, False)
    else:
        assert state.morph.slot == 0
        assert state.fx_undo_open


def test_a_mixer_press_closes_the_morph_undo_step():
    tracks = (TrackView(index=0, name="T1"),)
    snapshot = replace(SNAP, track_count=1, scene_count=1, tracks=tracks)
    morph = Morph(1, 0.0, 16.0, 2.0)
    state = State(mixer=True, morph=morph, fx_undo_open=True)
    state, actions = handle(state, (2, 1), snapshot=snapshot)
    assert actions[:2] == [EndUndoStep(), BeginUndoStep()]
    assert isinstance(actions[2], SetVolume)
    assert state.undo_open
    assert not state.fx_undo_open
    assert state.morph == morph


# Morph tick

M_FREE = MorphMacro(P0, "R", 0, 0.0, 100.0, False, 0.0, 127.0)
M_SWITCH = MorphMacro(P0, "R", 1, 0.0, 1.0, True, 0.0, 1.0)
M_OTHER = MorphMacro(P1, "R", 0, 50.0, 10.0, False, 50.0, 127.0)
MORPH = Morph(3, 0.0, 16.0, 0.0, (M_FREE, M_SWITCH, M_OTHER))
MORPHING = replace(FX, morph=MORPH, fx_undo_open=True)


def tick(state, beats, values, is_playing=True):
    transport = replace(SNAP, is_playing=is_playing, song_beats=beats)
    return engine.fx_tick(state, transport, values)


def test_no_morph_no_tick():
    assert engine.fx_tick(FX, playing(1.0), ()) == (FX, [], False)


def test_halfway():
    state, actions, redraw = tick(MORPHING, 8.0, (0.0, 0.0, 50.0))
    assert actions == [SetMacros(((P0, "R", 0, 50.0), (P1, "R", 0, 30.0)))]
    assert not redraw
    assert state.morph.last_beats == 8.0
    assert [m.written for m in state.morph.macros] == [50.0, 0.0, 30.0]
    assert state.fx_undo_open


def test_unchanged_values_are_not_written():
    state, _, _ = tick(MORPHING, 8.0, (0.0, 0.0, 50.0))
    _, actions, _ = tick(state, 8.0, (50.0, 0.0, 30.0))
    assert actions == []


def test_quantized_macro_switches_only_on_landing():
    state = MORPHING
    for beats in (4.0, 12.0, 15.9):
        state, actions, _ = tick(state, beats, tuple(m.written for m in state.morph.macros))
        assert all(write[2] != 1 or write[0] != P0 for write in actions[0].writes)
    state, actions, redraw = tick(state, 16.0, tuple(m.written for m in state.morph.macros))
    assert actions == [
        SetMacros(((P0, "R", 0, 100.0), (P0, "R", 1, 1.0), (P1, "R", 0, 10.0))),
        EndUndoStep(),
    ]
    assert redraw


def test_lands_exactly_on_the_end_beat():
    state, actions, redraw = tick(MORPHING, 16.0, (0.0, 0.0, 50.0))
    assert actions == [
        SetMacros(((P0, "R", 0, 100.0), (P0, "R", 1, 1.0), (P1, "R", 0, 10.0))),
        EndUndoStep(),
    ]
    assert redraw
    assert (state.morph, state.fx_undo_open, state.fx_landed) == (None, False, 3)


def test_a_stop_lands():
    state, actions, redraw = tick(MORPHING, 4.0, (0.0, 0.0, 50.0), is_playing=False)
    assert actions[0] == SetMacros(((P0, "R", 0, 100.0), (P0, "R", 1, 1.0), (P1, "R", 0, 10.0)))
    assert (state.morph, state.fx_landed, redraw) == (None, 3, True)


def test_a_backward_jump_lands():
    state, _, _ = tick(MORPHING, 8.0, (0.0, 0.0, 50.0))
    state, actions, redraw = tick(state, 2.0, (50.0, 0.0, 30.0))
    assert actions[-1] == EndUndoStep()
    assert (state.morph, redraw) == (None, True)


def test_landing_after_the_step_closed_keeps_the_mixer_step():
    state = replace(MORPHING, fx_undo_open=False, undo_open=True)
    state, actions, _ = tick(state, 16.0, (0.0, 0.0, 50.0))
    assert EndUndoStep() not in actions
    assert state.undo_open


def test_a_hand_turned_macro_drops_out():
    state, actions, _ = tick(MORPHING, 8.0, (0.0, 0.0, 60.0))
    assert actions == [SetMacros(((P0, "R", 0, 50.0),))]
    assert [m.index for m in state.morph.macros] == [0, 1]
    state, actions, _ = tick(state, 16.0, (50.0, 0.0))
    assert actions[0] == SetMacros(((P0, "R", 0, 100.0), (P0, "R", 1, 1.0)))


def test_a_value_within_the_tolerance_stays():
    nudge = FX_TOUCH_TOLERANCE * 127.0 * 0.9
    state, _, _ = tick(MORPHING, 8.0, (0.0, 0.0, 50.0 + nudge))
    assert len(state.morph.macros) == 3


def test_an_unreadable_macro_drops_out():
    state, actions, _ = tick(MORPHING, 8.0, (None, 0.0, 50.0))
    assert actions == [SetMacros(((P1, "R", 0, 30.0),))]
    assert [m.path for m in state.morph.macros] == [P0, P1]
    assert state.morph.macros[0].index == 1


# Render


def test_render_slots_and_lengths():
    state = with_slot(with_slot(with_slot(replace(FX, fx_length=4), 0), 9), 5)
    state = replace(state, fx_landed=9, morph=Morph(5, 0.0, 16.0, 0.0))
    frame = fx.render(state)
    assert frame[layout.FX_SLOTS[0]] == Light(CYAN)
    assert frame[layout.FX_SLOTS[9]] == Light(CYAN, Blink.TEMPO)
    assert frame[layout.FX_SLOTS[5]] == Light(CYAN, Blink.FAST)
    assert frame[layout.FX_SLOTS[1]] == Light(OFF)
    assert frame[(14, 3)] == Light(WHITE, Blink.FAST)
    for key in ((14, 1), (14, 2), (14, 4), (14, 5)):
        assert frame[key] == Light(WHITE)
    lit = {key for key, light in frame.items() if light != Light(OFF)}
    assert lit == {layout.FX_SLOTS[i] for i in (0, 5, 9)} | set(layout.FX_LENGTHS)


def test_render_landed_slot_that_was_cleared_is_dark():
    assert fx.render(replace(FX, fx_landed=2))[SLOT_3] == Light(OFF)


def test_render_morph_target_blinks_over_landed():
    state = replace(with_slot(FX, 2), fx_landed=2, morph=Morph(2, 0.0, 4.0, 0.0))
    assert fx.render(state)[SLOT_3] == Light(CYAN, Blink.FAST)


def test_render_under_shift_is_dark():
    state = replace(with_slot(FX, 2), shift=True, fx_length=1)
    assert set(fx.render(state).values()) == {Light(OFF)}


def test_session_render_in_fx_mode():
    snapshot = replace(SNAP, track_count=3, scene_count=2)
    state = with_slot(FX, 2)
    frame = session.render(state, snapshot)
    assert frame[layout.FX] == Light(CYAN, Blink.FAST)
    assert frame[SLOT_3] == Light(CYAN)
    for column in layout.GRID_COLUMNS:
        for pad in range(1, layout.ROWS + 1):
            assert frame[(column, pad)] == fx.render(state)[(column, pad)]


def test_session_render_fx_pad_off():
    assert session.render(State(), SNAP)[layout.FX] == Light(CYAN)


def test_session_render_shift_layer_in_fx():
    frame = session.render(replace(with_slot(FX, 2), shift=True), SNAP)
    assert frame[layout.FX] == Light(YELLOW)
    assert all(frame[(c, p)] == Light(OFF) for c in layout.GRID_COLUMNS for p in range(1, 9))
