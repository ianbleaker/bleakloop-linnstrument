"""The manual's pad maps and callout lists."""

from pathlib import Path

from BleakLoop.core import controls, leds
from BleakLoop.core.leds import Blink

from ..markers import read, replace_between
from . import columns, draw, pads, positions, surface
from .pads import LISTS, ordered
from .scenes import Layer

ROOT = Path(__file__).resolve().parents[3]
MANUAL = ROOT / "docs" / "manual.md"
MAPS = ROOT / "docs" / "manual"
SOURCE = Path(__file__).parent / "manual.md"
HEADER = (
    "<!-- Generated from tools/docs/manual/manual.md by PYTHONPATH=src python3 -m tools.docs. "
    "Edit that file, not this one. -->"
)

COLOUR_NAMES = {
    getattr(leds, name): name.lower()
    for name in ("RED", "YELLOW", "GREEN", "CYAN", "BLUE", "MAGENTA", "WHITE", "ORANGE", "LIME", "PINK")
}
BLINK_NAMES = {Blink.STEADY: "", Blink.TEMPO: " and blinking with the beat", Blink.FAST: " and blinking fast"}


def callouts(section):
    # The section's items, then what its pads do under Shift as a list of its own.
    lines = [_line(item) for item in ordered(section)]
    shifted = LISTS[section]
    if shifted is not None:
        variants = [item for item in ordered(shifted) if item.variant]
        if variants:
            lines += ["\nWith **Shift** held:\n\n", *(_line(item) for item in variants)]
    return "".join(lines)


def _line(item):
    return f"- **{item.name}**: {item.callout}\n"


def scene_lights():
    # The scene pads' colours, in the order scene_light tries them.
    states = [
        f"{COLOUR_NAMES[light.colour]}{BLINK_NAMES[light.blink]} {pads.SCENE_LIGHTS[state]}"
        for state, light in controls.SCENE_LIGHTS.items()
    ]
    return f"- **Scenes:** {'; '.join(states)}.\n"


def manual_text(text):
    # Rewrite each callout section between its marker pair, then the scene lights.
    for section in LISTS:
        start = f"<!-- callouts:{section} -->"
        end = f"<!-- /callouts:{section} -->"
        text = replace_between(text, start, end, callouts(section), MANUAL)
    return replace_between(
        text, "<!-- lights:scenes -->", "<!-- /lights:scenes -->", scene_lights(), MANUAL
    )


def header(text):
    # The generated-file note after the source's title line, as docs/buttons.md has it.
    title, _, rest = text.partition("\n")
    return f"{title}\n\n{HEADER}\n{rest}"


def source():
    text = read(SOURCE)
    if text is None:
        raise FileNotFoundError(f"{SOURCE}: the manual's source is missing")
    return text


def expected():
    files = {}
    for layer in Layer:
        files[MAPS / f"{layer.slug}.svg"] = draw.map_svg(layer)
    for slug in columns.FIGURES:
        files[MAPS / f"{slug}.svg"] = columns.figure_svg(slug)
    files[MAPS / f"{surface.SLUG}.svg"] = surface.svg()
    files[MANUAL] = manual_text(positions.fill(header(source())))
    return files


def strays():
    # Maps left over from a renamed or removed layer.
    expected_maps = {MAPS / f"{layer.slug}.svg" for layer in Layer}
    expected_maps |= {MAPS / f"{slug}.svg" for slug in columns.FIGURES}
    expected_maps.add(MAPS / f"{surface.SLUG}.svg")
    return sorted(set(MAPS.glob("*.svg")) - expected_maps)
