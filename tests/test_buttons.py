from pathlib import Path

import pytest

from BleakLoop.core import buttons, layout
from BleakLoop.core.model import ShowMessage
from tools.docs.manual import pads

FIXTURES = Path(__file__).parent / "fixtures" / "buttons"


def test_play_stop_comes_from_the_registry():
    assert layout.GLOBAL.play_stop == (1, 1)


def test_group_keeps_file_order_and_tuples():
    assert list(layout.DEVICE_CLIP.tracks) == [(16, 7), (16, 6)]
    assert layout.NAVIGATION_SHIFT.window[(16, 5)] == (0, -1)
    assert layout.FX.slots[8] == (12, 1)


def test_banks_are_column_13s_eight_pads():
    assert layout.FX.banks == {(13, bank): bank for bank in range(1, 9)}


@pytest.mark.parametrize("path", sorted(FIXTURES.glob("*.toml")), ids=lambda path: path.stem)
def test_invalid_file_raises(path):
    with pytest.raises(ValueError):
        buttons.load(path)


def test_sections_are_the_manuals_plus_held_modifiers():
    held = {"copy", "delete", "stop", "sequencer-copy", "sequencer-delete"}
    assert buttons.SECTIONS == set(pads.SECTIONS) | held


def test_the_shipped_file_loads():
    assert buttons.load(buttons.PATH).entries() == buttons.entries()


MESSAGES = buttons.load(Path(__file__).parent / "fixtures" / "messages.toml")


def test_say_formats_the_message_and_its_outcomes():
    assert MESSAGES.say("metronome", state="ON") == [ShowMessage("Metronome ON")]
    assert MESSAGES.say("metronome", "off") == [ShowMessage("Metronome off")]


def test_show_false_hides_the_message_and_its_outcomes():
    assert MESSAGES.say("undo") == []
    assert MESSAGES.say("undo", "done") == []


def test_a_refusal_shows_even_when_hidden():
    assert MESSAGES.refuse("undo", "no_track") == [ShowMessage("No selected track")]


def test_a_missing_placeholder_shows_the_raw_template():
    [message] = MESSAGES.say("metronome")
    assert message.text == "Metronome {state}"
    assert "metronome" in message.problem
    assert MESSAGES.system("moved") == "Controls moved to channel {channel}"


def test_system_formats():
    assert MESSAGES.system("moved", channel=3) == "Controls moved to channel 3"


def test_check_command(capsys):
    from tools import check_buttons

    assert check_buttons.main([]) == 0
    assert check_buttons.main([str(FIXTURES / "layer_clash.toml")]) == 1
    assert "navigation.delete" in capsys.readouterr().err


def test_a_function_whose_requirement_isnt_met_loads_dark_and_inert():
    from BleakLoop.core import engine, functions  # noqa: F401  registers every function
    from BleakLoop.core.modes import Mode, State

    registry = buttons.load(Path(__file__).parent / "fixtures" / "unmet_requirement.toml")
    button = registry.section("linnstrument").at((1, 5))
    state = State(mode=Mode.LINNSTRUMENT)
    assert button.function == "copy"
    assert functions.get("copy", state) is None
    assert functions.press(button, state, None) == (state, [])
    assert functions.light(button, state, None) == functions.Light(functions.OFF)


def test_a_fallback_that_cant_run_in_a_mode_is_dark_there():
    registry = buttons.load(Path(__file__).parent / "fixtures" / "dark_fallback.toml")
    session = registry.section("global")
    linnstrument = registry.section("linnstrument", session)
    assert session.at((1, 5))[1] == "fader_source"
    assert linnstrument.at((1, 5)) is None
    assert linnstrument.at((1, 6))[1] == "undo"
    assert linnstrument.at((1, 7))[1] == "back"
