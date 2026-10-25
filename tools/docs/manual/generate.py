"""The manual's pad maps and callout lists."""

from pathlib import Path

from ..markers import read, replace_between
from . import draw
from .pads import LISTS, ordered, shift_note
from .scenes import Layer

ROOT = Path(__file__).resolve().parents[3]
MANUAL = ROOT / "docs" / "manual.md"
MAPS = ROOT / "docs" / "manual"


def callouts(section):
    lines = []
    for item in ordered(section):
        note = shift_note(section, item)
        shift = f" *(Shift: {note})*" if note else ""
        lines.append(f"- **{item.name}**: {item.callout}{shift}\n")
    return "".join(lines)


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
    files[MANUAL] = manual_text(read(MANUAL) or "")
    return files


def strays():
    # Maps left over from a renamed or removed layer.
    expected_maps = {MAPS / f"{layer.slug}.svg" for layer in Layer}
    return sorted(set(MAPS.glob("*.svg")) - expected_maps)
