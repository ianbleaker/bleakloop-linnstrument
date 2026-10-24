"""Generate the manual's pad maps and callout lists, or check they're current.

PYTHONPATH=src python3 -m tools.manual [--check]
"""

import re
import sys
from pathlib import Path

from . import draw
from .pads import LISTS, ordered, shift_note
from .scenes import Layer

ROOT = Path(__file__).resolve().parents[2]
MANUAL = ROOT / "docs" / "manual.md"
MAPS = ROOT / "docs" / "manual"


class MissingMarkers(Exception):
    pass


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
        pattern = re.compile(re.escape(start) + r"\n.*?" + re.escape(end), re.DOTALL)
        if not pattern.search(text):
            raise MissingMarkers(f"{MANUAL}: missing callout markers for {section}")
        text = pattern.sub(
            lambda _: f"{start}\n{callouts(section)}{end}", text, count=1
        )
    return text


def expected():
    files = {}
    for layer in Layer:
        files[MAPS / f"{layer.slug}.svg"] = draw.map_svg(layer)
    files[MANUAL] = manual_text(_read(MANUAL) or "")
    return files


def write():
    MAPS.mkdir(parents=True, exist_ok=True)
    for path, text in expected().items():
        if _read(path) != text:
            path.write_text(text, encoding="utf-8", newline="\n")
    for path in _strays():
        path.unlink()


def check():
    # Every stale or missing path; nothing is written.
    try:
        files = expected()
    except MissingMarkers:
        return [MANUAL]
    return [path for path, text in files.items() if _read(path) != text] + _strays()


def _strays():
    # Maps left over from a renamed or removed layer.
    expected_maps = {MAPS / f"{layer.slug}.svg" for layer in Layer}
    return sorted(set(MAPS.glob("*.svg")) - expected_maps)


def _read(path):
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None


def main(argv):
    if "--check" in argv:
        stale = check()
        if MANUAL in stale:
            try:
                manual_text(_read(MANUAL) or "")
            except MissingMarkers as error:
                print(error)
        for path in stale:
            print(f"stale: {path.relative_to(ROOT)}")
        return 1 if stale else 0
    try:
        write()
    except MissingMarkers as error:
        print(error)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
