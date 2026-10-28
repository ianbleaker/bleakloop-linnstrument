import json

import pytest

from tools.docs import mockup
from tools.docs.manual import draw
from tools.docs.manual.scenes import Layer
from tools.docs.svg import SWATCHES, rect

from BleakLoop.core import layout
from BleakLoop.core.leds import BLUE, WHITE


def run(tmp_path, spec):
    path = tmp_path / "spec.json"
    path.write_text(json.dumps(spec))
    out = tmp_path / "out.svg"
    code = mockup.main([str(path), "-o", str(out)])
    return code, out.read_text() if out.exists() else None


@pytest.mark.parametrize("layer", [Layer.SESSION, Layer.FX, Layer.SEQUENCER_SHIFT])
def test_a_layer_alone_is_its_map(tmp_path, layer):
    code, svg = run(tmp_path, {"panels": [{"layer": layer.slug}]})
    assert code == 0
    assert svg == draw.map_svg(layer)


def test_a_light_override_changes_the_fill(tmp_path):
    # Column 15 pad 8, Stop, is red on the Session map; the pad's rect sits at its column.
    _, svg = run(
        tmp_path, {"panels": [{"layer": "session", "columns": [15], "lights": {"15,8": "white"}}]}
    )
    assert rect(16, 40 + 7 * 46, 40, 40, SWATCHES[WHITE]) in svg


def test_an_empty_label_removes_it(tmp_path):
    _, before = run(tmp_path, {"panels": [{"layer": "session"}]})
    _, after = run(tmp_path, {"panels": [{"layer": "session", "labels": {"15,8": ""}}]})
    assert ">Stop</text>" in before
    assert ">Stop</text>" not in after


def test_a_layout_override_moves_a_pad_and_its_label(tmp_path):
    # Session is blue on column 16 pad 1; moved to pad 3, its label and light go with it.
    spec = {"panels": [{"layer": "session", "columns": [16]}]}
    _, before = run(tmp_path, spec)
    _, after = run(tmp_path, {**spec, "layout": {"SESSION": "16,3", "FX": "16,1"}})
    assert rect(16, 40, 40, 40, SWATCHES[BLUE]) in before
    assert rect(16, 40 + 2 * 46, 40, 40, SWATCHES[BLUE]) in after
    assert after.index(">FX</text>") < after.index(">Session</text>")


def test_a_layout_override_moves_the_pads_aliases(tmp_path):
    # Source, FX's Shift function, is drawn on pad 3 and follows FX to pad 4.
    spec = {"panels": [{"layer": "session-shift", "columns": [16]}]}
    source = '<text x="36" y="{}" font-size="9" fill="#ffffff" text-anchor="middle">Source</text>'
    _, before = run(tmp_path, spec)
    _, after = run(tmp_path, {**spec, "layout": {"FX": "16,4", "RESERVED": []}})
    assert source.format(63 + 2 * 46) in before
    assert source.format(63 + 3 * 46) in after
    assert layout.FADER_SOURCE == layout.FX == (16, 3)


def test_an_overridden_alias_stays_put():
    with mockup._layout({"FX": "16,4", "FADER_SOURCE": "16,2"}):
        assert (layout.FX, layout.FADER_SOURCE) == ((16, 4), (16, 2))


def test_ring_labels_follow_their_direction(tmp_path):
    # Listed out of the stock order, each pad still names its own step.
    moves = {"16,8": [0, -1], "16,7": [0, 1], "16,6": [-1, 0], "16,5": [1, 0]}
    tempo = {"16,2": 1, "16,1": -1}
    _, svg = run(
        tmp_path,
        {
            "layout": {"WINDOW_MOVES": moves, "TEMPO_STEPS": tempo},
            "panels": [{"layer": "session-shift", "columns": [16]}],
        },
    )
    names = [">Tempo-</text>", ">Tempo+</text>", ">Right</text>", ">Left</text>", ">Down</text>",
             ">Up</text>"]
    assert sorted(names, key=svg.index) == names


def test_a_layout_override_is_undone(tmp_path):
    session, steps = layout.SESSION, layout.DEVICE_CLIP_TRACK_STEPS
    run(
        tmp_path,
        {
            "layout": {"SESSION": "16,3", "DEVICE_CLIP_TRACK_STEPS": {"16,1": -1, "16,2": 1}},
            "panels": [{"layer": "session"}],
        },
    )
    assert (layout.SESSION, layout.DEVICE_CLIP_TRACK_STEPS) == (session, steps)
    assert run(tmp_path, {"panels": [{"layer": "session"}]})[1] == draw.map_svg(Layer.SESSION)


@pytest.mark.parametrize(
    "overrides",
    [
        {"ROWS": 4},
        {"SESSION": [16, 1]},
        {"RESERVED": "16,6"},
        {"WINDOW_MOVES": ["16,1"]},
        {"DEVICE_CLIP_TRACK_STEPS": {"16,7": {"step": -1}}},
    ],
)
def test_a_bad_layout_exits_non_zero(tmp_path, capsys, overrides):
    code, svg = run(tmp_path, {"layout": overrides, "panels": [{"layer": "session"}]})
    assert code != 0 and svg is None
    assert len(capsys.readouterr().err.strip().splitlines()) == 1


@pytest.mark.parametrize(
    "panel",
    [
        {"layer": "session", "colour": "red"},
        {"layer": "no-such-layer"},
        {"layer": "session", "lights": {"15,8": "mauve"}},
        {"layer": "session", "lights": {"15,8": ["red", "slow"]}},
        {"layer": "session", "state": {"no_such_field": True}},
        {"layer": "session", "columns": [1, 3]},
        {"layer": "session", "blocks": [{"name": "X", "columns": [2], "pads": [1, 3]}]},
    ],
)
def test_a_bad_spec_exits_non_zero(tmp_path, capsys, panel):
    code, svg = run(tmp_path, {"panels": [panel]})
    assert code != 0 and svg is None
    assert len(capsys.readouterr().err.strip().splitlines()) == 1
