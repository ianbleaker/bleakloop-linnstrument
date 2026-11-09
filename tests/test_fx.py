import json
from dataclasses import replace

import pytest

from BleakLoop.core import engine, fx, layout, session
from BleakLoop.core.leds import BLUE, CYAN, LIME, OFF, ORANGE, PINK, WHITE, YELLOW, Blink, Light
from BleakLoop.core.model import (
    Undo,
    BindFaderRow,
    BindSelectedParameter,
    ParameterBound,
    FaderView,
    SlideMoved,
    XAxis,
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
from BleakLoop.core.modes import BindHold, BoundRead, BoundSlot, FaderBinding, FxRack, Glide, Mode, Morph, MorphMacro, PendingLaunch, SlotHold, State
from BleakLoop.core.values import FX_TOUCH_TOLERANCE, STATUS_MAX, X_COLUMN_WIDTH


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


V1_RACK = [{"track": "A", "rack": "R", "n": 0, "macros": [0.5]}]
ONE = (FxRack("A", "R", 0, (0.5,)),)


def _v1(slots, **more):
    return json.dumps({"v": 1, "slots": slots, **more})


BOUND = BoundSlot(
    (
        FaderBinding("Bass", 0, "Auto Filter", 0, 1, "Frequency"),
        FaderBinding("Main", 0, None, 0, 0, "Track Volume"),
    )
)
BOUND_JSON = {
    "bound": [
        {"track": "Bass", "tn": 0, "device": "Auto Filter", "dn": 0, "param": 1, "name": "Frequency"},
        {"track": "Main", "tn": 0, "device": None, "dn": 0, "param": 0, "name": "Track Volume"},
    ]
}


def test_dump_parse_round_trip():
    slots = (None,) * 2 + ((FxRack("A", "R", 0, (0.5, 1.0)), FxRack("A", "R", 1, ())),)
    slots += (None,) * 100 + (ONE,) + (BOUND,) + (None,) * 23
    text = fx.dump(slots)
    assert json.loads(text)["v"] == 2
    assert json.loads(text)["slots"][104] == BOUND_JSON
    assert fx.parse(text) == slots
    assert fx.readable(text)


def test_a_v1_store_loads_as_bank_1():
    text = _v1([V1_RACK] + [None] * 14 + [V1_RACK])
    assert fx.parse(text) == (ONE,) + (None,) * 14 + (ONE,) + (None,) * 112
    assert fx.readable(text)


def test_a_scoped_slot_converts_to_a_bound_slot_of_its_racks_macros():
    rack = [{"track": "Drums", "rack": "FX", "n": 1, "macros": [0.5, 0.25]}]
    text = _v1([None, rack] + [None] * 14, scoped=[1])
    expected = BoundSlot(
        (
            FaderBinding("Drums", 0, "FX", 1, 1, "Macro 1"),
            FaderBinding("Drums", 0, "FX", 1, 2, "Macro 2"),
        )
    )
    assert fx.parse(text)[1] == expected
    assert json.loads(fx.dump(fx.parse(text)))["slots"][1]["bound"][1]["param"] == 2


def test_a_v1_store_saves_as_v2_without_scoped():
    slots = fx.parse(_v1([V1_RACK] + [None] * 15, scoped=[0]))
    data = json.loads(fx.dump(slots))
    assert data["v"] == 2 and len(data["slots"]) == 128 and "scoped" not in data
    assert "bound" in data["slots"][0]


@pytest.mark.parametrize("scoped", ['"x"', "null", "{}", '[1, "0", true, -1, 128, 0.0]', "[3]"])
def test_bad_scoped_entries_are_ignored(scoped):
    slots = "[" + json.dumps(V1_RACK) + ",null" * 127 + "]"
    assert fx.parse(f'{{"v": 2, "slots": {slots}, "scoped": {scoped}}}')[0] == ONE


def test_a_v1_scoped_entry_past_bank_1_is_ignored():
    text = _v1([V1_RACK] + [None] * 15, scoped=[16])
    assert fx.parse(text)[0] == ONE


@pytest.mark.parametrize(
    "entry",
    [
        "x",
        {"track": "A", "tn": 0, "device": "D", "dn": 0, "param": 1},
        {"track": 1, "tn": 0, "device": "D", "dn": 0, "param": 1, "name": "P"},
        {"track": "A", "tn": -1, "device": "D", "dn": 0, "param": 1, "name": "P"},
        {"track": "A", "tn": 0, "device": 3, "dn": 0, "param": 1, "name": "P"},
        {"track": "A", "tn": 0, "device": "D", "dn": True, "param": 1, "name": "P"},
    ],
)
def test_bad_bound_entries_are_dropped(entry):
    good = BOUND_JSON["bound"][0]
    text = json.dumps({"v": 2, "slots": [{"bound": [entry, good]}, {"bound": [entry]}] + [None] * 126})
    slots = fx.parse(text)
    assert slots[0] == BoundSlot((BOUND.params[0],)) and slots[1] is None


def test_bound_punch_values_round_trip():
    slot = replace(BOUND, values=(0.75, None))
    text = fx.dump((slot,) + (None,) * 127)
    entries = json.loads(text)["slots"][0]["bound"]
    assert entries[0]["value"] == 0.75 and "value" not in entries[1]
    assert fx.parse(text)[0] == slot


def test_a_bound_store_without_values_loads_with_none():
    text = json.dumps({"v": 2, "slots": [BOUND_JSON] + [None] * 127})
    slot = fx.parse(text)[0]
    assert slot == BOUND and fx._values(slot) == (None, None)


@pytest.mark.parametrize("value", ["0.5", True, None, [1]])
def test_a_bad_punch_value_loads_as_none_and_keeps_the_parameter(value):
    first = dict(BOUND_JSON["bound"][0], value=value)
    second = dict(BOUND_JSON["bound"][1], value=3)
    text = json.dumps({"v": 2, "slots": [{"bound": [first, second]}] + [None] * 127})
    slot = fx.parse(text)[0]
    assert slot.params == BOUND.params and fx._values(slot) == (None, 3.0)


def test_a_dropped_entry_takes_its_value_with_it():
    bad = {"track": "A", "tn": -1, "device": "D", "dn": 0, "param": 1, "name": "P", "value": 0.1}
    second = dict(BOUND_JSON["bound"][1], value=0.9)
    text = json.dumps({"v": 2, "slots": [{"bound": [bad, second]}] + [None] * 127})
    assert fx.parse(text)[0] == BoundSlot((BOUND.params[1],), (0.9,))


def test_a_scoped_slot_converts_without_values():
    rack = [{"track": "Drums", "rack": "FX", "n": 1, "macros": [0.5, 0.25]}]
    slot = fx.parse(_v1([None, rack] + [None] * 14, scoped=[1]))[1]
    assert slot.values == () and fx._values(slot) == (None, None)


def test_an_all_empty_store_round_trips():
    text = fx.dump(EMPTY_SLOTS)
    assert fx.dump(fx.parse(text)) == text


def test_dump_format():
    slots = (ONE,) + (None,) * 127
    assert json.loads(fx.dump(slots)) == {"v": 2, "slots": [V1_RACK] + [None] * 127}


@pytest.mark.parametrize(
    "text",
    [
        "",
        "{",
        "null",
        "[]",
        '{"v": 3, "slots": [' + ",".join(["null"] * 128) + "]}",
        '{"v": 2, "slots": [' + ",".join(["null"] * 16) + "]}",
        '{"v": 2, "slots": [' + ",".join(["null"] * 127) + "]}",
        '{"v": 1, "slots": [' + ",".join(["null"] * 15) + "]}",
        '{"v": 1, "slots": [' + ",".join(["null"] * 128) + "]}",
        '{"v": 1}',
        '{"v": 1, "slots": [[{"track": "A"}]' + ",null" * 15 + "]}",
        '{"v": 2, "slots": [[{"track": "A", "rack": "R", "n": 0, "macros": ["x"]}]'
        + ",null" * 127
        + "]}",
    ],
)
def test_invalid_store_gives_empty_slots(text):
    assert fx.parse(text) == EMPTY_SLOTS
    assert not fx.readable(text)


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
EMPTY_SLOTS = (None,) * layout.FX_SNAPSHOTS
STORED = (FxRack("A", "R", 0, (1.0,)),)
SLOT_3 = layout.FX.slots[2]


def press(key, pressed=True):
    return PadPress(key[0], key[1], pressed)


def handle(state, key, pressed=True, snapshot=SNAP):
    return session.handle(state, press(key, pressed), snapshot)


def with_slot(state, slot, value=STORED):
    return replace(state, fx_slots=fx._put(state.fx_slots, slot, value))


def test_toggle_on():
    state, actions = handle(State(), layout.NAVIGATION.fx)
    assert state.fx
    assert actions == [ShowMessage("FX Mode: ON")]


def test_toggle_off_clears_length():
    state, actions = handle(replace(FX, fx_length=4), layout.NAVIGATION.fx)
    assert not state.fx
    assert state.fx_length is None
    assert actions == [ShowMessage("FX Mode: OFF")]


def test_fx_turns_mixer_off():
    state = State(mixer=True, undo_open=True, glides=(Glide(0, 0.5, 0.6),))
    state, actions = handle(state, layout.NAVIGATION.fx)
    assert state.fx
    assert not state.mixer
    assert not state.undo_open
    assert state.glides == ()
    assert actions == [EndUndoStep(), SetMixer(False), ShowMessage("FX Mode: ON")]


def test_mixer_turns_fx_off():
    state, actions = handle(replace(FX, fx_length=2), layout.NAVIGATION.mixer)
    assert state.mixer
    assert not state.fx
    assert state.fx_length is None
    assert actions == [SetMixer(True), ShowMessage("Mixer Mode: ON")]


def test_shift_fx_pad_does_nothing_in_fx_mode():
    state = replace(FX, shift=True)
    assert handle(state, layout.NAVIGATION.fx) == (state, [])


@pytest.mark.parametrize("key, bars", list(layout.FX.bars.items()))
def test_length_pad_held(key, bars):
    state, actions = handle(FX, key)
    unit = "bar" if bars == 1 else "bars"
    message = ShowMessage(f"Bars: {bars} {unit}, press a snapshot or scene")
    assert (state.fx_length, actions) == (bars, [message])
    state, actions = handle(state, key, pressed=False)
    assert (state.fx_length, actions) == (None, [])


def test_length_release_keeps_a_newer_length():
    state, _ = handle(FX, (10, 1))
    state, _ = handle(state, (10, 3))
    state, _ = handle(state, (10, 1), pressed=False)
    assert state.fx_length == 4


def test_empty_slot_stores():
    assert handle(FX, SLOT_3) == (FX, [StoreFxSnapshot(2)])


def test_full_slot_recalls_with_held_length():
    state = with_slot(replace(FX, fx_length=8), 2)
    assert handle(state, SLOT_3) == (state, [RecallFxSnapshot(2, 8)])


def test_a_stored_slot_press_holds_it_and_reads_at_once():
    state = with_slot(FX, 2)
    held, actions = handle(state, SLOT_3)
    assert held.fx_holds == (SlotHold(SLOT_3[1], SLOT_3[0], 2),)
    assert actions == [RecallFxSnapshot(2, None, hold=True)]


@pytest.mark.parametrize("stored", [False, True])
def test_copy_stores_into_any_slot(stored):
    state = replace(FX, copy=True)
    if stored:
        state = with_slot(state, 2)
    assert handle(state, SLOT_3) == (state, [StoreFxSnapshot(2)])


def test_delete_clears_a_full_slot():
    state = with_slot(replace(FX, delete=True), 2)
    state, actions = handle(state, SLOT_3)
    assert state.fx_slots == EMPTY_SLOTS
    assert actions == [SaveFxSnapshots(fx.dump(EMPTY_SLOTS)), ShowMessage("Snapshot 3 cleared")]


def test_delete_on_an_empty_slot_does_nothing():
    state = replace(FX, delete=True)
    assert handle(state, SLOT_3) == (state, [])


def test_slot_numbers():
    assert handle(FX, (11, 1))[1] == [StoreFxSnapshot(0)]
    assert handle(FX, (11, 8))[1] == [StoreFxSnapshot(7)]
    assert handle(FX, (12, 1))[1] == [StoreFxSnapshot(8)]
    assert handle(FX, (12, 8))[1] == [StoreFxSnapshot(15)]


@pytest.mark.parametrize("key", [(2, 1), (10, 6), (10, 8), (2, 8), (14, 7), (14, 8)])
def test_other_grid_pads_do_nothing(key):
    assert handle(FX, key) == (FX, [])
    assert handle(FX, key, pressed=False) == (FX, [])


def test_banks_start_on_bank_1():
    assert FX.fx_bank == 0


def test_a_bank_press_selects_it():
    state, actions = handle(FX, (13, 3))
    assert state.fx_bank == 2
    assert actions == [ShowMessage("Bank 3")]
    assert handle(state, (13, 3), pressed=False) == (state, [])


def test_render_lights_the_selected_bank_orange_and_the_others_dark():
    frame = fx.render(replace(FX, fx_bank=4), SNAP)
    assert [frame[(13, pad)] for pad in range(1, 9)] == [Light(OFF)] * 4 + [Light(ORANGE)] + [Light(OFF)] * 3


def test_slot_release_does_nothing():
    assert handle(FX, SLOT_3, pressed=False) == (FX, [])


def test_copy_message_in_fx():
    state, actions = handle(FX, layout.NAVIGATION.copy)
    assert state.copy
    assert actions == [ShowMessage("Copy: press a slot to overwrite")]


def test_delete_message_in_fx():
    state, actions = handle(FX, layout.NAVIGATION.delete)
    assert state.delete
    assert actions == [ShowMessage("Delete: pick a clip or scene")]


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
    slots = (None, None, fx.capture(racks)) + (None,) * 125
    assert state.fx_slots == slots
    assert actions == [SaveFxSnapshots(fx.dump(slots)), ShowMessage("Snapshot 3 stored (2 racks)")]


STORED_AB = (FxRack("A", "R", 0, (10.0, 20.0)), FxRack("B", "R", 0, (30.0,)))
NOW_AB = (rack("A", "R", 0.0, 0.0, path=P0), rack("B", "R", 0.0, path=P1))


# Banks: a slot is the global index bank * 16 + slot.

BANK_2 = replace(FX, fx_bank=1)


def test_an_empty_slot_in_bank_2_stores_its_global_slot():
    assert handle(BANK_2, SLOT_3) == (BANK_2, [StoreFxSnapshot(18)])


def test_a_store_in_bank_2_names_the_bank():
    racks = (rack("A", "R", 1.0, path=P0),)
    state, actions = racks_read(BANK_2, 18, racks)
    assert state.fx_slots[18] == fx.capture(racks) and state.fx_slots[2] is None
    assert actions[1:] == [ShowMessage("Snapshot 3, bank 2 stored (1 rack)")]


def test_a_stored_slot_in_bank_2_recalls_its_global_slot():
    state = with_slot(BANK_2, 18)
    assert handle(state, SLOT_3)[1] == [RecallFxSnapshot(18, None, hold=True)]


def test_a_recall_in_bank_2_names_the_bank():
    state = with_slot(BANK_2, 18, STORED_AB)
    _, actions = racks_read(state, 18, NOW_AB, recall=True)
    assert actions[-1] == ShowMessage("Snapshot 3, bank 2 recalled")


def test_delete_clears_the_slot_in_the_selected_bank_only():
    state = with_slot(with_slot(replace(BANK_2, delete=True), 18), 2)
    state, actions = handle(state, SLOT_3)
    assert state.fx_slots[18] is None and state.fx_slots[2] == STORED
    assert actions[1:] == [ShowMessage("Snapshot 3, bank 2 cleared")]


def test_banks_show_their_own_slots():
    state = with_slot(FX, 2)
    assert fx.render(state, SNAP)[SLOT_3] == Light(CYAN)
    assert fx.render(replace(state, fx_bank=1), SNAP)[SLOT_3] == Light(OFF)


def test_switching_bank_mid_morph_keeps_the_morph_and_its_blink_in_its_bank():
    state = replace(with_slot(with_slot(FX, 2), 18), morph=Morph(2, 0.0, 16.0, 0.0))
    state, _ = handle(state, (13, 2))
    assert state.morph == Morph(2, 0.0, 16.0, 0.0)
    assert fx.render(state, SNAP)[SLOT_3] == Light(CYAN)
    state, _ = handle(state, (13, 1))
    assert fx.render(state, SNAP)[SLOT_3] == Light(CYAN, Blink.FAST)


def test_the_landed_blink_stays_in_its_bank():
    state = replace(with_slot(with_slot(FX, 2), 18), fx_landed=18)
    assert fx.render(state, SNAP)[SLOT_3] == Light(CYAN)
    assert fx.render(replace(state, fx_bank=1), SNAP)[SLOT_3] == Light(CYAN, Blink.TEMPO)


def test_a_recall_landing_in_bank_2_blinks_its_global_slot():
    state = with_slot(BANK_2, 18, STORED_AB)
    state, _ = racks_read(state, 18, NOW_AB, recall=True)
    assert state.fx_landed == 18




def test_recall_jump_while_playing_with_no_length():
    state = with_slot(FX, 4, STORED_AB)
    state, actions = racks_read(state, 4, NOW_AB, recall=True, snapshot=playing(3.0))
    writes = (((P0, "R", 0), 10.0), ((P0, "R", 1), 20.0), ((P1, "R", 0), 30.0))
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
        SetMacros((((P0, "R", 0), 10.0), ((P0, "R", 1), 20.0), ((P1, "R", 0), 30.0))),
        EndUndoStep(),
    ]
    assert state.morph is None
    assert state.fx_landed == 4


def test_delete_clears_a_bound_slot():
    state, actions = handle(replace(with_slot(FX, 4, BOUND), delete=True), layout.FX.slots[4])
    assert state.fx_slots[4] is None
    assert actions == [SaveFxSnapshots(fx.dump(EMPTY_SLOTS)), ShowMessage("Snapshot 5 cleared")]


def test_a_set_wide_store_over_a_bound_slot_replaces_it():
    state, _ = racks_read(with_slot(FX, 2, BOUND), 2, (rack("A", "R", 1.0, path=P0),))
    assert state.fx_slots[2] == (FxRack("A", "R", 0, (1.0,)),)


def test_recall_clamps_targets():
    state = with_slot(FX, 0, (FxRack("A", "R", 0, (200.0, -5.0)),))
    _, actions = racks_read(state, 0, (rack("A", "R", 0.0, 0.0),), recall=True)
    assert actions[1] == SetMacros((((P0, "R", 0), 127.0), ((P0, "R", 1), 0.0)))


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
            MorphMacro((P0, "R", 0), 5.0, 10.0, False, 5.0, 127.0),
            MorphMacro((P0, "R", 1), 1.0, 1.0, True, 1.0, 1.0),
            MorphMacro((P1, "R", 0), 7.0, 30.0, False, 7.0, 127.0),
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
        SetMacros((((P0, "R", 0), 10.0), ((P0, "R", 1), 20.0))),
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
        ((1.0, 2.0, 3.0), (0.0,), (((P0, "R", 0), 1.0),)),
        ((1.0,), (0.0, 0.0, 0.0), (((P0, "R", 0), 1.0),)),
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
    assert actions[1] == SetMacros((((P1, "R", 0), 30.0),))


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

M_FREE = MorphMacro((P0, "R", 0), 0.0, 100.0, False, 0.0, 127.0)
M_SWITCH = MorphMacro((P0, "R", 1), 0.0, 1.0, True, 0.0, 1.0)
M_OTHER = MorphMacro((P1, "R", 0), 50.0, 10.0, False, 50.0, 127.0)
MORPH = Morph(3, 0.0, 16.0, 0.0, (M_FREE, M_SWITCH, M_OTHER))
MORPHING = replace(FX, morph=MORPH, fx_undo_open=True)


def tick(state, beats, values, is_playing=True):
    transport = replace(SNAP, is_playing=is_playing, song_beats=beats)
    return engine.fx_tick(state, transport, values)


def test_no_morph_no_tick():
    assert engine.fx_tick(FX, playing(1.0), ()) == (FX, [], False)


def test_halfway():
    state, actions, redraw = tick(MORPHING, 8.0, (0.0, 0.0, 50.0))
    assert actions == [SetMacros((((P0, "R", 0), 50.0), ((P1, "R", 0), 30.0)))]
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
        assert all(key != (P0, "R", 1) for key, _ in actions[0].writes)
    state, actions, redraw = tick(state, 16.0, tuple(m.written for m in state.morph.macros))
    assert actions == [
        SetMacros((((P0, "R", 0), 100.0), ((P0, "R", 1), 1.0), ((P1, "R", 0), 10.0))),
        EndUndoStep(),
    ]
    assert redraw


def test_lands_exactly_on_the_end_beat():
    state, actions, redraw = tick(MORPHING, 16.0, (0.0, 0.0, 50.0))
    assert actions == [
        SetMacros((((P0, "R", 0), 100.0), ((P0, "R", 1), 1.0), ((P1, "R", 0), 10.0))),
        EndUndoStep(),
    ]
    assert redraw
    assert (state.morph, state.fx_undo_open, state.fx_landed) == (None, False, 3)


def test_a_stop_lands():
    state, actions, redraw = tick(MORPHING, 4.0, (0.0, 0.0, 50.0), is_playing=False)
    assert actions[0] == SetMacros((((P0, "R", 0), 100.0), ((P0, "R", 1), 1.0), ((P1, "R", 0), 10.0)))
    assert (state.morph, state.fx_landed, redraw) == (None, 3, True)


def test_a_backward_jump_lands():
    state, _, _ = tick(MORPHING, 8.0, (0.0, 0.0, 50.0))
    state, actions, redraw = tick(state, 2.0, (50.0, 0.0, 30.0))
    assert actions[-1] == EndUndoStep()
    assert (state.morph, redraw) == (None, True)


# The Arrangement loop over beats 0-16: song time wraps from 16 back to 0.
def looped(beats, is_playing=True):
    return replace(SNAP, is_playing=is_playing, song_beats=beats, loop=True, loop_length=16.0)


def loop_tick(state, beats, values=(0.0, 0.0, 50.0), triggered=None):
    return engine.fx_tick(state, looped(beats), values, triggered)


def written(state):
    return tuple(m.written for m in state.morph.macros)


def test_a_loop_wrap_carries_the_morph_on():
    state = replace(MORPHING, morph=replace(MORPH, start_beats=8.0, end_beats=24.0, last_beats=15.9))
    state, actions, redraw = loop_tick(state, 0.0)
    assert actions == [SetMacros((((P0, "R", 0), 50.0), ((P1, "R", 0), 30.0)))]
    assert not redraw
    morph = state.morph
    assert (morph.start_beats, morph.end_beats, morph.last_beats) == (-8.0, 8.0, 0.0)


def test_a_late_tick_after_a_loop_wrap_counts_the_beats_both_sides():
    state = replace(MORPHING, morph=replace(MORPH, start_beats=8.0, end_beats=24.0, last_beats=15.5))
    state, _, _ = loop_tick(state, 0.5)
    assert (state.morph.start_beats, state.morph.end_beats) == (-8.0, 8.0)


def test_a_morph_longer_than_the_loop_lands_after_its_length():
    state = replace(MORPHING, morph=replace(MORPH, end_beats=32.0))
    for beats in (8.0, 15.9, 0.0, 8.0, 15.9):
        state, _, redraw = loop_tick(state, beats, written(state))
        assert not redraw
    state, actions, redraw = loop_tick(state, 0.0, written(state))
    assert actions[-1] == EndUndoStep()
    assert (state.morph, state.fx_landed, redraw) == (None, 3, True)


@pytest.mark.parametrize("last, now", [(12.0, 4.0), (15.9, 3.0)])
def test_a_backward_jump_inside_the_loop_lands(last, now):
    state = replace(MORPHING, morph=replace(MORPH, last_beats=last))
    state, actions, redraw = loop_tick(state, now)
    assert actions[-1] == EndUndoStep()
    assert (state.morph, redraw) == (None, True)


LAUNCH = replace(MORPH, end_beats=8.0, scene=True, launch=True)
LAUNCH_MORPH = replace(MORPHING, morph=replace(LAUNCH, wrapped=True))


def test_a_loop_wrap_marks_the_morph_wrapped():
    state = replace(MORPHING, morph=replace(LAUNCH, end_beats=24.0, last_beats=15.9))
    state, _, _ = loop_tick(state, 0.0, triggered=True)
    assert state.morph.wrapped and state.morph.triggered


def test_without_a_wrap_a_launch_morph_lands_on_its_end_whatever_the_trigger():
    # Another scene's launch cancels this one's wait: the morph carries on to its end.
    state = replace(MORPHING, morph=LAUNCH)
    state, _, _ = loop_tick(state, 4.0, triggered=True)
    state, _, redraw = loop_tick(state, 6.0, written(state), triggered=False)
    assert not redraw
    state, _, redraw = loop_tick(state, 8.0, written(state), triggered=True)
    assert (state.morph, redraw) == (None, True)


def test_after_a_wrap_a_launch_morph_lands_as_the_scene_starts():
    state, _, redraw = loop_tick(LAUNCH_MORPH, 4.0, triggered=True)
    assert state.morph.triggered and not redraw
    state, _, redraw = loop_tick(state, 7.99, written(state), triggered=True)
    assert not redraw
    state, actions, redraw = loop_tick(state, 8.01, written(state), triggered=False)
    assert actions[0] == SetMacros((((P0, "R", 0), 100.0), ((P0, "R", 1), 1.0), ((P1, "R", 0), 10.0)))
    assert (state.morph, state.fx_landed_scene, redraw) == (None, 3, True)


def test_after_a_wrap_a_launch_morph_holds_at_its_targets_while_the_scene_starts_late():
    state, _, _ = loop_tick(LAUNCH_MORPH, 4.0, triggered=True)
    state, actions, redraw = loop_tick(state, 9.0, (50.0, 0.0, 30.0), triggered=True)
    assert actions == [SetMacros((((P0, "R", 0), 100.0), ((P1, "R", 0), 10.0)))]
    assert not redraw
    assert state.morph is not None


def test_after_a_wrap_another_scene_taking_the_wait_over_leaves_the_morph_alone():
    state, _, _ = loop_tick(LAUNCH_MORPH, 4.0, triggered=True)
    state, _, redraw = loop_tick(state, 6.0, written(state), triggered=None)
    assert not redraw
    assert not state.morph.triggered
    state, _, redraw = loop_tick(state, 8.0, written(state), triggered=None)
    assert (state.morph, redraw) == (None, True)


def test_after_a_wrap_a_launch_morph_lands_early_if_the_scene_starts_early():
    state, _, _ = loop_tick(LAUNCH_MORPH, 4.0, triggered=True)
    state, _, redraw = loop_tick(state, 6.0, triggered=False)
    assert (state.morph, redraw) == (None, True)


@pytest.mark.parametrize("triggered", [False, None])
def test_a_launch_morph_never_seen_waiting_lands_on_its_end(triggered):
    state, _, redraw = loop_tick(LAUNCH_MORPH, 7.99, triggered=triggered)
    assert not redraw
    state, _, redraw = loop_tick(state, 8.0, triggered=triggered)
    assert (state.morph, redraw) == (None, True)


def test_a_launch_morph_still_lands_on_a_stop():
    state, _, _ = loop_tick(LAUNCH_MORPH, 4.0, triggered=True)
    state, _, redraw = engine.fx_tick(state, looped(5.0, is_playing=False), (0.0, 0.0, 50.0), True)
    assert (state.morph, redraw) == (None, True)


def test_landing_after_the_step_closed_keeps_the_mixer_step():
    state = replace(MORPHING, fx_undo_open=False, undo_open=True)
    state, actions, _ = tick(state, 16.0, (0.0, 0.0, 50.0))
    assert EndUndoStep() not in actions
    assert state.undo_open


def test_a_hand_turned_macro_drops_out():
    state, actions, _ = tick(MORPHING, 8.0, (0.0, 0.0, 60.0))
    assert actions == [SetMacros((((P0, "R", 0), 50.0),))]
    assert [m.key[2] for m in state.morph.macros] == [0, 1]
    state, actions, _ = tick(state, 16.0, (50.0, 0.0))
    assert actions[0] == SetMacros((((P0, "R", 0), 100.0), ((P0, "R", 1), 1.0)))


def test_a_value_within_the_tolerance_stays():
    nudge = FX_TOUCH_TOLERANCE * 127.0 * 0.9
    state, _, _ = tick(MORPHING, 8.0, (0.0, 0.0, 50.0 + nudge))
    assert len(state.morph.macros) == 3


def test_an_unreadable_macro_drops_out():
    state, actions, _ = tick(MORPHING, 8.0, (None, 0.0, 50.0))
    assert actions == [SetMacros((((P1, "R", 0), 30.0),))]
    assert [m.key[0] for m in state.morph.macros] == [P0, P1]
    assert state.morph.macros[0].key[2] == 1


# Held slots: a tap recalls on the lift (B3)

AB_TARGETS = ((((P0, "R", 0), 10.0), ((P0, "R", 1), 20.0), ((P1, "R", 0), 30.0)))
AB = with_slot(FX, 2, STORED_AB)


def hold_read(state, slot=2, racks=NOW_AB):
    return engine.handle(state, RacksRead(slot, racks, True, hold=True), SNAP)


def lift(state, key=SLOT_3):
    return handle(state, key, pressed=False)


def held(state, **changes):
    (hold,) = state.fx_holds
    return replace(state, fx_holds=(replace(hold, **changes),))


def test_a_tap_recalls_on_the_lift():
    state, _ = handle(AB, SLOT_3)
    state, actions = hold_read(state)
    assert actions == [] and state.fx_holds[0].read is not None
    state, actions = lift(state)
    assert actions == [
        BeginUndoStep(),
        SetMacros(AB_TARGETS),
        EndUndoStep(),
        ShowMessage("Snapshot 3 recalled"),
    ]
    assert state.fx_holds == () and state.fx_landed == 2


def test_a_lift_before_the_read_lands_taps_when_it_lands():
    state, _ = handle(AB, SLOT_3)
    state, actions = lift(state)
    assert actions == [] and state.fx_holds[0].lifted
    state, actions = hold_read(state)
    assert actions[1] == SetMacros(AB_TARGETS)
    assert actions[-1] == ShowMessage("Snapshot 3 recalled")
    assert state.fx_holds == ()


def test_a_slide_before_the_read_lands_blends_when_it_lands():
    state, _ = handle(AB, SLOT_3)
    state = held(state, x0=100, slid=True, f=0.5, order=1)
    state, actions = hold_read(state)
    assert actions == [
        BeginUndoStep(),
        SetMacros((((P0, "R", 0), 5.0), ((P0, "R", 1), 10.0), ((P1, "R", 0), 15.0))),
    ]
    assert state.fx_holds[0].wrote and state.fx_slide_undo_open


def test_a_lift_after_a_slide_before_the_read_lands_writes_the_final_blend_and_keeps_it():
    state, _ = handle(AB, SLOT_3)
    state = held(state, x0=100, slid=True, f=0.6, order=1, lifted=True)
    state, actions = hold_read(state)
    assert actions == [
        BeginUndoStep(),
        SetMacros((((P0, "R", 0), 6.0), ((P0, "R", 1), 12.0), ((P1, "R", 0), 18.0))),
        EndUndoStep(),
        ShowMessage("Snapshot 3 at 60%"),
    ]
    assert state.fx_holds == () and not state.fx_slide_undo_open and state.fx_slide_params == ()


def test_a_read_with_nothing_found_taps_a_refusal():
    state, _ = handle(AB, SLOT_3)
    state, _ = hold_read(state, racks=())
    state, actions = lift(state)
    assert actions == [ShowMessage("Snapshot 3: nothing to recall, 2 racks not found")]


def test_bars_held_recalls_on_the_press_as_before():
    state = replace(AB, fx_length=4)
    assert handle(state, SLOT_3) == (state, [RecallFxSnapshot(2, 4)])


def test_a_scene_snapshot_recalls_on_the_press_as_before():
    state = with_scene(FX, 1)
    assert handle(state, SCENE_2, snapshot=SCENES)[1] == [RecallFxSnapshot(1, None, scene=True)]


def test_a_second_slot_press_on_a_held_row_is_ignored():
    # Slot 11 is on slot 3's row, in column 12.
    state, _ = handle(with_slot(AB, 10), SLOT_3)
    assert layout.FX.slots[10][1] == SLOT_3[1]
    assert handle(state, layout.FX.slots[10]) == (state, [])


def test_a_tap_cancels_a_running_morph_and_closes_its_step():
    state, _ = handle(replace(AB, morph=Morph(5, 0.0, 16.0, 0.0), fx_undo_open=True), SLOT_3)
    state, _ = hold_read(state)
    state, actions = lift(state)
    assert actions[:2] == [EndUndoStep(), BeginUndoStep()]
    assert state.morph is None and not state.fx_undo_open


# Held slots: X and capture (B4)

ROW = SLOT_3[1]


def centre(column):
    return X_COLUMN_WIDTH * (column - 0.5)


def x(state, column, value, pad=ROW):
    return engine.x_axis(state, XAxis(column, pad, round(value)))


def slide_to(state, *columns, pad=ROW):
    # The finger crosses each column in turn; every slide's actions.
    actions = []
    for to in columns:
        (hold,) = [h for h in state.fx_holds if h.pad == pad]
        state, more = engine.slide(state, SlideMoved(pad, hold.column, to), SNAP)
        actions += more
    return state, actions


def holding_read(state=AB):
    state, _ = handle(state, SLOT_3)
    state, _ = hold_read(state)
    return state


def test_the_first_x_sets_the_zero():
    state, actions, _ = x(holding_read(), 11, centre(11))
    assert actions == [] and state.fx_holds[0].x0 == round(centre(11))


def test_a_slide_right_over_the_panel_and_back_fires_nothing_and_ends_where_it_lifts():
    state, _, _ = x(holding_read(), 11, centre(11))
    state, actions = slide_to(state, 12, 13, 14, 15, 16)
    assert actions == [] and state.fx_holds[0].column == 16
    state, actions = slide_to(state, 15, 14, 13, 12, 11, 10)
    assert actions == [] and state.fx_holds[0].column == 10
    # A release where the finger started isn't the hold's: the finger is on column 10.
    assert lift(state, (11, ROW)) == (state, [])
    state, _, _ = x(state, 10, centre(10))
    state, actions = lift(state, (10, ROW))
    assert state.fx_holds == () and actions[-1] == ShowMessage("Snapshot 3 at 0%")


def test_a_release_at_column_16_ends_the_hold():
    state, _, _ = x(holding_read(), 11, centre(11))
    state, _ = slide_to(state, 12, 13, 14, 15, 16)
    state, _, _ = x(state, 16, centre(16))
    state, actions = lift(state, (16, ROW))
    assert state.fx_holds == () and actions[-1] == ShowMessage("Snapshot 3 at 100%")


def test_a_sub_threshold_wobble_across_a_cell_edge_still_taps():
    edge = X_COLUMN_WIDTH * 11 - 10
    state, _, _ = x(holding_read(), 11, edge)
    state, actions = slide_to(state, 12)
    assert actions == []
    state, actions, _ = x(state, 12, edge + 0.2 * X_COLUMN_WIDTH)
    assert actions == [] and not state.fx_holds[0].slid
    state, actions = lift(state, (12, ROW))
    assert actions[-1] == ShowMessage("Snapshot 3 recalled")


def test_a_quarter_column_left_is_a_slide_at_0():
    state, _, _ = x(holding_read(), 11, centre(11))
    state, _, redraw = x(state, 11, centre(11) - 0.3 * X_COLUMN_WIDTH)
    assert state.fx_holds[0].slid and state.fx_holds[0].f == 0.0 and redraw
    state, actions = lift(state, (11, ROW))
    assert actions[-1] == ShowMessage("Snapshot 3 at 0%")


def test_x_from_another_finger_on_the_row_is_not_the_holds():
    state, _, _ = x(holding_read(), 11, centre(11))
    assert not fx.holding(state, XAxis(14, ROW, 0))


def test_a_held_slots_row_wants_x_in_the_split_view():
    state, _ = handle(with_slot(PANEL, 2, STORED_AB), SLOT_3)
    assert engine.x_rows(PANEL) == ()
    assert engine.x_rows(state) == (layout.device_row(ROW),)


def test_leaving_fx_mode_mid_slide_drops_the_hold_and_closes_the_step():
    state, _, _ = x(holding_read(), 11, centre(11))
    state, _, _ = x(state, 11, centre(12))
    assert state.fx_slide_undo_open
    state, actions = handle(state, layout.NAVIGATION.fx)
    assert state.fx_holds == () and state.fx_slide_params == () and not state.fx_slide_undo_open
    assert actions.count(EndUndoStep()) == 1
    # Back in FX Mode, a fader touch opens its own step.
    state, _ = handle(state, layout.NAVIGATION.fx)
    view = FaderView("Macro 1", 0.0, 0.0, 127.0)
    faders_snap = replace(SNAP, faders=(view,) * 8)
    state, _ = session.handle(state, PadPress(5, 1, True), faders_snap)
    _, actions, _ = engine.x_axis(state, XAxis(5, 1, round(centre(7))))
    assert actions[0] == BeginUndoStep()


# Held slots: the blend (B5)


def sliding(state=AB, x0=0):
    # Holding slot 3 with its read in, its zero at x0.
    state, _, _ = x(holding_read(state), 11, x0)
    return state


def at(columns):
    return round(columns * X_COLUMN_WIDTH)


def test_a_slide_blends_from_the_press_values():
    state, actions, _ = x(sliding(), 11, at(2))
    f = at(2) / X_COLUMN_WIDTH / 4
    assert actions == [
        BeginUndoStep(),
        SetMacros(tuple((key, target * f) for key, target in AB_TARGETS)),
    ]
    assert state.fx_holds[0].f == f


@pytest.mark.parametrize("columns, f", [(9.0, 1.0), (-3.0, 0.0)])
def test_the_blend_clamps_at_both_ends(columns, f):
    state, _, _ = x(sliding(), 11, at(1))
    state, _, _ = x(state, 11, at(columns))
    assert state.fx_holds[0].f == f
    assert {p.written for p in state.fx_slide_params} == ({0.0} if f == 0 else {10.0, 20.0, 30.0})


def test_moving_back_left_lowers_the_blend():
    state, _, _ = x(sliding(), 11, at(4))
    state, actions, _ = x(state, 11, at(1))
    assert actions == [SetMacros(tuple((key, target * at(1) / X_COLUMN_WIDTH / 4) for key, target in AB_TARGETS))]


def test_a_quantized_macro_takes_the_nearest_step_both_ways():
    switch = rack("A", "R", 0.0, path=P0)
    switch = replace(switch, macros=(MacroView(0.0, 0.0, 1.0, is_quantized=True),))
    state = with_slot(FX, 2, (FxRack("A", "R", 0, (1.0,)),))
    state, _ = handle(state, SLOT_3)
    state, _ = hold_read(state, racks=(switch,))
    state, _, _ = x(state, 11, 0)
    state, actions, _ = x(state, 11, at(1.9))
    assert SetMacros((((P0, "R", 0), 1.0),)) not in actions
    state, actions, _ = x(state, 11, at(2.1))
    assert actions[-1] == SetMacros((((P0, "R", 0), 1.0),))
    state, actions, _ = x(state, 11, at(1.9))
    assert actions == [SetMacros((((P0, "R", 0), 0.0),))]


def test_the_lift_keeps_the_values_and_closes_the_step():
    state, _, _ = x(sliding(), 11, at(2.4))
    state, actions = lift(state, (11, ROW))
    assert actions == [EndUndoStep(), ShowMessage("Snapshot 3 at 60%")]
    assert state.fx_holds == () and state.fx_slide_params == () and not state.fx_slide_undo_open


def test_the_first_write_closes_a_fader_step_and_cancels_a_morph():
    state = replace(AB, fader_undo_open=True, fx_undo_open=True, morph=Morph(5, 0.0, 16.0, 0.0))
    state, actions, _ = x(sliding(state), 11, at(2))
    assert actions[:3] == [EndUndoStep(), EndUndoStep(), BeginUndoStep()]
    assert state.morph is None and not state.fx_undo_open and not state.fader_undo_open


OTHER_SLOT = layout.FX.slots[0]  # slot 1, on another row


def test_a_tap_on_another_row_mid_slide_takes_its_parameters_and_joins_the_step():
    state = with_slot(sliding(), 0, (FxRack("A", "R", 0, (99.0,)),))
    state, _, _ = x(state, 11, at(2))
    state, _ = handle(state, OTHER_SLOT)
    state, _ = hold_read(state, slot=0)
    state, actions = lift(state, OTHER_SLOT)
    assert actions == [SetMacros((((P0, "R", 0), 99.0),)), ShowMessage("Snapshot 1 recalled")]
    (hold,) = state.fx_holds
    assert hold.dropped == {(P0, "R", 0)}
    assert [p.key for p in state.fx_slide_params] == [(P0, "R", 1), (P1, "R", 0)]
    # The next X leaves the tapped macro alone.
    state, actions, _ = x(state, 11, at(5))
    assert actions == [SetMacros((((P0, "R", 1), 20.0), ((P1, "R", 0), 30.0)))]


def test_a_bars_morph_mid_slide_takes_its_parameters_and_joins_the_step():
    state = with_slot(sliding(), 0, (FxRack("B", "R", 0, (99.0,)),))
    state, _, _ = x(state, 11, at(2))
    state, actions = racks_read(state, 0, NOW_AB, recall=True, bars=4, snapshot=playing(3.0))
    assert actions == [ShowMessage("Snapshot 1 in 4 bars")]
    assert state.morph is not None and not state.fx_undo_open
    assert state.fx_holds[0].dropped == {(P1, "R", 0)}


# Held slots: several slides, faders and hand turns (B6)

ROW_1 = OTHER_SLOT[1]
A_ONLY = (FxRack("A", "R", 0, (100.0, 100.0)),)


def two_slides(f_a=2, f_b=1):
    # Slot 3 slides first (to f_a columns), then slot 1, sharing rack A's macros (to f_b).
    state = sliding(with_slot(AB, 0, A_ONLY))
    state, _, _ = x(state, 11, at(f_a))
    state, _ = handle(state, OTHER_SLOT)
    state, _ = hold_read(state, slot=0)
    state, _, _ = x(state, 11, 0, pad=ROW_1)
    state, actions, _ = x(state, 11, at(f_b), pad=ROW_1)
    return state, actions


def test_the_later_slide_owns_the_parameters_it_shares():
    state, actions = two_slides()
    f_a, f_b = at(2) / X_COLUMN_WIDTH / 4, at(1) / X_COLUMN_WIDTH / 4
    # One step for both: slot 1's slide writes from the shared origin, 0, with no Begin.
    assert actions == [SetMacros((((P0, "R", 0), 100.0 * f_b), ((P0, "R", 1), 100.0 * f_b)))]
    # Slot 3's X now moves only rack B's macro.
    state, actions, _ = x(state, 11, at(3))
    ((key, value),) = actions[0].writes
    assert len(actions) == 1 and key == (P1, "R", 0)
    assert value == pytest.approx(30.0 * at(3) / X_COLUMN_WIDTH / 4)
    assert f_a  # slot 3 had blended rack A first


def test_lifting_the_later_slide_hands_back_to_the_earlier_at_its_blend():
    state, _ = two_slides()
    f_a = at(2) / X_COLUMN_WIDTH / 4
    state, actions = lift(state, OTHER_SLOT)
    assert actions == [
        SetMacros((((P0, "R", 0), 10.0 * f_a), ((P0, "R", 1), 20.0 * f_a))),
        ShowMessage(f"Snapshot 1 at {round(at(1) / X_COLUMN_WIDTH / 4 * 100)}%"),
    ]
    state, actions = lift(state, (11, ROW))
    assert actions[0] == EndUndoStep() and not state.fx_slide_undo_open


def test_lifting_the_earlier_slide_first_leaves_the_later_in_charge():
    state, _ = two_slides()
    state, actions = lift(state, (11, ROW))
    assert actions == [ShowMessage(f"Snapshot 3 at {round(at(2) / X_COLUMN_WIDTH / 4 * 100)}%")]
    assert state.fx_slide_undo_open
    state, actions, _ = x(state, 11, at(4), pad=ROW_1)
    assert actions == [SetMacros((((P0, "R", 0), 100.0 * at(4) / X_COLUMN_WIDTH / 4), ((P0, "R", 1), 100.0 * at(4) / X_COLUMN_WIDTH / 4)))]
    state, actions = lift(state, OTHER_SLOT)
    assert actions[0] == EndUndoStep() and state.fx_slide_params == ()


def test_a_slide_after_another_lifted_starts_from_where_it_left_the_parameter():
    # Slot 1 is held first but slides only after slot 3 slid to 60% and lifted.
    state, _ = handle(with_slot(AB, 0, A_ONLY), OTHER_SLOT)
    state, _ = hold_read(state, slot=0)
    state, _, _ = x(state, 11, 0, pad=ROW_1)
    state, _ = handle(state, SLOT_3)
    state, _ = hold_read(state)
    state, _, _ = x(state, 11, 0)
    state, _, _ = x(state, 11, at(2.4))
    state, _ = lift(state, (11, ROW))
    left = {p.key: p.written for p in state.fx_slide_params}
    assert left[(P0, "R", 0)] == pytest.approx(6.0, abs=0.01)
    state, actions, _ = x(state, 11, at(2), pad=ROW_1)
    f = at(2) / X_COLUMN_WIDTH / 4
    origin = left[(P0, "R", 0)]
    assert actions[-1].writes[0] == ((P0, "R", 0), origin + f * (100.0 - origin))


def test_a_fader_on_a_sliding_macro_takes_it_out_with_no_undo_actions():
    state, _, _ = x(sliding(), 11, at(2))
    view = FaderView("Macro 1", 0.0, 0.0, 127.0, macro=(P0, "R", 0))
    snap = replace(SNAP, faders=(view,) * 8)
    state, _ = session.handle(state, PadPress(5, 2, True), snap)
    state, actions, _ = engine.x_axis(state, XAxis(5, 2, round(centre(6))))
    assert [a for a in actions if isinstance(a, (BeginUndoStep, EndUndoStep))] == []
    assert state.fx_holds[0].dropped == {(P0, "R", 0)}
    state, actions, _ = x(state, 11, at(5))
    assert actions == [SetMacros((((P0, "R", 1), 20.0), ((P1, "R", 0), 30.0)))]


def test_a_hand_turned_parameter_leaves_the_slide():
    state, _, _ = x(sliding(), 11, at(2))
    values = tuple(p.written for p in state.fx_slide_params)
    assert engine.slide_tick(state, values) == state
    turned = (values[0] + 10.0,) + values[1:]
    state = engine.slide_tick(state, turned)
    assert state.fx_holds[0].dropped == {(P0, "R", 0)}
    assert [p.key for p in state.fx_slide_params] == [(P0, "R", 1), (P1, "R", 0)]


def test_a_second_slide_on_a_row_is_ignored():
    state, _, _ = x(sliding(with_slot(AB, 10)), 11, at(2))
    assert handle(state, layout.FX.slots[10]) == (state, [])


def test_a_slide_at_0_writes_nothing_and_leaves_a_morph_running():
    morph = Morph(5, 0.0, 16.0, 0.0)
    state = sliding(replace(AB, morph=morph, fx_undo_open=True))
    state, actions, _ = x(state, 11, -at(0.3))
    assert state.fx_holds[0].slid and actions == []
    assert state.morph == morph and state.fx_undo_open and not state.fx_slide_undo_open
    # Its first write cancels the morph.
    state, actions, _ = x(state, 11, at(2))
    assert actions[:2] == [EndUndoStep(), BeginUndoStep()] and state.morph is None


def test_a_tap_beside_a_slide_at_0_is_its_own_step_and_takes_the_shared_macros():
    state = with_slot(sliding(), 0, A_ONLY)
    state, _, _ = x(state, 11, -at(0.3))
    state, _ = handle(state, OTHER_SLOT)
    state, _ = hold_read(state, slot=0)
    state, actions = lift(state, OTHER_SLOT)
    assert actions[0] == BeginUndoStep() and actions[2] == EndUndoStep()
    assert state.fx_holds[0].dropped == {(P0, "R", 0), (P0, "R", 1)}


def test_a_handback_to_an_earlier_slide_at_0_writes_its_origin():
    state, _ = two_slides(f_a=-0.3)
    state, actions = lift(state, OTHER_SLOT)
    assert actions[0] == SetMacros((((P0, "R", 0), 0.0), ((P0, "R", 1), 0.0)))


# Bound slots: a relative slide both ways (C2)

FREQ = FaderBinding("Bass", 0, "Auto Filter", 0, 1, "Frequency")
MACRO_KEY = (P0, "R", 0)
FREQ_READ = BoundRead(FREQ, "Frequency", 100.0, 0.0, 127.0, False)
SWITCH_READ = BoundRead(MACRO_KEY, "On", 0.0, 0.0, 1.0, True)
BOUND_AB = with_slot(FX, 2, BoundSlot((FREQ, FaderBinding("A", 0, "R", 0, 1, "Macro 1"))))


def bound_read(state, params=(FREQ_READ, SWITCH_READ)):
    return engine.handle(state, RacksRead(2, (), True, hold=True, params=params), SNAP)


def bound_sliding(params=(FREQ_READ, SWITCH_READ)):
    state, _ = handle(BOUND_AB, SLOT_3)
    state, _ = bound_read(state, params)
    state, _, _ = x(state, 11, 0)
    return state


def test_a_bound_slot_press_reads_its_locators():
    state, actions = handle(BOUND_AB, SLOT_3)
    assert actions == [RecallFxSnapshot(2, None, hold=True, locators=BOUND_AB.fx_slots[2].params)]
    assert state.fx_holds[0].bound


def test_bars_and_a_bound_slot_does_nothing():
    state = replace(BOUND_AB, fx_length=4)
    assert handle(state, SLOT_3) == (state, [])


def test_a_bound_tap_names_its_parameters_and_writes_nothing():
    state, _ = handle(BOUND_AB, SLOT_3)
    state, _ = bound_read(state, (FREQ_READ, None))
    state, actions = lift(state)
    assert actions == [ShowMessage("Snapshot 3: Frequency 100, 1 parameter not found")]
    assert state.fx_holds == () and state.fx_landed is None


def test_a_bound_slide_right_moves_a_quarter_range_per_pad_and_stops_at_the_end():
    state, actions, _ = x(bound_sliding(), 11, at(0.5))
    f = at(0.5) / X_COLUMN_WIDTH / 4
    assert actions[-1] == SetMacros(((FREQ, 100.0 + f * 127.0),))
    state, actions, _ = x(state, 11, at(2.2))
    assert actions[-1] == SetMacros(((FREQ, 127.0), (MACRO_KEY, 1.0)))


def test_a_bound_slide_left_goes_below_the_start_down_to_the_min():
    state, actions, _ = x(bound_sliding(), 11, -at(2))
    f = -at(2) / X_COLUMN_WIDTH / 4
    assert actions[-1] == SetMacros(((FREQ, 100.0 + f * 127.0),))
    state, actions, _ = x(state, 11, -at(9))
    assert actions[-1] == SetMacros(((FREQ, 0.0),))
    assert state.fx_holds[0].f == -1.0


def test_back_travel_returns_exactly_to_the_start():
    state, _, _ = x(bound_sliding(), 11, at(3))
    state, actions, _ = x(state, 11, 0)
    assert actions == [SetMacros(((FREQ, 100.0), (MACRO_KEY, 0.0)))]


def test_a_quantized_bound_on_off_flips_halfway_either_way():
    state, actions, _ = x(bound_sliding((SWITCH_READ,)), 11, -at(2.2))
    assert actions == []  # already at its min
    state, actions, _ = x(state, 11, at(2.2))
    assert actions[-1] == SetMacros(((MACRO_KEY, 1.0),))
    state, actions, _ = x(state, 11, at(1.8))
    assert actions == [SetMacros(((MACRO_KEY, 0.0),))]


def test_a_quantized_bound_chooser_steps_a_pad_at_a_time_and_returns_to_its_start():
    chooser = replace(SWITCH_READ, name="Mode", start=1.0, high=4.0)
    state, actions, _ = x(bound_sliding((chooser,)), 11, at(1.4))
    assert actions[-1] == SetMacros(((MACRO_KEY, 2.0),))
    state, actions, _ = x(state, 11, at(2.6))
    assert actions == [SetMacros(((MACRO_KEY, 4.0),))]
    state, actions, _ = x(state, 11, -at(1.6))
    assert actions == [SetMacros(((MACRO_KEY, 0.0),))]
    state, actions, _ = x(state, 11, 0)
    assert actions == [SetMacros(((MACRO_KEY, 1.0),))]


def test_a_bound_lift_names_its_parameters_with_a_signed_percent():
    state, _, _ = x(bound_sliding(), 11, -at(1.6))
    state, actions = lift(state, (11, ROW))
    assert actions[-1] == ShowMessage("Snapshot 3 at -40%: Frequency, On")


def test_a_bound_and_a_set_wide_slide_share_a_rack_macro():
    # The bound slot's Macro 1 resolves to the same key as the Set-wide slot's.
    state = with_slot(bound_sliding(), 0, A_ONLY)
    state, _, _ = x(state, 11, at(1))
    state, _ = handle(state, OTHER_SLOT)
    state, _ = hold_read(state, slot=0)
    state, _, _ = x(state, 11, 0, pad=ROW_1)
    state, actions, _ = x(state, 11, at(2), pad=ROW_1)
    assert MACRO_KEY in dict(actions[-1].writes)
    state, actions, _ = x(state, 11, at(3))
    assert all(MACRO_KEY not in dict(a.writes) for a in actions if isinstance(a, SetMacros))


# Bound slots: the value meter (C2b)


def test_a_held_bound_slot_shows_its_parameters_value_right_of_it():
    state, _ = handle(BOUND_AB, SLOT_3)
    assert fx.render_meters(state) == {}  # no read yet
    state, _ = bound_read(state, (FREQ_READ,))
    frame = session.render(state, SNAP)
    # 100 of 127: 3 of 4 pads, columns 12-15 right of the slot in column 11.
    assert [frame[(c, ROW)] for c in (12, 13, 14, 15)] == [Light(PINK)] * 3 + [Light(OFF)]
    assert frame[(10, ROW)] != Light(PINK) and frame[SLOT_3] == Light(PINK)


def test_the_value_meter_shows_the_average_of_several_parameters():
    # Frequency at 100 of 127 and On at 0 of 1: about 39%, 2 of 4 pads.
    state, _ = handle(BOUND_AB, SLOT_3)
    state, _ = bound_read(state)
    frame = fx.render_meters(state)
    assert [frame[(c, ROW)] for c in (12, 13, 14, 15)] == [Light(PINK)] * 2 + [Light(OFF)] * 2


def test_the_value_meter_leaves_out_dropped_parameters_and_ones_without_a_range():
    flat = replace(SWITCH_READ, key="flat", high=0.0)
    state, _ = handle(BOUND_AB, SLOT_3)
    state, _ = bound_read(state, (FREQ_READ, SWITCH_READ, flat))
    hold = replace(state.fx_holds[0], dropped=frozenset({MACRO_KEY}))
    assert fx.value_meter(state, hold) == 3
    assert fx.value_meter(state, replace(hold, read=(flat,))) == 0


def test_the_value_meter_follows_the_slide_and_redraws():
    state, _, redraw = x(bound_sliding(), 11, at(2.2))
    assert redraw
    assert all(light == Light(PINK) for light in fx.render_meters(state).values())
    state, _, _ = x(state, 11, -at(9))
    assert all(light == Light(OFF) for light in fx.render_meters(state).values())
    assert session.render(state, SNAP)[SLOT_3] == Light(PINK, Blink.FAST)


# Binding: Shift + a slot (C3)

EQ = FaderBinding("Bass", 0, "EQ", 1, 1, "Frequency")


def bound_answer(state, slot=2, binding=FREQ, parameter="Frequency", refusal=None, value=None, text=""):
    return engine.handle(state, ParameterBound(slot, binding, parameter, refusal, value, text), SNAP)


@pytest.mark.parametrize("layer", ["FX", "PANEL", "MIXER_PANEL"])
def test_shift_and_a_slot_binds_on_the_lift(layer):
    # The panels are defined further down.
    shifted = replace(globals()[layer], shift=True)
    held, actions = handle(shifted, SLOT_3)
    assert actions == [] and held.fx_bind_hold == BindHold(SLOT_3[1], SLOT_3[0], 2)
    released, actions = handle(replace(held, shift=False), SLOT_3, pressed=False)
    assert actions == [BindSelectedParameter(2)] and released.fx_bind_hold is None


def test_shift_and_a_slot_in_bank_2_binds_its_global_slot():
    held, _ = handle(replace(BANK_2, shift=True), SLOT_3)
    assert handle(held, SLOT_3, pressed=False)[1] == [BindSelectedParameter(18)]


def test_shift_and_a_stored_slot_never_recalls_or_slides():
    state = replace(with_slot(FX, 2), shift=True)
    held, actions = handle(state, SLOT_3)
    assert actions == [] and held.fx_holds == ()
    assert handle(state, SCENE_2, snapshot=SCENES) == (state, [])


def test_a_bind_adds_to_an_empty_slot_and_names_it():
    state, actions = bound_answer(FX)
    assert state.fx_slots[2] == BoundSlot((FREQ,))
    assert actions == [SaveFxSnapshots(fx.dump(state.fx_slots)), ShowMessage("Snapshot 3: Frequency")]


def test_a_second_bind_adds_and_names_both():
    state, _ = bound_answer(FX)
    state, actions = bound_answer(state, binding=EQ)
    assert state.fx_slots[2] == BoundSlot((FREQ, EQ))
    assert actions[-1] == ShowMessage("Snapshot 3: Auto Filter Frequency, EQ Frequency")


def test_binding_a_held_parameter_removes_it_and_the_last_empties_the_slot():
    state, _ = bound_answer(with_slot(FX, 2, BoundSlot((FREQ, EQ))))
    assert state.fx_slots[2] == BoundSlot((EQ,))
    state, actions = bound_answer(state, binding=EQ)
    assert state.fx_slots[2] is None
    assert actions[-1] == ShowMessage("Removed EQ Frequency from Snapshot 3")


def test_a_bind_saves_the_parameters_value_and_names_it():
    state, actions = bound_answer(FX, value=0.6, text="1.20 kHz")
    assert state.fx_slots[2] == BoundSlot((FREQ,), (0.6,))
    assert actions[-1] == ShowMessage("Snapshot 3: Auto Filter Frequency 1.20 kHz")
    assert fx.parse(actions[0].text)[2] == state.fx_slots[2]


def test_a_second_bind_saves_its_value_and_leaves_the_firsts():
    state, _ = bound_answer(FX, value=0.6, text="1.20 kHz")
    state, actions = bound_answer(state, binding=EQ, value=0.2, text="300 Hz")
    assert state.fx_slots[2] == BoundSlot((FREQ, EQ), (0.6, 0.2))
    assert actions[-1] == ShowMessage("Snapshot 3: Auto Filter Frequency, EQ Frequency 300 Hz")


def test_a_bind_without_a_value_keeps_the_others():
    state = with_slot(FX, 2, BoundSlot((FREQ,), (0.6,)))
    state, actions = bound_answer(state, binding=EQ)
    assert state.fx_slots[2] == BoundSlot((FREQ, EQ), (0.6, None))
    assert actions[-1] == ShowMessage("Snapshot 3: Auto Filter Frequency, EQ Frequency")


def test_a_removal_drops_its_value():
    state = with_slot(FX, 2, BoundSlot((FREQ, EQ), (0.6, 0.2)))
    state, _ = bound_answer(state)
    assert state.fx_slots[2] == BoundSlot((EQ,), (0.2,))
    state = with_slot(FX, 2, BoundSlot((FREQ, EQ), (None, 0.2)))
    state, _ = bound_answer(state, binding=EQ)
    assert state.fx_slots[2] == BoundSlot((FREQ,))


def test_a_renamed_macro_still_toggles_off():
    macro = FaderBinding("A", 0, "R", 0, 1, "Macro 1")
    renamed = replace(macro, name="Cutoff")
    state, _ = bound_answer(with_slot(FX, 2, BoundSlot((macro,))), binding=renamed)
    assert state.fx_slots[2] is None


@pytest.mark.parametrize(
    "refusal, parameter, message",
    [
        ("select", None, "Click a parameter in Live first"),
        ("macro", "Gain", "Snapshot 3 can't hold Gain"),
        ("refused", "Crossfader", "Snapshot 3 can't hold Crossfader"),
    ],
)
def test_bind_refusals(refusal, parameter, message):
    assert bound_answer(FX, binding=None, parameter=parameter, refusal=refusal) == (FX, [ShowMessage(message)])


def test_a_set_wide_slot_refuses_a_bind():
    state = with_slot(FX, 2)
    assert bound_answer(state) == (state, [ShowMessage("Delete Snapshot 3 to bind to it")])


# Binding: Shift + a slot + a Device FX row (C4)

ROW_VIEWS = replace(SNAP, faders=(FaderView("Frequency", 1.0, 0.0, 127.0),) * 4 + (None,) * 4)


def bind_holding():
    state, _ = handle(replace(FX, shift=True), SLOT_3)
    return state


def test_a_device_fx_row_during_a_bind_hold_binds_its_parameter():
    state, actions = session.handle(bind_holding(), PadPress(5, 2, True), ROW_VIEWS)
    assert actions == [BindFaderRow(2, 1)]
    assert state.fader_touches == () and state.fx_bind_hold.used
    # The slot's lift then does nothing more.
    state, actions = handle(state, SLOT_3, pressed=False)
    assert actions == [] and state.fx_bind_hold is None


def test_a_row_with_no_parameter_does_nothing():
    state = bind_holding()
    assert session.handle(state, PadPress(5, 6, True), ROW_VIEWS) == (state, [])


def test_rows_answer_with_the_same_toggle():
    state, _ = bound_answer(bind_holding())
    state, actions = bound_answer(state)
    assert state.fx_slots[2] is None


# Messages: long parameter lists (C5)


def say_as_is(text):
    return [ShowMessage(text)]


def test_a_list_that_fits_is_whole():
    assert fx.listed(["a", "b"], say_as_is) == [ShowMessage("a, b")]


def test_a_list_past_the_limit_ends_with_the_count_left():
    items = ["x" * 70, "y" * 70, "z" * 70]
    assert fx.listed(items, say_as_is) == [ShowMessage("x" * 70 + ", " + "y" * 70 + ", +1")]


def test_a_message_exactly_at_the_limit_is_whole():
    items = ["x" * 79, "y" * 79]
    assert len("x" * 79 + ", " + "y" * 79) == STATUS_MAX
    assert fx.listed(items, say_as_is) == [ShowMessage("x" * 79 + ", " + "y" * 79)]


def test_one_item_too_long_still_shows():
    assert fx.listed(["x" * 200, "y"], say_as_is) == [ShowMessage("x" * 200 + ", +1")]


def test_a_bind_message_shortens():
    params = tuple(FaderBinding("Bass", 0, f"Device {i}", 0, 1, "Frequency") for i in range(12))
    state = with_slot(FX, 2, BoundSlot(params[:11]))
    _, actions = bound_answer(state, binding=params[11])
    text = actions[-1].text
    assert text.startswith("Snapshot 3: Device 0 Frequency") and text.endswith(", +5") and len(text) <= STATUS_MAX


def test_labels_name_the_owner_only_where_two_share_a_name():
    params = [("Auto Filter", "Frequency"), ("Bass", "Volume"), ("EQ", "Frequency")]
    assert fx.labels(params) == ["Auto Filter Frequency", "Volume", "EQ Frequency"]


# Binding: the Undo pad (C6)

UNDO = layout.GLOBAL.undo
SHIFT = layout.GLOBAL.shift
CAN_UNDO = replace(SNAP, can_undo=True)


def bound_freq(state=FX):
    state, _ = bound_answer(state)
    return state


def test_the_undo_pad_unbinds_within_the_window_without_lives_undo():
    state, actions = handle(bound_freq(), UNDO, snapshot=CAN_UNDO)
    assert state.fx_slots[2] is None and state.bind_undo == ()
    assert actions == [SaveFxSnapshots(fx.dump(state.fx_slots)), ShowMessage("Unbound Auto Filter Frequency from Snapshot 3")]


def test_the_undo_pad_rebinds_a_removal():
    state, _ = bound_answer(bound_freq())
    state, actions = handle(state, UNDO, snapshot=CAN_UNDO)
    assert state.fx_slots[2] == BoundSlot((FREQ,))
    assert actions[-1] == ShowMessage("Bound Auto Filter Frequency to Snapshot 3 again")


def test_several_undos_pop_newest_first_each_restarting_the_window():
    state, _ = bound_answer(bound_freq(), binding=EQ)
    state = engine.bind_tick(state, 0.0)
    state = engine.bind_tick(state, 9000.0)
    state, actions = handle(state, UNDO, snapshot=CAN_UNDO)
    assert actions[-1] == ShowMessage("Unbound EQ Frequency from Snapshot 3")
    assert state.bind_undo_at is None
    state = engine.bind_tick(state, 9010.0)
    state = engine.bind_tick(state, 18000.0)
    state, actions = handle(state, UNDO, snapshot=CAN_UNDO)
    assert actions[-1] == ShowMessage("Unbound Auto Filter Frequency from Snapshot 3")


def test_after_the_window_the_undo_pad_is_lives_undo():
    state = engine.bind_tick(bound_freq(), 0.0)
    state = engine.bind_tick(state, 10000.0)
    assert state.bind_undo == ()
    state, actions = handle(state, UNDO, snapshot=CAN_UNDO)
    assert actions == [Undo(), ShowMessage("Undo")] and state.fx_slots[2] == BoundSlot((FREQ,))


def test_another_press_ends_the_window():
    state, _ = engine.handle(bound_freq(), PadPress(13, 2, True), SNAP)
    assert state.bind_undo == ()
    assert handle(state, UNDO, snapshot=CAN_UNDO)[1][0] == Undo()


def test_shift_and_its_release_keep_the_window():
    state, _ = engine.handle(bound_freq(), PadPress(*SHIFT, True), SNAP)
    state, _ = engine.handle(state, PadPress(*SHIFT, False), SNAP)
    assert state.bind_undo != ()


def test_a_binds_own_presses_keep_the_window():
    state, _ = engine.handle(replace(bound_freq(), shift=True), PadPress(*SLOT_3, True), SNAP)
    assert state.bind_undo != ()
    state, _ = engine.handle(state, PadPress(5, 2, True), ROW_VIEWS)
    assert state.bind_undo != ()


def test_two_rows_in_one_bind_hold_both_undo():
    state, _ = engine.handle(replace(FX, shift=True), PadPress(*SLOT_3, True), SNAP)
    state, actions = engine.handle(state, PadPress(5, 2, True), ROW_VIEWS)
    assert actions == [BindFaderRow(2, 1)]
    state, _ = bound_answer(state)
    state, actions = engine.handle(state, PadPress(5, 3, True), ROW_VIEWS)
    assert actions == [BindFaderRow(2, 2)]
    state, _ = bound_answer(state, binding=EQ)
    state, _ = engine.handle(replace(state, shift=False), PadPress(*SLOT_3, False), SNAP)
    state, actions = engine.handle(state, PadPress(*UNDO, True), CAN_UNDO)
    assert actions[-1] == ShowMessage("Unbound EQ Frequency from Snapshot 3")
    state, actions = engine.handle(state, PadPress(*UNDO, True), CAN_UNDO)
    assert actions[-1] == ShowMessage("Unbound Auto Filter Frequency from Snapshot 3")


def test_a_bound_tap_shows_lives_text_for_the_value():
    state, _ = handle(BOUND_AB, SLOT_3)
    state, _ = bound_read(state, (replace(FREQ_READ, text="1.20 kHz"),))
    _, actions = lift(state)
    assert actions == [ShowMessage("Snapshot 3: Frequency 1.20 kHz")]


def test_a_bound_tap_and_lift_name_the_device_where_two_share_a_name():
    eq = replace(FREQ_READ, key=FaderBinding("Bass", 0, "EQ", 0, 1, "Frequency"), owner="EQ")
    reads = (replace(FREQ_READ, owner="Auto Filter"), eq, replace(SWITCH_READ, owner="R"))
    state, _ = handle(BOUND_AB, SLOT_3)
    state, _ = bound_read(state, reads)
    _, actions = lift(state)
    assert actions == [ShowMessage("Snapshot 3: Auto Filter Frequency 100, EQ Frequency 100, On 0")]
    state, _, _ = x(bound_sliding(reads), 11, at(2))
    _, actions = lift(state, (11, ROW))
    assert actions[-1] == ShowMessage("Snapshot 3 at 50%: Auto Filter Frequency, EQ Frequency, On")


# Held slots: the meter (B7)


def test_the_meter_fills_one_pad_per_quarter():
    state = held(holding_read(), x0=0, slid=True, f=0.6, order=1)
    frame = session.render(state, SNAP)
    assert [frame[(c, ROW)] for c in range(12, 16)] == [Light(CYAN)] * 3 + [Light(OFF)]
    assert frame[SLOT_3] == Light(CYAN, Blink.FAST)


@pytest.mark.parametrize("f, lit", [(0.0, 0), (0.01, 1), (0.25, 1), (0.26, 2), (1.0, 4)])
def test_meter_counts(f, lit):
    assert fx.meter(f) == lit


def test_a_column_12_slides_meter_covers_scenes_and_navigation():
    slot_11 = layout.FX.slots[10]
    state, _ = handle(with_slot(AB, 10), slot_11)
    state = held(state, x0=0, slid=True, f=1.0, order=1)
    frame = session.render(state, SCENES)
    assert [frame[(c, slot_11[1])] for c in range(13, 17)] == [Light(CYAN)] * 4


def test_a_held_slot_before_it_slides_shows_no_meter():
    state = holding_read()
    assert fx.render_meters(state) == {}
    assert session.render(state, SNAP)[SLOT_3] == Light(CYAN)


def test_a_scoped_slots_meter_is_pink():
    state = held(holding_read(), x0=0, slid=True, f=0.3, order=1)
    state = with_slot(state, 2, BOUND)
    assert fx.render_meters(state)[(12, ROW)] == Light(PINK)


def test_the_meter_goes_on_the_lift():
    state, _, _ = x(sliding(), 11, at(3))
    state, _ = lift(state, (11, ROW))
    assert session.render(state, SNAP)[(12, ROW)] == Light(OFF)


def test_x_redraws_when_the_meter_changes():
    state, _, redraw = x(sliding(), 11, at(0.5))
    assert redraw  # the slide starts
    state, _, redraw = x(state, 11, at(0.6))
    assert not redraw
    state, _, redraw = x(state, 11, at(1.1))
    assert redraw


# Render


def test_render_slots_and_lengths():
    state = with_slot(with_slot(with_slot(replace(FX, fx_length=4), 0), 9), 5)
    state = replace(state, fx_landed=9, morph=Morph(5, 0.0, 16.0, 0.0))
    frame = fx.render(state, SNAP)
    assert frame[layout.FX.slots[0]] == Light(CYAN)
    assert frame[layout.FX.slots[9]] == Light(CYAN, Blink.TEMPO)
    assert frame[layout.FX.slots[5]] == Light(CYAN, Blink.FAST)
    assert frame[layout.FX.slots[1]] == Light(OFF)
    assert frame[(10, 3)] == Light(WHITE, Blink.FAST)
    for key in ((10, 1), (10, 2), (10, 4), (10, 5)):
        assert frame[key] == Light(WHITE)
    lit = {key for key, light in frame.items() if light != Light(OFF)}
    assert lit == {layout.FX.slots[i] for i in (0, 5, 9)} | set(layout.FX.bars) | {(13, 1)}


def test_render_scoped_slots_pink():
    state = with_slot(with_slot(with_slot(FX, 0, BOUND), 9, BOUND), 5, BOUND)
    state = replace(state, fx_landed=9, morph=Morph(5, 0.0, 16.0, 0.0))
    frame = fx.render(state, SNAP)
    assert frame[layout.FX.slots[0]] == Light(PINK)
    assert frame[layout.FX.slots[9]] == Light(PINK, Blink.TEMPO)
    assert frame[layout.FX.slots[5]] == Light(PINK, Blink.FAST)


def test_render_column_14_is_dark_with_no_scene_snapshots():
    frame = fx.render(with_slot(FX, 2), SNAP)
    assert all(frame[(14, pad)] == Light(OFF) for pad in range(1, layout.ROWS + 1))


def test_render_landed_slot_that_was_cleared_is_dark():
    assert fx.render(replace(FX, fx_landed=2), SNAP)[SLOT_3] == Light(OFF)


def test_render_morph_target_blinks_over_landed():
    state = replace(with_slot(FX, 2), fx_landed=2, morph=Morph(2, 0.0, 4.0, 0.0))
    assert fx.render(state, SNAP)[SLOT_3] == Light(CYAN, Blink.FAST)


def test_render_under_shift_is_unchanged():
    state = replace(with_slot(FX, 2), fx_length=1)
    assert fx.render(replace(state, shift=True), SNAP) == fx.render(state, SNAP)


def test_session_render_in_fx_mode():
    snapshot = replace(SNAP, track_count=3, scene_count=2)
    state = with_slot(FX, 2)
    frame = session.render(state, snapshot)
    assert frame[layout.NAVIGATION.fx] == Light(BLUE)
    assert frame[SLOT_3] == Light(CYAN)
    for column in layout.GRID_COLUMNS:
        if column in layout.FX_FADER_COLUMNS:
            continue
        for pad in range(1, layout.ROWS + 1):
            assert frame[(column, pad)] == fx.render(state, snapshot)[(column, pad)]


def test_session_render_fx_pad_off():
    assert session.render(State(), SNAP)[layout.NAVIGATION.fx] == Light(CYAN)


def test_session_render_shift_layer_in_fx():
    state = with_slot(FX, 2)
    frame = session.render(replace(state, shift=True), SNAP)
    assert frame[layout.NAVIGATION.fx] == Light(ORANGE)
    plain = session.render(state, SNAP)
    assert all(frame[(c, p)] == plain[(c, p)] for c in layout.GRID_COLUMNS for p in range(1, 9))


# Scene snapshots

SCENES = replace(SNAP, scene_count=8)
SCENE_2 = layout.FX.scene_slots[1]


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
    assert handle(FX, layout.FX.scene_slots[2], snapshot=snapshot)[1] == [
        StoreFxSnapshot(2, scene=True)
    ]
    assert handle(FX, layout.FX.scene_slots[3], snapshot=snapshot) == (FX, [])


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
    keys = layout.FX.scene_slots
    assert frame[keys[0]] == Light(LIME)
    assert frame[keys[1]] == Light(OFF)
    assert frame[keys[2]] == Light(LIME, Blink.TEMPO)
    assert frame[keys[4]] == Light(LIME, Blink.FAST)
    assert frame[(14, 7)] == frame[(14, 8)] == Light(OFF)


def test_a_scene_morph_does_not_blink_the_global_slot_with_its_number():
    state = with_scene(with_slot(FX, 4), 4)
    state = replace(state, morph=Morph(4, 0.0, 16.0, 0.0, scene=True))
    frame = fx.render(state, SCENES)
    assert frame[layout.FX.slots[4]] == Light(CYAN)
    assert frame[layout.FX.scene_slots[4]] == Light(LIME, Blink.FAST)


def test_a_global_morph_does_not_blink_the_scene_pad_with_its_number():
    state = with_scene(with_slot(FX, 4), 4)
    state = replace(state, morph=Morph(4, 0.0, 16.0, 0.0))
    frame = fx.render(state, SCENES)
    assert frame[layout.FX.slots[4]] == Light(CYAN, Blink.FAST)
    assert frame[layout.FX.scene_slots[4]] == Light(LIME)


def test_render_scene_snapshots_follow_the_window():
    state = replace(with_scene(FX, 3), window=layout.Window(0, 2))
    frame = fx.render(state, SCENES)
    assert frame[layout.FX.scene_slots[1]] == Light(LIME)
    assert frame[layout.FX.scene_slots[3]] == Light(OFF)


def test_render_scene_snapshots_past_the_last_scene_are_dark():
    # A stale entry past the Set's end, kept until the next save, lights nothing.
    state = with_scene(FX, 3)
    assert fx.render(state, replace(SNAP, scene_count=3))[layout.FX.scene_slots[3]] == Light(OFF)


def test_render_scene_snapshots_under_shift_stay_lit():
    state = replace(with_scene(FX, 0), shift=True)
    assert fx.render(state, SCENES)[layout.FX.scene_slots[0]] == Light(LIME)


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
    assert state.morph.launch


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
    # 1 Bar quantization: fired in the bar before, at bar 4.
    state, actions = timed(FX, 1.5)
    assert state.pending_launch == PendingLaunch(2, 12.0, 1.5)
    assert actions == [ShowMessage("Scene 3 in 4 bars")]


def test_a_timed_launch_morphs_its_snapshot_to_land_as_the_scene_starts():
    state, actions = timed(with_scene(FX, 2), 1.5)
    assert actions == [
        ShowMessage("Scene 3 in 4 bars"),
        RecallFxSnapshot(2, None, scene=True, end_beats=16.0),
    ]


def test_a_timed_launch_snaps_to_a_coarser_quantization():
    # 4 Bars quantization (2), 1 bar held at bar 1: the first 4-bar line after bar 2, which
    # Live's quantization already starts it on.
    state, actions = timed(with_scene(FX, 2), 1.5, quantization=2, bars=1)
    assert state.pending_launch is None
    assert actions == [
        FireScene(2, legato=False),
        RecallFxSnapshot(2, None, scene=True, end_beats=16.0),
    ]
    state, _ = timed(FX, 1.5, quantization=2, bars=8)
    assert state.pending_launch == PendingLaunch(2, 16.0, 1.5)


def test_a_timed_launch_unquantized_fires_on_the_bar_line():
    state, _ = timed(FX, 1.5, quantization=0)
    assert state.pending_launch == PendingLaunch(2, 16.0, 1.5)


def test_a_timed_launch_inside_its_last_step_fires_at_once():
    # 1 bar held: Live's 1 Bar quantization starts it on the line.
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


def test_launch_tick_counts_across_a_loop_wrap():
    # Fires on beat 20 counted from the press, which the wrap moves to beat 4.
    state = replace(FX, pending_launch=PendingLaunch(2, 20.0, 15.9))
    state, actions, redraw = engine.launch_tick(state, looped(0.0))
    assert (state.pending_launch, actions, redraw) == (PendingLaunch(2, 4.0, 0.0), [], False)
    state, actions, redraw = engine.launch_tick(state, looped(4.0))
    assert (state.pending_launch, actions, redraw) == (None, [FireScene(2, legato=False)], True)


def test_launch_tick_cancels_on_a_jump_back_inside_the_loop():
    state = replace(FX, pending_launch=PendingLaunch(2, 20.0, 12.0))
    state, actions, _ = engine.launch_tick(state, looped(4.0))
    assert state.pending_launch is None
    assert actions == [ShowMessage("Scene 3 launch cancelled")]


def test_a_pending_scene_blinks_yellow():
    frame = session.render(PENDING, launching(2.0))
    assert frame[SCENE_3] == Light(YELLOW, Blink.TEMPO)


# The split views' snapshot panel


PANEL = State(split=True, split_snapshots=True)
MIXER_PANEL = State(mixer=True, mixer_split=True, split_snapshots=True)


@pytest.mark.parametrize("state", [PANEL, MIXER_PANEL])
def test_the_split_panel_selects_banks(state):
    assert handle(state, (13, 8))[0].fx_bank == 7


@pytest.mark.parametrize("state", [PANEL, MIXER_PANEL])
def test_the_panel_is_fx_modes_columns_10_to_14(state):
    assert handle(state, SLOT_3) == (state, [StoreFxSnapshot(2)])
    assert handle(state, SCENE_2, snapshot=SCENES) == (state, [StoreFxSnapshot(1, scene=True)])
    assert handle(state, (10, 7)) == (state, [])
    held, _ = handle(state, (10, 3))
    assert held.fx_length == 4
    assert handle(held, (10, 3), pressed=False)[0] == state


@pytest.mark.parametrize("state", [PANEL, MIXER_PANEL])
def test_the_panel_stores_over_and_clears_with_copy_and_delete(state):
    state = with_slot(state, 2)
    copying, _ = handle(state, layout.NAVIGATION.copy)
    assert copying.copy
    assert handle(copying, SLOT_3)[1] == [StoreFxSnapshot(2)]
    deleting, _ = handle(state, layout.NAVIGATION.delete)
    assert handle(deleting, SLOT_3)[1] == [
        SaveFxSnapshots(fx.dump(fx._put(state.fx_slots, 2, None))),
        ShowMessage("Snapshot 3 cleared"),
    ]


@pytest.mark.parametrize("held", ["copy", "delete"])
def test_copy_and_delete_come_before_shift(held):
    state = replace(with_slot(FX, 2), shift=True, **{held: True})
    action = handle(state, SLOT_3)[1][0]
    assert action == StoreFxSnapshot(2) if held == "copy" else isinstance(action, SaveFxSnapshots)


def test_stop_leaves_the_panel_alone():
    state = with_slot(replace(PANEL, stop=True), 2)
    assert handle(state, SLOT_3)[1][0] == RecallFxSnapshot(2, None, hold=True)


def test_mixer_copy_and_delete_only_hold_for_the_panel():
    state = State(mixer=True, mixer_split=True)
    assert handle(state, layout.NAVIGATION.copy) == (state, [])
    copying, actions = handle(MIXER_PANEL, layout.NAVIGATION.copy)
    assert actions == [ShowMessage("Copy: press a slot to overwrite")]
    copying = replace(MIXER_PANEL, copy=True)
    assert handle(copying, (2, layout.MUTE_ROW)) == (copying, [])


def test_a_timed_launch_from_the_panel():
    state, _ = timed(PANEL, 1.5)
    assert state.pending_launch == PendingLaunch(2, 12.0, 1.5)


@pytest.mark.parametrize("state", [PANEL, MIXER_PANEL])
def test_the_panel_renders_as_fx_mode_with_its_free_pads_dark(state):
    state = with_slot(state, 2)
    frame = session.render(state, SCENES)
    assert frame[SLOT_3] == Light(CYAN)
    assert frame[(10, 1)] == Light(WHITE)
    assert all(frame[(10, pad)] == Light(OFF) for pad in range(6, 9))


def test_leaving_a_split_view_lets_go_of_a_held_length():
    state, _ = handle(replace(PANEL, fx_length=4), layout.NAVIGATION.session)
    assert not state.split and state.fx_length is None
    state, _ = handle(replace(MIXER_PANEL, fx_length=4), layout.NAVIGATION.mixer)
    assert not state.mixer_split and state.fx_length is None


def test_snapshot_buttons_move_to_free_pads(monkeypatch):
    # Slot 1 to column 14's unused pad 7, and the 1-bar pad to column 10's pad 6.
    slots = list(layout.FX.slots)
    slots[0] = (14, 7)
    monkeypatch.setattr(layout.FX, "slots", tuple(slots))
    monkeypatch.setattr(layout.FX, "bars", {(10, 6) if bars == 1 else key: bars for key, bars in layout.FX.bars.items()})
    assert handle(FX, (14, 7)) == (FX, [StoreFxSnapshot(0)])
    assert handle(FX, (11, 1)) == (FX, [])
    assert handle(FX, (10, 6))[0].fx_length == 1
