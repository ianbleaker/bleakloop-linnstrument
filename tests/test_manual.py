import re

import pytest

from BleakLoop.core import controls, engine, layout
from BleakLoop.core.leds import OFF
from tools.docs import __main__ as generator
from tools.docs import buttons as button_docs
from tools.docs.manual.columns import FIGURES
from tools.docs.manual import pads, positions
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


@pytest.fixture
def moved():
    # Move shipped buttons for one test: moved(section, attr, key). Restored afterwards, since
    # the Sections are module-level.
    undo = []

    def move(section, attr, key):
        undo.append((section, attr, getattr(section, attr)))
        setattr(section, attr, key)

    yield move
    for section, attr, key in reversed(undo):
        setattr(section, attr, key)


@pytest.mark.parametrize(
    "placeholder, text",
    [
        ("{pad:view.stop}", "column 15, pad 8"),
        ("{pad:navigation.session,navigation.mixer,navigation.fx}", "column 16, pads 1–3"),
        ("{pad:navigation_shift.window}", "column 16, pads 5–8"),
        ("{row:linnstrument.back}", "pad 7"),
        ("{row:navigation_shift.window}", "pads 5–8"),
        ("{column:fx.bars}", "column 14"),
        ("{runs:fx.slots}", "1–8 in column 11, 9–16 in column 12"),
        ("{runs:sequencer_settings.pages}", "1–8 in column 12, 9–16 in column 13"),
    ],
)
def test_placeholders_render_the_shipped_positions(placeholder, text):
    assert positions.fill(placeholder) == text


def test_a_moved_button_moves_its_position(moved):
    moved(layout.VIEW, "stop", (15, 6))
    assert positions.fill("Stop ({pad:view.stop})") == "Stop (column 15, pad 6)"


def test_a_group_spread_over_columns_raises(moved):
    moved(layout.NAVIGATION, "mixer", (15, 2))
    with pytest.raises(ValueError, match="navigation.session,navigation.mixer"):
        positions.fill("{pad:navigation.session,navigation.mixer}")


@pytest.mark.parametrize("placeholder", ["{pads:view.stop}", "{pad:view.nothing}", "{pad:nowhere.stop}"])
def test_an_unknown_kind_or_ref_raises(placeholder):
    with pytest.raises(ValueError, match=re.escape(placeholder)):
        positions.fill(placeholder)


def test_text_without_a_kind_passes_through():
    assert positions.fill("Type `{bpm}` here.") == "Type `{bpm}` here."


def test_a_column_heading_follows_its_buttons(moved):
    moved(layout.VIEW, "stop", (16, 8))
    moved(layout.VIEW, "unmute_all", (16, 7))
    assert "## Column 16: Session, Mixer and FX Mode" in button_docs.text()
