"""Deterministic SVG figures for section 5: orientation and colour values."""

from xml.sax.saxutils import escape

from BleakLoop.core import layout
from BleakLoop.core.leds import (
    BLUE,
    CYAN,
    DEVICE_DEFAULT,
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

from ..svg import (
    BACKGROUND,
    GAP,
    INSTRUMENT,
    MUTED,
    PAD,
    STEP,
    SWATCHES,
    TEXT,
    rect,
    text,
)

NAMES = {
    RED: "red",
    YELLOW: "yellow",
    GREEN: "green",
    CYAN: "cyan",
    BLUE: "blue",
    MAGENTA: "magenta",
    OFF: "off",
    WHITE: "white",
    ORANGE: "orange",
    LIME: "lime",
    PINK: "pink",
}

AXIS = 56
GRID_TOP = 40
SPLIT = 10  # extra space between the control switches and the playing surface
SWATCH_STEP = 72


def orientation_svg():
    grid_width = 17 * STEP - GAP + SPLIT
    grid_height = layout.ROWS * STEP - GAP
    width = 2 * AXIS + grid_width
    height = GRID_TOP + grid_height + 56
    lines = _open("Orientation", width, height)
    for column in range(17):
        x = _column_x(column)
        lines.append(text(x + PAD // 2, GRID_TOP - 12, str(column), 11, MUTED))
        for pad in range(1, layout.ROWS + 1):
            y = GRID_TOP + (pad - 1) * STEP
            lines.append(
                rect(x, y, PAD, PAD, INSTRUMENT if column == 0 else SWATCHES[OFF])
            )
    for pad in range(1, layout.ROWS + 1):
        y = GRID_TOP + (pad - 1) * STEP + PAD // 2 + 4
        lines.append(text(AXIS // 2, y, f"pad {pad}", 11, TEXT))
        lines.append(text(width - AXIS // 2, y, f"row {layout.ROWS - pad}", 11, MUTED))
    label_y = GRID_TOP + grid_height + 22
    lines.append(text(_column_x(0) + PAD // 2, label_y, "control", 10, TEXT))
    lines.append(text(_column_x(0) + PAD // 2, label_y + 13, "switches", 10, TEXT))
    surface_x = _column_x(1)
    surface_width = _column_x(16) + PAD - surface_x
    lines.append(
        f'<line x1="{surface_x}" y1="{label_y - 12}" x2="{surface_x + surface_width}" '
        f'y2="{label_y - 12}" stroke="{MUTED}" stroke-width="1"/>'
    )
    lines.append(
        text(surface_x + surface_width // 2, label_y + 6, "playing surface", 12, TEXT)
    )
    return "\n".join(lines + ["</svg>"]) + "\n"


def colours_svg():
    swatches = [(value, f"{value} {name}") for value, name in sorted(NAMES.items())]
    swatches.append((DEVICE_DEFAULT, f"{DEVICE_DEFAULT} default"))
    width = AXIS + len(swatches) * SWATCH_STEP
    height = 104
    lines = _open("Colour values", width, height)
    for index, (value, label) in enumerate(swatches):
        cx = AXIS // 2 + index * SWATCH_STEP + SWATCH_STEP // 2
        fill = SWATCHES[OFF] if value == DEVICE_DEFAULT else SWATCHES[value]
        lines.append(rect(cx - PAD // 2, 20, PAD, PAD, fill))
        lines.append(text(cx, 20 + PAD + 22, label, 11, TEXT))
    return "\n".join(lines + ["</svg>"]) + "\n"


def _column_x(column):
    return AXIS + column * STEP + (SPLIT if column else 0)


def _open(title, width, height):
    return [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" font-family="Helvetica, Arial, sans-serif">',
        f"<title>{escape(title)}</title>",
        rect(0, 0, width, height, BACKGROUND, radius=8),
    ]
