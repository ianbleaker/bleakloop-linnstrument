import pytest

from BleakLoop.core import modes
from BleakLoop.core.layout import Window
from BleakLoop.core.modes import (
    ClipSource,
    FxRack,
    Glide,
    Lift,
    Mode,
    Morph,
    Origin,
    SceneSource,
    State,
    Touch,
)


def test_entering_session_resets():
    state = State(mode=Mode.LINNSTRUMENT, mixer=True, shift=True)
    entered = modes.enter(state, Mode.SESSION)
    assert entered.mode is Mode.SESSION
    assert not entered.mixer


@pytest.mark.parametrize(
    "state, origin",
    [(State(), Origin.SESSION), (State(mixer=True), Origin.MIXER), (State(fx=True), Origin.FX)],
)
def test_entering_linnstrument_records_the_origin(state, origin):
    assert modes.enter(state, Mode.LINNSTRUMENT).came_from is origin


def test_entering_session_keeps_the_origin():
    state = State(mode=Mode.LINNSTRUMENT, came_from=Origin.FX)
    assert modes.enter(state, Mode.SESSION).came_from is Origin.FX


def test_entering_linnstrument_turns_mixer_off():
    entered = modes.enter(State(mixer=True), Mode.LINNSTRUMENT)
    assert entered.mode is Mode.LINNSTRUMENT
    assert not entered.mixer


@pytest.mark.parametrize("start, target", [(Mode.SESSION, Mode.LINNSTRUMENT), (Mode.LINNSTRUMENT, Mode.SESSION)])
def test_entry_keeps_window_and_quantization_memory(start, target):
    state = State(mode=start, window=Window(3, 2), quantization_memory=7)
    entered = modes.enter(state, target)
    assert entered.window == Window(3, 2)
    assert entered.quantization_memory == 7


@pytest.mark.parametrize("start, target", [(Mode.SESSION, Mode.LINNSTRUMENT), (Mode.LINNSTRUMENT, Mode.SESSION)])
@pytest.mark.parametrize("source", [ClipSource(1, 2, True), SceneSource(3)])
def test_entry_clears_copy_and_delete(start, target, source):
    state = State(mode=start, copy=True, delete=True, copy_source=source)
    entered = modes.enter(state, target)
    assert not entered.copy
    assert not entered.delete
    assert entered.copy_source is None


@pytest.mark.parametrize("shift", [True, False])
def test_entering_session_keeps_shift(shift):
    # Shift is column 1 pad 8 in both modes, and its control-split release still arrives.
    assert modes.enter(State(mode=Mode.LINNSTRUMENT, shift=shift), Mode.SESSION).shift is shift


def test_entering_linnstrument_clears_shift():
    # The firmware sends the release of a pad pressed in User Firmware Mode as a User
    # Firmware note, so a Shift held across this entry never reports its release.
    assert not modes.enter(State(shift=True), Mode.LINNSTRUMENT).shift


@pytest.mark.parametrize("start, target", [(Mode.SESSION, Mode.LINNSTRUMENT), (Mode.LINNSTRUMENT, Mode.SESSION)])
def test_entry_keeps_fixed_length(start, target):
    assert modes.enter(State(mode=start, fixed_length=4), target).fixed_length == 4


@pytest.mark.parametrize("start, target", [(Mode.SESSION, Mode.LINNSTRUMENT), (Mode.LINNSTRUMENT, Mode.SESSION)])
def test_entry_clears_fader_state(start, target):
    state = State(
        mode=start,
        mixer=True,
        touches=(Touch(2, 0, 3, 0.5),),
        lifts=(Lift(3, 1, 4),),
        glides=(Glide(0, 0.5, 0.6),),
        glide_ms=123.0,
        undo_open=True,
    )
    entered = modes.enter(state, target)
    assert entered.touches == ()
    assert entered.lifts == ()
    assert entered.glides == ()
    assert entered.glide_ms is None
    assert not entered.undo_open


@pytest.mark.parametrize("start, target", [(Mode.SESSION, Mode.LINNSTRUMENT), (Mode.LINNSTRUMENT, Mode.SESSION)])
def test_entry_starts_on_controls_page(start, target):
    assert modes.enter(State(mode=start, scene_page=True), target).scene_page is False


@pytest.mark.parametrize("target", [Mode.SESSION, Mode.LINNSTRUMENT])
def test_entry_turns_fx_off_but_keeps_the_morph(target):
    morph = Morph(slot=2, start_beats=0.0, end_beats=16.0, last_beats=1.0)
    slots = (None,) * 3 + ((FxRack("A", "Rack", 0, (0.5,)),),) + (None,) * 12
    state = State(fx=True, fx_length=4, fx_slots=slots, morph=morph, fx_undo_open=True, fx_landed=1)
    entered = modes.enter(state, target)
    assert not entered.fx
    assert entered.fx_length is None
    assert entered.morph == morph
    assert entered.fx_undo_open
    assert entered.fx_slots == slots
    assert entered.fx_landed == 1
