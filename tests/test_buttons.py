from itertools import combinations
from pathlib import Path

import pytest

from BleakLoop.core import buttons, layout
from tools.docs.manual import pads

FIXTURES = Path(__file__).parent / "fixtures" / "buttons"


def test_play_stop_comes_from_the_registry():
    assert layout.PLAY_STOP == (1, 1)


def test_group_keeps_file_order_and_tuples():
    assert list(layout.DEVICE_CLIP_TRACK_STEPS) == [(16, 7), (16, 6)]
    assert layout.WINDOW_MOVES[(16, 5)] == (0, -1)
    assert layout.FX_SLOTS[8] == (12, 1)


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
