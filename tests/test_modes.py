import pytest

from BleakLoop.core import modes
from BleakLoop.core.layout import Window
from BleakLoop.core.modes import Mode, State, TrackControl


def test_entering_session_resets():
    state = State(mode=Mode.NOTE, track_control=TrackControl.MUTE, mixer=True, shift=True)
    entered = modes.enter(state, Mode.SESSION)
    assert entered.mode is Mode.SESSION
    assert entered.track_control is TrackControl.ARM
    assert not entered.mixer
    assert not entered.shift


def test_entering_note_resets_mixer_and_shift_only():
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
