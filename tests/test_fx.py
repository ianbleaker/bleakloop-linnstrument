import json
from dataclasses import replace

import pytest

from BleakLoop.core import engine, fx, layout, session
from BleakLoop.core.leds import BLUE, CYAN, LIME, OFF, ORANGE, WHITE, YELLOW, Blink, Light
from BleakLoop.core.model import (
    BeginUndoStep,
    EndUndoStep,
    FireScene,
    MacroView,
    PadPress,
    RacksRead,
    RackView,
    RecallFxSnapshot,
    SaveFxScenes,
    ScenesChanged,
    SaveFxSnapshots,
    SetMacros,
    SetMixer,
    SetVolume,
    ShowMessage,
    Snapshot,
    StoreFxSnapshot,
    TrackView,
)
from BleakLoop.core.modes import FxRack, Glide, Mode, Morph, MorphMacro, PendingLaunch, State
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


def test_scene_store_round_trip():
    scenes = (None, (FxRack("A", "R", 0, (0.5, 1.0)), FxRack("A", "R", 1, ())), None)
    text = fx.dump_scenes(scenes)
    assert json.loads(text) == {
        "v": 1,
        "scenes": [
            None,
            [
                {"track": "A", "rack": "R", "n": 0, "macros": [0.5, 1.0]},
                {"track": "A", "rack": "R", "n": 1, "macros": []},
            ],
            None,
        ],
    }
    assert fx.parse_scenes(text) == scenes


def test_an_empty_scene_store_round_trips():
    text = fx.dump_scenes(())
    assert json.loads(text) == {"v": 1, "scenes": []}
    assert fx.parse_scenes(text) == ()


@pytest.mark.parametrize(
    "text",
    [
        "",
        "{",
        "null",
        "[]",
        '{"v": 2, "scenes": []}',
        '{"v": 1}',
        '{"v": 1, "scenes": {}}',
        '{"v": 1, "scenes": [[{"track": "A"}]]}',
    ],
)
def test_invalid_scene_store_gives_no_scene_snapshots(text):
    assert fx.parse_scenes(text) == ()


def test_scene_snapshot_past_the_end_is_none():
    state = State(fx_scenes=(None, (FxRack("A", "R", 0, (1.0,)),)))
    assert fx.scene_snapshot(state, 0) is None
    assert fx.scene_snapshot(state, 1) == (FxRack("A", "R", 0, (1.0,)),)
    assert fx.scene_snapshot(state, 2) is None


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


def test_shift_fx_pad_toggles_the_fader_source():
    state = replace(FX, shift=True)
    assert handle(state, layout.FX) == (
        replace(state, fader_source="mapped"), [ShowMessage("Mapped FX")]
    )


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
    assert handle(FX, (11, 1))[1] == [StoreFxSnapshot(0)]
    assert handle(FX, (11, 8))[1] == [StoreFxSnapshot(7)]
    assert handle(FX, (12, 1))[1] == [StoreFxSnapshot(8)]
    assert handle(FX, (12, 8))[1] == [StoreFxSnapshot(15)]


@pytest.mark.parametrize("key", [(2, 1), (13, 7), (13, 8), (2, 8), (14, 6), (14, 8)])
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
    frame = fx.render(state, SNAP)
    assert frame[layout.FX_SLOTS[0]] == Light(CYAN)
    assert frame[layout.FX_SLOTS[9]] == Light(CYAN, Blink.TEMPO)
    assert frame[layout.FX_SLOTS[5]] == Light(CYAN, Blink.FAST)
    assert frame[layout.FX_SLOTS[1]] == Light(OFF)
    assert frame[(14, 3)] == Light(WHITE, Blink.FAST)
    for key in ((14, 1), (14, 2), (14, 4), (14, 5)):
        assert frame[key] == Light(WHITE)
    lit = {key for key, light in frame.items() if light != Light(OFF)}
    assert lit == {layout.FX_SLOTS[i] for i in (0, 5, 9)} | set(layout.FX_LENGTHS)


def test_render_column_13_is_dark_with_no_scene_snapshots():
    frame = fx.render(with_slot(FX, 2), SNAP)
    assert all(frame[(13, pad)] == Light(OFF) for pad in range(1, layout.ROWS + 1))


def test_render_landed_slot_that_was_cleared_is_dark():
    assert fx.render(replace(FX, fx_landed=2), SNAP)[SLOT_3] == Light(OFF)


def test_render_morph_target_blinks_over_landed():
    state = replace(with_slot(FX, 2), fx_landed=2, morph=Morph(2, 0.0, 4.0, 0.0))
    assert fx.render(state, SNAP)[SLOT_3] == Light(CYAN, Blink.FAST)


def test_render_under_shift_is_dark():
    state = replace(with_slot(FX, 2), shift=True, fx_length=1)
    assert set(fx.render(state, SNAP).values()) == {Light(OFF)}


def test_session_render_in_fx_mode():
    snapshot = replace(SNAP, track_count=3, scene_count=2)
    state = with_slot(FX, 2)
    frame = session.render(state, snapshot)
    assert frame[layout.FX] == Light(BLUE)
    assert frame[SLOT_3] == Light(CYAN)
    for column in layout.GRID_COLUMNS:
        if column in layout.FX_FADER_COLUMNS:
            continue
        for pad in range(1, layout.ROWS + 1):
            assert frame[(column, pad)] == fx.render(state, snapshot)[(column, pad)]


def test_session_render_fx_pad_off():
    assert session.render(State(), SNAP)[layout.FX] == Light(CYAN)


def test_session_render_shift_layer_in_fx():
    frame = session.render(replace(with_slot(FX, 2), shift=True), SNAP)
    assert frame[layout.FX] == Light(ORANGE)
    assert all(frame[(c, p)] == Light(OFF) for c in layout.GRID_COLUMNS for p in range(1, 9))


# Scene snapshots

SCENES = replace(SNAP, scene_count=8)
SCENE_2 = layout.FX_SCENE_SLOTS[1]


def with_scene(state, scene, value=STORED):
    scenes = state.fx_scenes + (None,) * (scene + 1 - len(state.fx_scenes))
    return replace(state, fx_scenes=fx._put(scenes, scene, value))


def test_empty_scene_pad_stores():
    assert handle(FX, SCENE_2, snapshot=SCENES) == (FX, [StoreFxSnapshot(1, scene=True)])


def test_stored_scene_pad_recalls_with_held_length():
    state = replace(with_scene(FX, 1), fx_length=4)
    assert handle(state, SCENE_2, snapshot=SCENES) == (
        state,
        [RecallFxSnapshot(1, 4, scene=True)],
    )


@pytest.mark.parametrize("stored", [False, True])
def test_copy_stores_over_a_scene_snapshot(stored):
    state = replace(FX, copy=True)
    if stored:
        state = with_scene(state, 1)
    assert handle(state, SCENE_2, snapshot=SCENES) == (state, [StoreFxSnapshot(1, scene=True)])


def test_delete_clears_a_scene_snapshot():
    state = with_scene(replace(FX, delete=True), 1)
    state, actions = handle(state, SCENE_2, snapshot=SCENES)
    assert state.fx_scenes == (None,) * 8
    assert actions == [
        SaveFxScenes(fx.dump_scenes((None,) * 8)),
        ShowMessage("Scene 2 snapshot cleared"),
    ]


def test_delete_on_an_empty_scene_pad_does_nothing():
    state = replace(FX, delete=True)
    assert handle(state, SCENE_2, snapshot=SCENES) == (state, [])


def test_scene_pads_follow_the_window():
    state = replace(FX, window=layout.Window(0, 2))
    assert handle(state, SCENE_2, snapshot=SCENES)[1] == [StoreFxSnapshot(3, scene=True)]


def test_a_scene_pad_past_the_last_scene_does_nothing():
    snapshot = replace(SNAP, scene_count=3)
    assert handle(FX, layout.FX_SCENE_SLOTS[2], snapshot=snapshot)[1] == [
        StoreFxSnapshot(2, scene=True)
    ]
    assert handle(FX, layout.FX_SCENE_SLOTS[3], snapshot=snapshot) == (FX, [])


def test_shift_scene_pad_does_nothing():
    state = replace(with_scene(FX, 1), shift=True)
    assert handle(state, SCENE_2, snapshot=SCENES) == (state, [])


def scene_read(state, scene, racks, recall=False, bars=None, snapshot=SCENES):
    event = RacksRead(scene, racks, recall, bars, scene=True)
    return engine.handle(state, event, snapshot)


def test_scene_store():
    racks = (rack("A", "R", 1.0, 2.0, path=P0),)
    state, actions = scene_read(FX, 2, racks)
    scenes = (None, None, fx.capture(racks)) + (None,) * 5
    assert state.fx_scenes == scenes
    assert state.fx_slots == FX.fx_slots
    assert actions == [
        SaveFxScenes(fx.dump_scenes(scenes)),
        ShowMessage("Scene 3 snapshot stored (1 rack)"),
    ]


def test_scene_store_keeps_the_other_scenes():
    state = with_scene(FX, 5)
    state, _ = scene_read(state, 1, (rack("A", "R", 1.0, path=P0),))
    assert state.fx_scenes[5] == STORED
    assert len(state.fx_scenes) == 8


def test_scene_instant_recall_lands_and_clears_the_global_landed():
    state = replace(with_scene(FX, 2, STORED_AB), fx_landed=4)
    state, actions = scene_read(state, 2, NOW_AB, recall=True, snapshot=playing(3.0))
    assert actions[-1] == ShowMessage("Scene 3 snapshot recalled")
    assert (state.fx_landed, state.fx_landed_scene, state.morph) == (None, 2, None)


def test_scene_morph_recall():
    state = with_scene(FX, 2, STORED_AB)
    snapshot = replace(playing(3.0), scene_count=8)
    state, actions = scene_read(state, 2, NOW_AB, recall=True, bars=2, snapshot=snapshot)
    assert actions == [BeginUndoStep(), ShowMessage("Scene 3 snapshot in 2 bars")]
    assert (state.morph.slot, state.morph.scene, state.morph.end_beats) == (2, True, 8.0)


def test_a_global_recall_clears_the_scene_landed():
    state = replace(with_slot(FX, 4, STORED_AB), fx_landed_scene=2)
    state, _ = racks_read(state, 4, NOW_AB, recall=True)
    assert (state.fx_landed, state.fx_landed_scene) == (4, None)


def test_a_scene_morph_lands_as_the_scene():
    state = replace(MORPHING, morph=replace(MORPH, slot=2, scene=True), fx_landed=5)
    state, _, _ = tick(state, 16.0, (0.0, 0.0, 50.0))
    assert (state.fx_landed, state.fx_landed_scene) == (None, 2)


def test_a_global_morph_lands_and_clears_the_scene_landed():
    state, _, _ = tick(replace(MORPHING, fx_landed_scene=2), 16.0, (0.0, 0.0, 50.0))
    assert (state.fx_landed, state.fx_landed_scene) == (3, None)


def test_render_scene_snapshots():
    state = with_scene(with_scene(with_scene(FX, 0), 2), 4)
    state = replace(state, fx_landed_scene=2, morph=Morph(4, 0.0, 16.0, 0.0, scene=True))
    frame = fx.render(state, SCENES)
    keys = layout.FX_SCENE_SLOTS
    assert frame[keys[0]] == Light(LIME)
    assert frame[keys[1]] == Light(OFF)
    assert frame[keys[2]] == Light(LIME, Blink.TEMPO)
    assert frame[keys[4]] == Light(LIME, Blink.FAST)
    assert frame[(13, 7)] == frame[(13, 8)] == Light(OFF)


def test_a_scene_morph_does_not_blink_the_global_slot_with_its_number():
    state = with_scene(with_slot(FX, 4), 4)
    state = replace(state, morph=Morph(4, 0.0, 16.0, 0.0, scene=True))
    frame = fx.render(state, SCENES)
    assert frame[layout.FX_SLOTS[4]] == Light(CYAN)
    assert frame[layout.FX_SCENE_SLOTS[4]] == Light(LIME, Blink.FAST)


def test_a_global_morph_does_not_blink_the_scene_pad_with_its_number():
    state = with_scene(with_slot(FX, 4), 4)
    state = replace(state, morph=Morph(4, 0.0, 16.0, 0.0))
    frame = fx.render(state, SCENES)
    assert frame[layout.FX_SLOTS[4]] == Light(CYAN, Blink.FAST)
    assert frame[layout.FX_SCENE_SLOTS[4]] == Light(LIME)


def test_render_scene_snapshots_follow_the_window():
    state = replace(with_scene(FX, 3), window=layout.Window(0, 2))
    frame = fx.render(state, SCENES)
    assert frame[layout.FX_SCENE_SLOTS[1]] == Light(LIME)
    assert frame[layout.FX_SCENE_SLOTS[3]] == Light(OFF)


def test_render_scene_snapshots_past_the_last_scene_are_dark():
    # A stale entry past the Set's end, kept until the next save, lights nothing.
    state = with_scene(FX, 3)
    assert fx.render(state, replace(SNAP, scene_count=3))[layout.FX_SCENE_SLOTS[3]] == Light(OFF)


def test_render_scene_snapshots_under_shift_are_dark():
    state = replace(with_scene(FX, 0), shift=True)
    assert fx.render(state, SCENES)[layout.FX_SCENE_SLOTS[0]] == Light(OFF)


# Scene launch


def launching(beats, quantization=4, numerator=4, denominator=4, is_playing=True):
    return replace(
        playing(beats, numerator, denominator),
        is_playing=is_playing,
        launch_quantization=quantization,
        scene_count=8,
    )


def test_launch_end_beats_unquantized():
    assert fx.launch_end_beats(launching(5.5, quantization=0)) is None


@pytest.mark.parametrize(
    "beats, quantization, signature, end",
    [
        (5.5, 4, (4, 4), 8.0),  # 1 Bar in 4/4
        (4.0, 4, (6, 8), 6.0),  # 1 Bar in 6/8: 3 beats
        (5.0, 3, (4, 4), 8.0),  # 2 Bars, mid-bar
        (13.0, 1, (4, 4), 32.0),  # 8 Bars
        (1.0, 8, (4, 4), 4 / 3),  # 1/4T
        (4.0, 4, (4, 4), 8.0),  # on a boundary: the next one
    ],
)
def test_launch_end_beats(beats, quantization, signature, end):
    snapshot = launching(beats, quantization, *signature)
    assert fx.launch_end_beats(snapshot) == pytest.approx(end)


def test_scene_launch_without_a_snapshot_does_nothing():
    assert fx.scene_launch(with_scene(FX, 1), 2, launching(5.5)) == []


def test_scene_launch_while_playing_lands_on_the_boundary_at_the_press():
    actions = fx.scene_launch(with_scene(FX, 2), 2, launching(5.5))
    assert actions == [RecallFxSnapshot(2, None, scene=True, end_beats=8.0)]


@pytest.mark.parametrize("snapshot", [launching(5.5, is_playing=False), launching(5.5, 0)])
def test_scene_launch_stopped_or_unquantized_recalls_at_once(snapshot):
    actions = fx.scene_launch(with_scene(FX, 2), 2, snapshot)
    assert actions == [RecallFxSnapshot(2, None, scene=True)]


def test_scene_launch_ignores_a_held_length():
    actions = fx.scene_launch(replace(with_scene(FX, 2), fx_length=4), 2, launching(5.5))
    assert actions == [RecallFxSnapshot(2, None, scene=True, end_beats=8.0)]


def launch_read(state, scene, end, snapshot):
    event = RacksRead(scene, NOW_AB, True, None, scene=True, end_beats=end)
    return engine.handle(state, event, snapshot)


def test_a_launch_recall_morphs_to_the_end_set_at_the_press():
    state = with_scene(FX, 2, STORED_AB)
    # The follow-up's snapshot is a little later, and its quantization changed: ignored.
    state, actions = launch_read(state, 2, 8.0, launching(5.6, quantization=1))
    assert actions == [BeginUndoStep(), ShowMessage("Scene 3 snapshot on launch")]
    assert (state.morph.start_beats, state.morph.end_beats) == (5.6, 8.0)
    assert state.morph.scene


def test_a_launch_recall_past_its_end_recalls_at_once():
    state = with_scene(FX, 2, STORED_AB)
    state, actions = launch_read(state, 2, 8.0, launching(8.0))
    assert actions[-1] == ShowMessage("Scene 3 snapshot recalled")
    assert (state.morph, state.fx_landed_scene) == (None, 2)


def test_a_launch_from_stopped_recalls_at_once_though_the_follow_up_plays():
    # FireScene started the transport before the rack read.
    state = with_scene(FX, 2, STORED_AB)
    (recall,) = fx.scene_launch(state, 2, launching(0.0, is_playing=False))
    event = RacksRead(2, NOW_AB, True, recall.bars, scene=True, end_beats=recall.end_beats)
    state, actions = engine.handle(state, event, launching(0.0))
    assert actions[-1] == ShowMessage("Scene 3 snapshot recalled")
    assert state.morph is None


def test_a_launch_recall_replaces_a_running_morph():
    state = with_scene(replace(MORPHING), 2, STORED_AB)
    state, actions = launch_read(state, 2, 8.0, launching(5.5))
    assert actions[:2] == [EndUndoStep(), BeginUndoStep()]
    assert (state.morph.slot, state.morph.scene) == (2, True)


# Scene changes in the Set


def never(i):
    return False


def always(i):
    return True


def test_scene_origins_unchanged():
    assert fx.scene_origins(["a", "b"], ["a", "b"], never) == ((0, 1), (None, None))


def test_scene_origins_insert():
    assert fx.scene_origins(["a", "b"], ["a", "x", "b"], never) == ((0, None, 1), (None,) * 3)


def test_scene_origins_delete():
    assert fx.scene_origins(["a", "b", "c"], ["a", "c"], never) == ((0, 2), (None, None))


def test_scene_origins_move():
    assert fx.scene_origins(["a", "b", "c"], ["b", "c", "a"], never) == ((1, 2, 0), (None,) * 3)


def test_scene_origins_live_drag_recreates_the_scene():
    # Live's drag of scene 3 to slot 6: the moved scene comes back as a new object.
    old = list("abcdefghijk")
    new = list("abdefXghijk")
    assert fx.scene_origins(old, new, always) == ((0, 1, 3, 4, 5, 2, 6, 7, 8, 9, 10), (None,) * 11)


def test_scene_origins_drag_of_two_scenes_pairs_them_in_order():
    old = list("abcde")
    new = list("adXYe")
    assert fx.scene_origins(old, new, never) == ((0, 3, 1, 2, 4), (None,) * 5)


def test_scene_origins_duplicate():
    asked = []

    def duplicate(i):
        asked.append(i)
        return True

    result = fx.scene_origins(["a", "b"], ["a", "a2", "b"], duplicate)
    assert result == ((0, None, 1), (None, 0, None))
    assert asked == [1]  # only new scenes are checked


def test_scene_origins_insert_at_the_top_is_never_a_duplicate():
    assert fx.scene_origins(["a"], ["x", "a"], always) == ((None, 0), (None, None))


def test_scene_origins_insert_after_an_insert_is_not_a_duplicate():
    assert fx.scene_origins(["a"], ["a", "x", "y"], always) == ((0, None, None), (None, 0, None))


def test_scene_origins_of_a_different_set_is_none():
    assert fx.scene_origins(["a", "b"], ["x", "y"], always) is None


A_SNAP = (FxRack("A", "R", 0, (1.0,)),)
B_SNAP = (FxRack("B", "R", 0, (2.0,)),)


def changed(state, origin, copies=None):
    copies = copies or (None,) * len(origin)
    return engine.handle(state, ScenesChanged(origin, copies), SNAP)


@pytest.mark.parametrize("state", [FX, State(), State(mode=Mode.SEQUENCER)])
def test_a_move_keeps_each_snapshot_in_every_mode(state):
    state = replace(state, fx_scenes=(A_SNAP, None, B_SNAP))
    state, actions = changed(state, (2, 0, 1))
    assert state.fx_scenes == (B_SNAP, A_SNAP, None)
    assert actions == [SaveFxScenes(fx.dump_scenes((B_SNAP, A_SNAP, None)))]


def test_a_delete_drops_its_snapshot():
    state, actions = changed(replace(FX, fx_scenes=(A_SNAP, B_SNAP)), (1,))
    assert state.fx_scenes == (B_SNAP,)
    assert actions == [SaveFxScenes(fx.dump_scenes((B_SNAP,)))]


def test_an_insert_starts_empty():
    state, _ = changed(replace(FX, fx_scenes=(A_SNAP, B_SNAP)), (0, None, 1))
    assert state.fx_scenes == (A_SNAP, None, B_SNAP)


def test_a_duplicate_copies_its_source():
    state, _ = changed(replace(FX, fx_scenes=(A_SNAP,)), (0, None), (None, 0))
    assert state.fx_scenes == (A_SNAP, A_SNAP)


def test_an_empty_scene_added_at_the_end_saves_nothing():
    state, actions = changed(replace(FX, fx_scenes=(A_SNAP,)), (0, None))
    assert state.fx_scenes == (A_SNAP, None)
    assert actions == []


def test_a_change_remaps_the_morph_and_the_landed_scene():
    morph = Morph(1, 0.0, 16.0, 0.0, scene=True)
    state = replace(FX, fx_scenes=(A_SNAP, B_SNAP), morph=morph, fx_landed_scene=0)
    state, _ = changed(state, (None, 0, 1))
    assert (state.morph.slot, state.fx_landed_scene) == (2, 1)


def test_a_change_remaps_a_pending_launch_and_drops_a_deleted_one():
    state = replace(FX, fx_scenes=(A_SNAP, B_SNAP), pending_launch=PendingLaunch(1, 6.0, 0.0))
    state, _ = changed(state, (None, 0, 1))
    assert state.pending_launch == PendingLaunch(2, 6.0, 0.0)
    state, _ = changed(state, (0, 1))
    assert state.pending_launch is None


def test_a_change_leaves_a_global_morph_and_landed_alone():
    state = replace(FX, fx_scenes=(A_SNAP,), morph=Morph(0, 0.0, 16.0, 0.0), fx_landed=0)
    state, _ = changed(state, (None, 0))
    assert (state.morph.slot, state.fx_landed) == (0, 0)


def test_a_deleted_morphing_scene_still_lands_and_blinks_nothing():
    morph = replace(MORPH, slot=1, scene=True)
    state = replace(MORPHING, fx_scenes=(A_SNAP, B_SNAP), morph=morph, fx_landed_scene=1)
    state, _ = changed(state, (0,))
    assert (state.morph.slot, state.fx_landed_scene) == (None, None)
    frame = fx.render(state, replace(SNAP, scene_count=1))
    blinking = [light for light in frame.values() if light.blink is Blink.FAST]
    assert blinking == []
    state, actions, _ = tick(state, 16.0, (0.0, 0.0, 50.0))
    assert state.morph is None and actions[-1] == EndUndoStep()
    assert (state.fx_landed, state.fx_landed_scene) == (None, None)


# Timed scene launch: a scene pressed with a Bars pad held


SCENE_3 = (layout.SCENE_COLUMN, 3)


def timed(state, beats, quantization=4, bars=4):
    snapshot = launching(beats, quantization)
    return handle(replace(state, fx_length=bars), SCENE_3, snapshot=snapshot)


def test_a_timed_launch_waits_for_the_bar_line():
    # 1 Bar quantization: fired halfway through the bar before, at beat 14 of bar 4.
    state, actions = timed(FX, 1.5)
    assert state.pending_launch == PendingLaunch(2, 14.0, 1.5)
    assert actions == [ShowMessage("Scene 3 in 4 bars")]


def test_a_timed_launch_morphs_its_snapshot_to_land_as_the_scene_starts():
    state, actions = timed(with_scene(FX, 2), 1.5)
    assert actions == [
        ShowMessage("Scene 3 in 4 bars"),
        RecallFxSnapshot(2, None, scene=True, end_beats=16.0),
    ]


def test_a_timed_launch_snaps_to_a_coarser_quantization():
    # 4 Bars quantization (2), 1 bar held at bar 1: the first 4-bar line after bar 2.
    state, actions = timed(with_scene(FX, 2), 1.5, quantization=2, bars=1)
    assert state.pending_launch == PendingLaunch(2, 8.0, 1.5)
    assert actions[1] == RecallFxSnapshot(2, None, scene=True, end_beats=16.0)


def test_a_timed_launch_unquantized_fires_on_the_bar_line():
    state, _ = timed(FX, 1.5, quantization=0)
    assert state.pending_launch == PendingLaunch(2, 16.0, 1.5)


def test_a_timed_launch_inside_its_last_step_fires_at_once():
    # 1 bar held past the bar's midpoint: Live's 1 Bar quantization starts it on the line.
    state, actions = timed(with_scene(FX, 2), 2.5, bars=1)
    assert state.pending_launch is None
    assert actions == [
        FireScene(2, legato=False),
        RecallFxSnapshot(2, None, scene=True, end_beats=4.0),
    ]


def test_a_timed_launch_while_stopped_launches_at_once():
    state, actions = handle(
        replace(with_scene(FX, 2), fx_length=4),
        SCENE_3,
        snapshot=launching(1.5, is_playing=False),
    )
    assert state.pending_launch is None
    assert actions == [FireScene(2, legato=False), RecallFxSnapshot(2, None, scene=True)]


def test_a_new_scene_press_replaces_a_pending_launch():
    state = replace(FX, pending_launch=PendingLaunch(0, 14.0, 1.5))
    state, actions = handle(state, SCENE_3, snapshot=launching(2.0))
    assert state.pending_launch is None
    assert actions == [FireScene(2, legato=False)]
    state, _ = timed(replace(FX, pending_launch=PendingLaunch(0, 14.0, 1.5)), 2.0)
    assert state.pending_launch.scene == 2


def test_a_legato_launch_ignores_a_held_length():
    state = replace(FX, shift=True, fx_length=4, pending_launch=PendingLaunch(0, 14.0, 1.5))
    state, actions = handle(state, SCENE_3, snapshot=launching(1.5))
    assert state.pending_launch is None
    assert actions == [FireScene(2, legato=True)]


def tick_at(state, beats, is_playing=True):
    return engine.launch_tick(state, replace(launching(beats), is_playing=is_playing))


PENDING = replace(FX, pending_launch=PendingLaunch(2, 14.0, 1.5))


def test_launch_tick_without_a_pending_launch_does_nothing():
    assert tick_at(FX, 3.0) == (FX, [], False)


def test_launch_tick_waits_then_fires():
    state, actions, redraw = tick_at(PENDING, 10.0)
    assert (state.pending_launch, actions, redraw) == (PendingLaunch(2, 14.0, 10.0), [], False)
    state, actions, redraw = tick_at(state, 14.01)
    assert (state.pending_launch, actions, redraw) == (None, [FireScene(2, legato=False)], True)


@pytest.mark.parametrize("beats, is_playing", [(10.0, False), (1.0, True)])
def test_launch_tick_cancels_on_a_stop_or_a_jump_back(beats, is_playing):
    state, actions, redraw = tick_at(PENDING, beats, is_playing)
    assert state.pending_launch is None
    assert actions == [ShowMessage("Scene 3 launch cancelled")]
    assert redraw


def test_a_pending_scene_blinks_yellow():
    frame = session.render(PENDING, launching(2.0))
    assert frame[SCENE_3] == Light(YELLOW, Blink.TEMPO)


# The split views' snapshot panel


PANEL = State(split=True, split_snapshots=True)
MIXER_PANEL = State(mixer=True, mixer_split=True, split_snapshots=True)


@pytest.mark.parametrize("state", [PANEL, MIXER_PANEL])
def test_the_panel_is_fx_modes_columns_11_to_14(state):
    assert handle(state, SLOT_3) == (state, [StoreFxSnapshot(2)])
    assert handle(state, SCENE_2, snapshot=SCENES) == (state, [StoreFxSnapshot(1, scene=True)])
    assert handle(state, (10, 3)) == (state, [])
    held, _ = handle(state, (14, 3))
    assert held.fx_length == 4
    assert handle(held, (14, 3), pressed=False)[0] == state


@pytest.mark.parametrize("state", [PANEL, MIXER_PANEL])
def test_the_panel_stores_over_and_clears_with_copy_and_delete(state):
    state = with_slot(state, 2)
    copying, _ = handle(state, layout.COPY)
    assert copying.copy
    assert handle(copying, SLOT_3)[1] == [StoreFxSnapshot(2)]
    deleting, _ = handle(state, layout.DELETE)
    assert handle(deleting, SLOT_3)[1] == [
        SaveFxSnapshots(fx.dump(fx._put(state.fx_slots, 2, None))),
        ShowMessage("Snapshot 3 cleared"),
    ]


def test_stop_leaves_the_panel_alone():
    state = with_slot(replace(PANEL, stop=True), 2)
    assert handle(state, SLOT_3)[1][0] == RecallFxSnapshot(2, None)


def test_mixer_copy_and_delete_only_hold_for_the_panel():
    state = State(mixer=True, mixer_split=True)
    assert handle(state, layout.COPY) == (state, [])
    copying, actions = handle(MIXER_PANEL, layout.COPY)
    assert actions == [ShowMessage("Copy: press a slot to overwrite")]
    copying = replace(MIXER_PANEL, copy=True)
    assert handle(copying, (2, layout.MUTE_ROW)) == (copying, [])


def test_a_timed_launch_from_the_panel():
    state, _ = timed(PANEL, 1.5)
    assert state.pending_launch == PendingLaunch(2, 14.0, 1.5)


@pytest.mark.parametrize("state", [PANEL, MIXER_PANEL])
def test_the_panel_renders_as_fx_mode_with_column_10_dark(state):
    state = with_slot(state, 2)
    frame = session.render(state, SCENES)
    assert frame[SLOT_3] == Light(CYAN)
    assert frame[(14, 1)] == Light(WHITE)
    assert all(frame[(10, pad)] == Light(OFF) for pad in range(1, 9))


def test_leaving_a_split_view_lets_go_of_a_held_length():
    state, _ = handle(replace(PANEL, fx_length=4), layout.SESSION)
    assert not state.split and state.fx_length is None
    state, _ = handle(replace(MIXER_PANEL, fx_length=4), layout.MIXER)
    assert not state.mixer_split and state.fx_length is None
