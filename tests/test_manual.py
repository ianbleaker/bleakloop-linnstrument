import pytest

from BleakLoop.core import engine
from BleakLoop.core.leds import OFF
from tools.manual import __main__ as generator
from tools.manual.pads import DIMMED, blocks, items, labels
from tools.manual.scenes import SCENES, Layer


def frame(layer):
    return engine.render(*SCENES[layer])


def in_block(layer, column, pad):
    return any(column in block.columns and pad in block.pads for block in blocks(layer))


@pytest.mark.parametrize("layer", Layer)
def test_every_lit_pad_is_labelled(layer):
    unlabelled = [
        key
        for key, light in sorted(frame(layer).items())
        if light.colour != OFF
        and key not in labels(layer)
        and not in_block(layer, *key)
        and key[0] not in DIMMED.get(layer, ())
    ]
    assert unlabelled == []


@pytest.mark.parametrize("layer", Layer)
def test_every_label_is_a_pad_of_the_layer(layer):
    assert set(labels(layer)) <= set(frame(layer))


@pytest.mark.parametrize("layer", Layer)
def test_labels_fit_on_a_pad(layer):
    assert [label for label in labels(layer).values() if len(label) > 7] == []


@pytest.mark.parametrize("layer", Layer)
def test_no_pad_is_in_two_items(layer):
    keys = [key for item in items(layer) for key in item.keys]
    assert len(keys) == len(set(keys))


def test_manual_is_current():
    assert generator.check() == []
