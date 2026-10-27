"""Draw a mockup pad figure from a JSON spec, with the manual's own drawer.

PYTHONPATH=src python3 -m tools.docs.mockup SPEC.json [-o OUT.svg]
"""

import argparse
import json
import sys
from dataclasses import fields, replace

from BleakLoop.core import engine, leds
from BleakLoop.core.leds import Blink, Light

from .manual import draw
from .manual.pads import DIMMED, Block, blocks, labels
from .manual.scenes import SCENES, Layer

COLOURS = {
    name.lower(): getattr(leds, name)
    for name in (
        "RED",
        "YELLOW",
        "GREEN",
        "CYAN",
        "BLUE",
        "MAGENTA",
        "OFF",
        "WHITE",
        "ORANGE",
        "LIME",
        "PINK",
    )
}
BLINKS = {"steady": Blink.STEADY, "tempo": Blink.TEMPO, "fast": Blink.FAST}
SPEC_KEYS = {"title", "panels"}
PANEL_KEYS = {"layer", "columns", "caption", "state", "lights", "labels", "blocks"}
BLOCK_KEYS = {"name", "columns", "pads"}


class SpecError(Exception):
    pass


def mockup(spec):
    _known(spec, SPEC_KEYS, "spec")
    panels = spec.get("panels")
    if not isinstance(panels, list) or not panels:
        raise SpecError("spec: panels must be a non-empty list")
    layers = [_layer(p) for p in panels]
    title = spec.get("title", draw.TITLES[layers[0]])
    return draw.figure(title, [_panel(p, layer) for p, layer in zip(panels, layers)])


def _panel(spec, layer):
    _known(spec, PANEL_KEYS, "panel")
    state, snapshot = SCENES[layer]
    state = _state(state, spec.get("state", {}))
    frame = engine.render(state, snapshot)
    for key, light in spec.get("lights", {}).items():
        frame[_key(key)] = _light(light)
    pad_labels = labels(layer)
    for key, label in spec.get("labels", {}).items():
        if label == "":
            pad_labels.pop(_key(key), None)
        else:
            pad_labels[_key(key)] = label
    extra = [_block(block) for block in spec.get("blocks", [])]
    columns = _run(spec.get("columns", list(range(1, 17))), "columns")
    return draw.panel(
        frame,
        columns,
        pad_labels,
        blocks(layer) + extra,
        caption=spec.get("caption"),
        dimmed=DIMMED.get(layer, ()),
    )


def _layer(spec):
    try:
        return Layer(spec.get("layer"))
    except (AttributeError, ValueError):
        raise SpecError(f"unknown layer: {spec.get('layer') if isinstance(spec, dict) else spec}")


def _state(state, overrides):
    names = {field.name for field in fields(state)}
    for name, value in overrides.items():
        if name not in names:
            raise SpecError(f"unknown state field: {name}")
        if not isinstance(value, (bool, int, float, str)) and value is not None:
            raise SpecError(f"state field {name}: only JSON scalars")
    return replace(state, **overrides)


def _light(light):
    if isinstance(light, str):
        light = [light, "steady"]
    if not isinstance(light, list) or len(light) != 2:
        raise SpecError(f"bad light: {light}, want a colour or [colour, blink]")
    colour, blink = light
    if colour not in COLOURS:
        raise SpecError(f"unknown colour: {colour}")
    if blink not in BLINKS:
        raise SpecError(f"unknown blink: {blink}")
    return Light(COLOURS[colour], BLINKS[blink])


def _block(spec):
    _known(spec, BLOCK_KEYS, "block")
    name = spec.get("name")
    if not isinstance(name, str):
        raise SpecError("block: name must be a string")
    columns = _run(spec.get("columns"), "block columns")
    pads = _run(spec.get("pads"), "block pads")
    return Block(name, range(columns[0], columns[-1] + 1), range(pads[0], pads[-1] + 1), "")


def _run(numbers, what):
    # An explicit list of consecutive numbers.
    if (
        not isinstance(numbers, list)
        or not numbers
        or not all(isinstance(n, int) for n in numbers)
        or numbers != list(range(numbers[0], numbers[0] + len(numbers)))
    ):
        raise SpecError(f"{what}: a list of consecutive numbers, got {numbers}")
    return numbers


def _key(key):
    try:
        column, pad = (int(part) for part in key.split(","))
    except ValueError:
        raise SpecError(f"bad pad key: {key!r}, want 'column,pad'")
    return column, pad


def _known(spec, keys, what):
    if not isinstance(spec, dict):
        raise SpecError(f"{what}: must be an object")
    unknown = sorted(set(spec) - keys)
    if unknown:
        raise SpecError(f"{what}: unknown key {unknown[0]}")


def main(argv):
    parser = argparse.ArgumentParser(prog="python3 -m tools.docs.mockup")
    parser.add_argument("spec")
    parser.add_argument("-o", "--output")
    args = parser.parse_args(argv)
    try:
        with open(args.spec, encoding="utf-8") as file:
            svg = mockup(json.load(file))
    except (OSError, json.JSONDecodeError, SpecError) as error:
        print(f"mockup: {error}", file=sys.stderr)
        return 1
    if args.output:
        with open(args.output, "w", encoding="utf-8", newline="\n") as file:
            file.write(svg)
    else:
        sys.stdout.write(svg)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
