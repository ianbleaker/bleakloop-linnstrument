import json
from dataclasses import replace

import pytest

from BleakLoop.core import column_1, engine, faders, fx, layout, mixer, session
from BleakLoop.core.leds import BLUE, MAGENTA, OFF, Light
from BleakLoop.core.model import (
    BeginUndoStep,
    BindFader,
    EndUndoStep,
    FaderBound,
    FaderView,
    MacroView,
    PadPress,
    RacksRead,
    RackView,
    SaveFaderBindings,
    SetFaderParameter,
    SetMacros,
    ShowMessage,
    SlideMoved,
    Snapshot,
    StoreFxSnapshot,
    XAxis,
)
from BleakLoop.core.modes import FaderBinding, FxRack, Morph, MorphMacro, State
from BleakLoop.core.values import X_COLUMN_WIDTH

RACK = ("track", 0, 0)
VIEWS = tuple(FaderView(f"Macro {row + 1}", 0.0, 0.0, 127.0) for row in range(8))
SNAP = Snapshot(
    is_playing=True,
    song_beats=0.0,
    tempo=120.0,
    metronome=False,
    session_view=True,
    faders=VIEWS,
)
FX_ON = State(fx=True)


def centre(column):
    return X_COLUMN_WIDTH * (column - 0.5)


def press(column, pad, pressed=True, state=FX_ON, snapshot=SNAP):
    return faders.press(state, PadPress(column, pad, pressed), snapshot)


def x(state, column, pad, value):
    return faders.x_axis(state, XAxis(column, pad, round(value)))


def touched(column=5, pad=3, state=FX_ON, snapshot=SNAP):
    return press(column, pad, state=state, snapshot=snapshot)[0]


# Maths


def test_norm_at_the_end_pads_centres():
    assert faders.norm(centre(2), 2, 11) == 0.0
    assert faders.norm(centre(11), 2, 11) == 1.0


@pytest.mark.parametrize("value, expected", [(0, 0.0), (centre(1), 0.0), (2730, 1.0)])
def test_norm_clamps_past_the_ends(value, expected):
    assert faders.norm(value, 2, 11) == expected


def test_norm_halfway():
    assert faders.norm((centre(2) + centre(11)) / 2, 2, 11) == pytest.approx(0.5)


@pytest.mark.parametrize(
    "position, count, expected",
    [(0.0, 10, 1), (1.0, 10, 10), (0.5, 10, 6), (0.0, 5, 1), (1.0, 5, 5), (0.5, 5, 3)],
)
def test_lit(position, count, expected):
    assert faders.lit(position, count) == expected


def test_quantized_values_round():
    state = touched(snapshot=replace(SNAP, faders=(None, None, FaderView("Mode", 0, 0, 3, True))))
    touch = state.fader_touches[0]
    assert faders.value(touch, 0.5) == 2.0  # 1.5 rounds up
    assert faders.value(touch, 0.4) == 1.0


# Touch and write


def test_press_alone_writes_nothing():
    state, actions = press(5, 3)
    assert actions == []
    (touch,) = state.fader_touches
    assert (touch.pad, touch.column, touch.first, touch.last) == (3, 5, 2, 11)
    assert touch.name == "Macro 3"


def test_x_writes_and_a_repeat_writes_nothing():
    state, actions, redraw = x(touched(), 5, 3, centre(11))
    assert actions == [BeginUndoStep(), SetFaderParameter(2, "Macro 3", 127.0)]
    assert redraw
    assert x(state, 5, 3, centre(11)) == (state, [], False)


def test_redraw_only_when_the_lit_count_changes():
    state, _, _ = x(touched(), 5, 3, centre(5))
    _, actions, redraw = x(state, 5, 3, centre(5) + 2)
    assert actions and not redraw


def test_x_on_another_cell_is_ignored():
    state = touched()
    assert x(state, 6, 3, centre(6)) == (state, [], False)
    assert x(state, 5, 4, centre(5)) == (state, [], False)


def test_one_undo_step_per_gesture_across_two_rows():
    state = touched(5, 3)
    state = touched(7, 6, state=state)
    state, first, _ = x(state, 5, 3, centre(4))
    state, second, _ = x(state, 7, 6, centre(9))
    assert first[0] == BeginUndoStep()
    assert BeginUndoStep() not in second
    state, actions = press(5, 3, False, state=state)
    assert actions == []
    state, actions = press(7, 6, False, state=state)
    assert actions == [EndUndoStep()]
    assert state.fader_touches == () and not state.fader_undo_open


def test_a_morphs_step_closes_and_the_touched_macro_leaves_the_morph():
    macros = tuple(MorphMacro(RACK, "FX", i, 0.0, 100.0, False, 0.0, 127.0) for i in range(3))
    morph = Morph(0, 0.0, 16.0, 0.0, macros)
    views = list(VIEWS)
    views[1] = replace(views[1], macro=(RACK, "FX", 1))
    snapshot = replace(SNAP, faders=tuple(views))
    state = touched(5, 2, state=replace(FX_ON, morph=morph, fx_undo_open=True), snapshot=snapshot)
    state, actions, _ = x(state, 5, 2, centre(5))
    assert actions[:2] == [EndUndoStep(), BeginUndoStep()]
    assert not state.fx_undo_open and state.fader_undo_open
    assert [m.index for m in state.morph.macros] == [0, 2]


def test_a_recall_closes_an_open_fader_step():
    stored = ((FxRack("Bass", "FX", 0, (10.0,)),),) + (None,) * 15
    state = replace(touched(), fader_undo_open=True, fx_slots=stored)
    racks = (RackView(RACK, "Bass", "FX", (MacroView(0.0, 0.0, 127.0),)),)
    stopped = replace(SNAP, is_playing=False)
    state, actions = fx.racks_read(state, RacksRead(0, racks, recall=True), stopped)
    assert actions[:2] == [EndUndoStep(), BeginUndoStep()]
    assert SetMacros(((RACK, "FX", 0, 10.0),)) in actions
    assert not state.fader_undo_open


@pytest.mark.parametrize("held", ["shift", "stop", "copy"])
def test_presses_ignored_while_shift_stop_or_copy_is_held(held):
    state = replace(FX_ON, **{held: True})
    assert press(5, 3, state=state) == (state, [])


def test_a_second_press_on_a_touched_row_is_ignored():
    state = touched(5, 3)
    assert press(8, 3, state=state) == (state, [])


def test_a_row_with_no_parameter_ignores_presses():
    state = replace(FX_ON)
    snapshot = replace(SNAP, faders=(None,) * 8)
    assert press(5, 3, state=state, snapshot=snapshot) == (state, [])


def test_release_under_shift_still_ends_the_touch():
    state = replace(touched(), shift=True)
    state, _ = press(5, 3, False, state=state)
    assert state.fader_touches == ()


# Slides


def test_a_slide_off_the_fader_keeps_the_touch_and_its_release_ends_it():
    state, _, _ = x(touched(11, 3), 11, 3, centre(11))
    state, owned = faders.slide(state, SlideMoved(3, 11, 12))
    assert owned
    assert state.fader_touches[0].column == 12
    state, actions, _ = x(state, 12, 3, centre(12))
    assert actions == []  # still 1: nothing new to write
    # Back over the fader: it writes again from where the finger is.
    state, actions, _ = x(state, 12, 3, centre(10))
    (write,) = actions
    assert write.value == pytest.approx(127.0 * 8 / 9, abs=0.1)
    state, actions = press(12, 3, False, state=state)
    assert state.fader_touches == ()
    assert actions == [EndUndoStep()]


def test_an_unowned_slide_becomes_a_release():
    stopping = replace(FX_ON, stop=True)
    state, actions = engine.slide(stopping, SlideMoved(8, 15, 16), SNAP)
    assert not state.stop and actions == []


def test_a_slide_from_another_column_is_not_owned():
    state = touched(5, 3)
    assert faders.slide(state, SlideMoved(3, 6, 7)) == (state, False)


# Through Session Mode


def test_fx_modes_fader_columns_go_to_the_faders():
    state, actions = session.handle(FX_ON, PadPress(2, 1, True), SNAP)
    assert state.fader_touches[0].column == 2 and actions == []
    state, _ = session.handle(FX_ON, PadPress(11, 8, True), SNAP)
    assert state.fader_touches[0].pad == 8


def test_fx_modes_slots_and_bars_are_unchanged():
    state, actions = session.handle(FX_ON, PadPress(*layout.FX_SLOTS[0], True), SNAP)
    assert actions == [StoreFxSnapshot(0)] and state.fader_touches == ()
    state, _ = session.handle(FX_ON, PadPress(*min(layout.FX_LENGTHS), True), SNAP)
    assert state.fx_length == 1


def test_a_slide_onto_a_slot_ends_on_its_release_and_touches_no_snapshot():
    state, _ = session.handle(FX_ON, PadPress(11, 3, True), SNAP)
    state, _, _ = x(state, 11, 3, centre(11))
    state, actions = engine.slide(state, SlideMoved(3, 11, 12), SNAP)
    assert actions == []
    state, actions = session.handle(state, PadPress(12, 3, False), SNAP)
    assert state.fader_touches == () and not state.fader_undo_open
    assert actions == [EndUndoStep()]


def test_a_slide_onto_shift_ends_on_its_release_and_leaves_shift_alone():
    state, _ = session.handle(FX_ON, PadPress(2, 8, True), SNAP)
    state, _, _ = x(state, 2, 8, centre(2) + 10)
    state, _ = engine.slide(state, SlideMoved(8, 2, 1), SNAP)
    shifted = replace(state, shift=True)
    state, actions = session.handle(shifted, PadPress(1, 8, False), SNAP)
    assert state.shift and state.fader_touches == ()
    assert actions == [EndUndoStep()]


# Split view


SPLIT = State(split=True)


def test_split_faders_span_columns_10_to_14():
    state, _ = session.handle(SPLIT, PadPress(12, 4, True), SNAP)
    (touch,) = state.fader_touches
    assert (touch.first, touch.last) == (10, 14)
    _, actions, _ = x(state, 12, 4, centre(14) + 5)
    assert actions[-1] == SetFaderParameter(3, "Macro 4", 127.0)


def test_a_slide_onto_the_scenes_ends_on_its_release_and_launches_nothing():
    state, _ = session.handle(SPLIT, PadPress(14, 2, True), SNAP)
    state, _, _ = x(state, 14, 2, centre(14))
    state, actions = engine.slide(state, SlideMoved(2, 14, 15), SNAP)
    assert actions == []
    state, actions = session.handle(state, PadPress(15, 2, False), SNAP)
    assert state.fader_touches == () and actions == [EndUndoStep()]


@pytest.mark.parametrize("pad", [1, layout.MUTE_ROW, layout.SELECT_ROW])
def test_a_slide_onto_the_tracks_ends_on_its_release_and_fires_nothing(pad):
    state, _ = session.handle(SPLIT, PadPress(10, pad, True), SNAP)
    state, _, _ = x(state, 10, pad, centre(10) + 5)
    state, actions = engine.slide(state, SlideMoved(pad, 10, 9), SNAP)
    assert actions == []
    state, actions = session.handle(state, PadPress(9, pad, False), SNAP)
    assert state.fader_touches == () and actions == [EndUndoStep()]


def test_split_off_resets_the_faders():
    state, _ = session.handle(SPLIT, PadPress(12, 4, True), SNAP)
    state, _, _ = x(state, 12, 4, centre(13))
    state, actions = session.handle(state, PadPress(*layout.SESSION, True), SNAP)
    assert not state.split and state.fader_touches == () and not state.fader_undo_open
    assert actions == [EndUndoStep(), ShowMessage("Split view OFF")]


def test_split_render_draws_the_faders_in_columns_10_to_14():
    frame = session.render(SPLIT, SNAP)
    # Pad 2's fader is at 0: only its first pad is lit.
    assert [frame[(c, 2)] for c in range(10, 15)] == [Light(BLUE)] + [Light(OFF)] * 4


def test_x_rows_follow_the_split_view():
    assert engine.x_rows(SPLIT) == tuple(range(8))
    assert engine.x_rows(replace(SPLIT, mixer=True)) == ()


# Reset


def test_fx_off_resets_the_faders():
    state, _, _ = x(touched(), 5, 3, centre(8))
    state, actions = fx.toggle(state)
    assert state.fader_touches == () and not state.fader_undo_open
    assert actions == [EndUndoStep(), ShowMessage("FX Mode OFF")]


def test_mixer_on_resets_the_faders():
    state, _, _ = x(touched(), 5, 3, centre(8))
    state, actions = mixer.toggle(state)
    assert state.fader_touches == () and not state.fader_undo_open
    assert actions[0] == EndUndoStep()


def test_entering_linnstrument_mode_resets_the_faders():
    state, _, _ = x(touched(), 5, 3, centre(8))
    state, actions = column_1.handle(state, PadPress(*layout.MODE_PAD, True), SNAP)
    assert state.fader_touches == () and not state.fader_undo_open
    assert actions[0] == EndUndoStep()


def test_x_rows_follow_the_faders():
    assert engine.x_rows(FX_ON) == tuple(range(8))
    assert engine.x_rows(State()) == ()
    assert engine.x_rows(State(mixer=True)) == ()


# Render


def test_render_alternates_colours_and_lights_from_the_left():
    views = tuple(FaderView("P", value, 0.0, 9.0) for value in (0, 9, 4.5, 0, 0, 0, 0, 0))
    frame = faders.render(FX_ON, replace(SNAP, faders=views))
    assert [frame[(c, 1)] for c in range(2, 4)] == [Light(MAGENTA), Light(OFF)]
    assert all(frame[(c, 2)] == Light(BLUE) for c in range(2, 12))
    assert [frame[(c, 3)] for c in range(2, 12)].count(Light(MAGENTA)) == 6


def test_render_follows_the_finger_while_touched():
    state, _, _ = x(touched(), 5, 3, centre(11))
    frame = faders.render(state, SNAP)
    assert all(frame[(c, 3)] == Light(MAGENTA) for c in range(2, 12))


def test_render_dark_rows_and_dark_under_shift():
    snapshot = replace(SNAP, faders=(None,) * 8)
    assert set(faders.render(FX_ON, snapshot).values()) == {Light(OFF)}
    assert set(faders.render(replace(FX_ON, shift=True), SNAP).values()) == {Light(OFF)}


# Mapped FX: bindings


MAPPED = replace(FX_ON, fader_source="mapped")
BINDING = FaderBinding("Bass", 0, "Auto Filter", 1, 5, "Frequency")
MIXER_BINDING = FaderBinding("A Reverb", 0, None, 0, 0, "Track Volume")


def test_bindings_round_trip():
    bindings = (BINDING, None, MIXER_BINDING) + (None,) * 5
    text = faders.dump(bindings)
    assert json.loads(text)["v"] == 1
    assert faders.parse(text) == bindings


def test_binding_format():
    assert json.loads(faders.dump((BINDING,) + (None,) * 7)) == {
        "v": 1,
        "rows": [
            {
                "track": "Bass",
                "tn": 0,
                "device": "Auto Filter",
                "dn": 1,
                "param": 5,
                "name": "Frequency",
            }
        ]
        + [None] * 7,
    }


@pytest.mark.parametrize(
    "text",
    [
        "",
        "not json",
        "[]",
        '{"v": 2, "rows": [null, null, null, null, null, null, null, null]}',
        '{"v": 1, "rows": [null]}',
        '{"v": 1, "rows": 5}',
        '{"v": 1}',
        '{"v": 1, "rows": [{"track": "A"}, null, null, null, null, null, null, null]}',
        '{"v": 1, "rows": [{"track": "A", "tn": "x", "device": null, "dn": 0, "param": 0, '
        '"name": "V"}, null, null, null, null, null, null, null]}',
        '{"v": 1, "rows": [7, null, null, null, null, null, null, null]}',
    ],
)
def test_bad_binding_text_gives_empty_rows(text):
    assert faders.parse(text) == (None,) * 8


def test_dev_and_a_row_binds_in_mapped_fx():
    state = replace(MAPPED, dev=True)
    assert press(5, 3, state=state) == (state, [BindFader(2)])


def test_dev_and_a_row_in_device_fx_points_to_mapped_fx():
    state = replace(FX_ON, dev=True)
    assert press(5, 3, state=state) == (state, [ShowMessage("Dev + FX for Mapped FX")])


def test_a_bound_row_stores_and_saves():
    bound = FaderBound(2, BINDING, "Fader 3: Auto Filter Frequency")
    state, actions = engine.handle(MAPPED, bound, SNAP)
    assert state.fader_bindings[2] == BINDING
    assert actions == [
        SaveFaderBindings(faders.dump(state.fader_bindings)),
        ShowMessage("Fader 3: Auto Filter Frequency"),
    ]


def test_a_refused_bind_only_shows_its_message():
    state, actions = engine.handle(MAPPED, FaderBound(2, None, "Map it to a macro instead"), SNAP)
    assert state == MAPPED
    assert actions == [ShowMessage("Map it to a macro instead")]


def test_delete_and_a_bound_row_unbinds():
    bindings = (None, None, BINDING) + (None,) * 5
    state = replace(MAPPED, delete=True, fader_bindings=bindings)
    state, actions = press(5, 3, state=state)
    assert state.fader_bindings == (None,) * 8
    assert actions == [
        SaveFaderBindings(faders.dump((None,) * 8)),
        ShowMessage("Fader 3 unbound"),
    ]


def test_delete_and_an_unbound_row_does_nothing():
    state = replace(MAPPED, delete=True)
    assert press(5, 3, state=state) == (state, [])


def test_delete_in_device_fx_does_nothing():
    state = replace(FX_ON, delete=True)
    assert press(5, 3, state=state) == (state, [])


def test_a_bound_row_whose_parameter_is_gone():
    state = replace(MAPPED, fader_bindings=(None, None, BINDING) + (None,) * 5)
    snapshot = replace(SNAP, faders=(None,) * 8)
    assert press(5, 3, state=state, snapshot=snapshot) == (
        state,
        [ShowMessage("Fader 3: parameter not found")],
    )
    assert press(5, 4, state=state, snapshot=snapshot) == (state, [])
