"""Track-/+ and its per-button options: arm and rack, both on by default."""

from dataclasses import replace

import pytest

from BleakLoop.core import buttons, engine, functions, layout
from BleakLoop.core.model import PadPress, SequencerView, StepTrack
from BleakLoop.core.modes import Mode, Origin, State
from tests.support import SNAP


def _press(state, key, snapshot=SNAP):
    return engine.handle(state, PadPress(*key, True), snapshot)


@pytest.fixture
def track_on_column_1(monkeypatch):
    # Track+ in place of Linnstrument Mode's Fixed Length.
    monkeypatch.delattr(layout.LINNSTRUMENT, "fixed_length")
    monkeypatch.setattr(layout.LINNSTRUMENT, "tracks", {(1, 5): 1}, raising=False)


def test_the_options_default_on():
    button = buttons.Button("track_next", "tracks", (16, 6), 1)
    assert functions.options(button) == {"arm": True, "rack": True}
    assert functions.press(button, State(), SNAP) == (State(), [StepTrack(1, arm=True, rack=True)])


def test_a_buttons_options_override_the_defaults():
    button = buttons.Button("track_next", "tracks", (16, 6), 1, {"arm": False})
    assert functions.press(button, State(), SNAP)[1] == [StepTrack(1, arm=False, rack=True)]
    button = buttons.Button("track_next", "tracks", (16, 6), 1, {"rack": False})
    assert functions.press(button, State(), SNAP)[1] == [StepTrack(1, arm=True, rack=False)]


def test_sequencer_mode_never_arms_on_a_step():
    button = buttons.Button("track_next", "tracks", (16, 6), 1, {"arm": True})
    state = State(mode=Mode.SEQUENCER)
    assert functions.press(button, state, SNAP)[1] == [StepTrack(1, arm=False, rack=True)]


def test_linnstrument_mode_from_sequencer_arms_and_back_resyncs(track_on_column_1):
    sequencer = State(mode=Mode.SEQUENCER, seq_track=0, seq_set_arms=(True, False), seq_saved_arms=(False, False))
    state, _ = _press(sequencer, layout.SEQUENCER_GLOBAL.linnstrument_mode)
    assert state.mode is Mode.LINNSTRUMENT and state.came_from is Origin.SEQUENCER
    state, actions = _press(state, (1, 5))
    assert actions == [StepTrack(1, arm=True, rack=True)]
    state, _ = _press(state, layout.LINNSTRUMENT.back)
    assert state.mode is Mode.SEQUENCER
    # Live armed track 1 alone; the next display tick follows the selection to it.
    snapshot = replace(SNAP, arms=(False, True), sequencer=SequencerView(track=1, is_midi=True))
    state, actions = engine.seq_sync(state, snapshot)
    assert state.seq_track == 1 and actions == []
    assert state.seq_set_arms == (False, True)


def _shipped_with(tmp_path, text):
    path = tmp_path / "buttons.toml"
    path.write_text(buttons.PATH.read_text(encoding="utf-8") + text, encoding="utf-8")
    return path


def test_a_button_sets_its_options_in_the_file(tmp_path):
    text = '\n[linnstrument_device_clip.track_next]\npad = [1, 2]\ndoes = "tracks"\nvalue = 1\noptions = { arm = false }\n'
    section = buttons.load(_shipped_with(tmp_path, text)).section("linnstrument-device-clip")
    assert section.at((1, 2)).options == {"arm": False}


@pytest.mark.parametrize(
    "options, error",
    [("{ solo = true }", "tracks has no option 'solo'"), ('{ arm = "no" }', "options has the wrong type")],
)
def test_an_unknown_or_non_boolean_option_is_refused(tmp_path, options, error):
    text = f'\n[linnstrument_device_clip.track_next]\npad = [1, 2]\ndoes = "tracks"\nvalue = 1\noptions = {options}\n'
    with pytest.raises(ValueError, match=error):
        buttons.load(_shipped_with(tmp_path, text))


def test_a_function_without_options_refuses_one(tmp_path):
    text = "\n[global.undo]\npad = [1, 6]\noptions = { arm = true }\n"
    text = buttons.PATH.read_text(encoding="utf-8").replace("[global.undo]\npad = [1, 6]\n", "") + text
    path = tmp_path / "buttons.toml"
    path.write_text(text, encoding="utf-8")
    with pytest.raises(ValueError, match="undo has no option 'arm'; its options: none"):
        buttons.load(path)
