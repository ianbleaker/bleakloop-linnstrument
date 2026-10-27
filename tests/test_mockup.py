import json

import pytest

from tools.docs import mockup
from tools.docs.manual import draw
from tools.docs.manual.scenes import Layer
from tools.docs.svg import SWATCHES, rect

from BleakLoop.core.leds import WHITE


def run(tmp_path, spec):
    path = tmp_path / "spec.json"
    path.write_text(json.dumps(spec))
    out = tmp_path / "out.svg"
    code = mockup.main([str(path), "-o", str(out)])
    return code, out.read_text() if out.exists() else None


@pytest.mark.parametrize("layer", [Layer.SESSION, Layer.FX, Layer.LINNSTRUMENT])
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
