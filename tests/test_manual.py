import pytest

from BleakLoop.core import controls, engine
from BleakLoop.core.leds import OFF
from tools.docs import __main__ as generator
from tools.docs.manual.columns import FIGURES
from tools.docs.manual import pads
from tools.docs.manual.pads import DIMMED, blocks, items, labels, section_labels
from tools.docs.manual.scenes import SCENES, Layer


def too_wide(label):
    # At most 7 characters a line, and at most two lines.
    lines = label.split("\n")
    return len(lines) > 2 or any(len(line) > 7 for line in lines)


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
    assert [label for label in labels(layer).values() if too_wide(label)] == []


@pytest.mark.parametrize("layer", Layer)
def test_no_pad_is_in_two_items(layer):
    keys = [key for item in items(layer) for key in item.keys]
    assert len(keys) == len(set(keys))


COLUMN_PANELS = [
    (column, scene, section)
    for _, column, panels in FIGURES.values()
    for _, scene, section in panels
]


@pytest.mark.parametrize("column, scene, section", COLUMN_PANELS)
def test_every_lit_pad_of_a_column_panel_is_labelled(column, scene, section):
    lit = {
        key
        for key, light in engine.render(*scene).items()
        if key[0] == column and light.colour != OFF
    }
    assert lit - set(section_labels(section)) == set()
    assert set(section_labels(section)) <= {key for key in engine.render(*scene) if key[0] == column}


@pytest.mark.parametrize("column, scene, section", COLUMN_PANELS)
def test_column_panel_labels_fit_on_a_pad(column, scene, section):
    assert [label for label in section_labels(section).values() if too_wide(label)] == []


def test_every_scene_light_is_described():
    assert set(pads.SCENE_LIGHTS) == set(controls.SCENE_LIGHTS)


def test_generated_docs_are_current():
    assert generator.check() == []
