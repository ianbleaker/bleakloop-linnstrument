"""The manual's pad maps and callout lists."""

from pathlib import Path

from ..markers import read, replace_between
from . import columns, draw, surface
from .pads import LISTS, ordered
from .scenes import Layer

ROOT = Path(__file__).resolve().parents[3]
MANUAL = ROOT / "docs" / "manual.md"
MAPS = ROOT / "docs" / "manual"


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


def manual_text(text):
    # Rewrite each callout section between its marker pair.
    for section in LISTS:
        start = f"<!-- callouts:{section} -->"
        end = f"<!-- /callouts:{section} -->"
        text = replace_between(text, start, end, callouts(section), MANUAL)
    return text


def expected():
    files = {}
    for layer in Layer:
        files[MAPS / f"{layer.slug}.svg"] = draw.map_svg(layer)
    for slug in columns.FIGURES:
        files[MAPS / f"{slug}.svg"] = columns.figure_svg(slug)
    files[MAPS / f"{surface.SLUG}.svg"] = surface.svg()
    files[MANUAL] = manual_text(read(MANUAL) or "")
    return files


def strays():
    # Maps left over from a renamed or removed layer.
    expected_maps = {MAPS / f"{layer.slug}.svg" for layer in Layer}
    expected_maps |= {MAPS / f"{slug}.svg" for slug in columns.FIGURES}
    expected_maps.add(MAPS / f"{surface.SLUG}.svg")
    return sorted(set(MAPS.glob("*.svg")) - expected_maps)
