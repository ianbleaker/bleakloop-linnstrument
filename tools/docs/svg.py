"""SVG palette and drawing primitives shared by every generated figure."""

from xml.sax.saxutils import escape

from BleakLoop.core.leds import (
    BLUE,
    CYAN,
    GREEN,
    LIME,
    MAGENTA,
    OFF,
    ORANGE,
    PINK,
    RED,
    WHITE,
    YELLOW,
)

PAD = 40
GAP = 6
STEP = PAD + GAP

BACKGROUND = "#141418"
TEXT = "#e8e8ec"
MUTED = "#9a9aa4"
INSTRUMENT = "#3a3a40"

SWATCHES = {
    RED: "#ff2a2a",
    YELLOW: "#ffe600",
    GREEN: "#22d43a",
    CYAN: "#19e0e6",
    BLUE: "#2a5bff",
    MAGENTA: "#e82ae8",
    WHITE: "#f2f2f2",
    ORANGE: "#ff8a1a",
    LIME: "#a6ff1a",
    PINK: "#ff7ab8",
    OFF: "#2a2a2e",
}


def rect(x, y, width, height, fill, radius=4, opacity=None):
    faded = f' fill-opacity="{opacity}"' if opacity else ""
    return (
        f'<rect x="{x}" y="{y}" width="{width}" height="{height}" rx="{radius}" '
        f'fill="{fill}"{faded}/>'
    )


def text(x, y, label, size, fill):
    return (
        f'<text x="{x}" y="{y}" font-size="{size}" fill="{fill}" '
        f'text-anchor="middle">{escape(label)}</text>'
    )
