import pytest

from BleakLoop.core import modes
from BleakLoop.core.layout import Window
from BleakLoop.core.modes import ClipSource, Mode, SceneSource, State, TrackControl


def test_entering_session_resets():
    state = State(mode=Mode.NOTE, track_control=TrackControl.MUTE, mixer=True, shift=True)
    entered = modes.enter(state, Mode.SESSION)
    assert entered.mode is Mode.SESSION
    assert entered.track_control is TrackControl.ARM
    assert not entered.mixer
    assert not entered.shift


def test_entering_note_keeps_track_control():
    state = State(mixer=True, shift=True, track_control=TrackControl.SOLO)
    entered = modes.enter(state, Mode.NOTE)
    assert entered.mode is Mode.NOTE
    assert not entered.mixer
    assert not entered.shift
    assert entered.track_control is TrackControl.SOLO


@pytest.mark.parametrize("start, target", [(Mode.SESSION, Mode.NOTE), (Mode.NOTE, Mode.SESSION)])
def test_entry_keeps_window_and_quantization_memory(start, target):
    state = State(mode=start, window=Window(3, 2), quantization_memory=7)
    entered = modes.enter(state, target)
    assert entered.window == Window(3, 2)
    assert entered.quantization_memory == 7


@pytest.mark.parametrize("start, target", [(Mode.SESSION, Mode.NOTE), (Mode.NOTE, Mode.SESSION)])
@pytest.mark.parametrize("source", [ClipSource(1, 2, True), SceneSource(3)])
def test_entry_clears_copy_and_delete(start, target, source):
    state = State(mode=start, copy=True, delete=True, copy_source=source)
    entered = modes.enter(state, target)
    assert not entered.copy
    assert not entered.delete
    assert entered.copy_source is None


@pytest.mark.parametrize("start, target", [(Mode.SESSION, Mode.NOTE), (Mode.NOTE, Mode.SESSION)])
def test_entry_keeps_fixed_length(start, target):
    assert modes.enter(State(mode=start, fixed_length=4), target).fixed_length == 4
