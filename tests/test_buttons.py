from itertools import combinations
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


@pytest.mark.parametrize("path", sorted(FIXTURES.glob("*.toml")), ids=lambda path: path.stem)
def test_invalid_file_raises(path):
    with pytest.raises(ValueError):
        buttons.load(path)


def test_sections_are_the_manuals_plus_held_modifiers():
    held = {"copy", "delete", "stop", "sequencer-copy", "sequencer-delete"}
    assert buttons.SECTIONS == set(pads.SECTIONS) | held


@pytest.mark.parametrize("layer", list(pads.LAYERS), ids=lambda layer: layer.name)
def test_no_two_buttons_share_a_pad_in_a_layer(layer):
    sections = pads.LAYERS[layer]
    placed = [
        (id, item["section"], tuple(item["pad"]))
        for id, item in buttons.entries().items()
        if item["section"] in sections and "pad" in item
    ]
    clashes = [(a[0], b[0]) for a, b in combinations(placed, 2) if a[2] == b[2]]
    assert clashes == []


MESSAGES = buttons.load(Path(__file__).parent / "fixtures" / "messages.toml")


def test_say_formats_the_message_and_its_outcomes():
    assert MESSAGES.say("global.metronome", state="ON") == [ShowMessage("Metronome ON")]
    assert MESSAGES.say("global.metronome", "off") == [ShowMessage("Metronome off")]


def test_show_false_hides_the_message_and_its_outcomes():
    assert MESSAGES.say("global.hidden") == []
    assert MESSAGES.say("global.hidden", "done") == []


def test_a_refusal_shows_even_when_hidden():
    assert MESSAGES.refuse("global.hidden", "no_track") == [ShowMessage("No selected track")]


def test_a_missing_placeholder_shows_the_raw_template():
    [message] = MESSAGES.say("global.metronome")
    assert message.text == "Metronome {state}"
    assert "global.metronome" in message.problem
    assert MESSAGES.system("moved") == "Controls moved to channel {channel}"


def test_system_formats():
    assert MESSAGES.system("moved", channel=3) == "Controls moved to channel 3"
