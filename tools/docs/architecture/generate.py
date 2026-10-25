"""The architecture doc's import graph and figures."""

from pathlib import Path

from ..markers import read, replace_between
from . import figures, imports

ROOT = Path(__file__).resolve().parents[3]
ARCHITECTURE = ROOT / "docs" / "architecture.md"
FIGURES = ROOT / "docs" / "architecture"
FIGURE_FILES = {
    "orientation.svg": figures.orientation_svg,
    "colours.svg": figures.colours_svg,
}


def architecture_text(text):
    start = "<!-- generated:imports -->"
    end = "<!-- /generated:imports -->"
    return replace_between(text, start, end, imports.mermaid(), ARCHITECTURE)


def expected():
    return {
        **{FIGURES / name: draw() for name, draw in FIGURE_FILES.items()},
        ARCHITECTURE: architecture_text(read(ARCHITECTURE) or ""),
    }


def strays():
    # Figures left over from a renamed or removed one.
    return sorted(
        set(FIGURES.glob("*.svg")) - {FIGURES / name for name in FIGURE_FILES}
    )
