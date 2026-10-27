"""Deterministic SVG pad maps: one per layer, labels over the lights."""

from xml.sax.saxutils import escape

from BleakLoop.core import engine, layout
from BleakLoop.core.leds import OFF, Blink

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
from .pads import DIMMED, blocks, labels
from .scenes import SCENES, Layer

MARGIN = 16
GRID_TOP = 40
GRID_WIDTH = 16 * STEP - GAP
GRID_HEIGHT = layout.ROWS * STEP - GAP
WIDTH = 2 * MARGIN + GRID_WIDTH
HEIGHT = GRID_TOP + GRID_HEIGHT + 56

BUBBLE = "#000000"
BUBBLE_OPACITY = "0.72"

RINGS = {Blink.TEMPO: "6 4", Blink.FAST: "2 3"}

TITLES = {
    Layer.SESSION: "Session Mode",
    Layer.SIDE: "Side columns",
    Layer.SESSION_SHIFT: "Session Mode with Shift held",
    Layer.SPLIT: "Session Mode, split view",
    Layer.MIXER: "Mixer Mode",
    Layer.FX: "FX Mode",
    Layer.MAPPED_FX: "FX Mode, Mapped FX",
    Layer.DEV: "Dev held",
    Layer.LINNSTRUMENT: "Linnstrument Mode controls page",
    Layer.LINNSTRUMENT_SHIFT: "Linnstrument Mode with Shift held",
    Layer.LINNSTRUMENT_SCENES: "Linnstrument Mode scene page",
    Layer.SEQUENCER: "Sequencer Mode",
    Layer.SEQUENCER_SETTINGS: "Sequencer Mode, settings",
    Layer.SEQUENCER_SHIFT: "Sequencer Mode with Shift held",
    Layer.SEQUENCER_DRUMS: "Sequencer Mode on a Drum Rack",
}

INSTRUMENT_COLUMNS = range(2, 17)


def map_svg(layer):
    frame = engine.render(*SCENES[layer])
    lines = _open(TITLES[layer])
    for key in sorted(frame):
        light = frame[key]
        x, y = _pad_xy(*key)
        if key[0] in DIMMED.get(layer, ()):
            lines.append(rect(x, y, PAD, PAD, SWATCHES[light.colour], opacity="0.18"))
            continue
        lines.append(rect(x, y, PAD, PAD, SWATCHES[light.colour]))
        if light.blink in RINGS:
            lines.append(_ring(x - 2, y - 2, PAD + 4, RINGS[light.blink]))
    for key, label in sorted(labels(layer).items()):
        x, y = _pad_xy(*key)
        lines += _bubble(x + PAD // 2, y + PAD // 2, label, 9, PAD - 4)
    for block in blocks(layer):
        lines += _block(block.name, block.columns, block.pads)
    lines += _instrument(frame)
    lines += _legend(GRID_TOP + GRID_HEIGHT + 20)
    return "\n".join(lines + ["</svg>"]) + "\n"


def _pad_xy(column, pad):
    return MARGIN + (column - 1) * STEP, GRID_TOP + (pad - 1) * STEP


def _open(title):
    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{HEIGHT}" '
        f'viewBox="0 0 {WIDTH} {HEIGHT}" font-family="Helvetica, Arial, sans-serif">',
        f"<title>{escape(title)}</title>",
        rect(0, 0, WIDTH, HEIGHT, BACKGROUND, radius=8),
    ]
    for column in range(1, 17):
        x, _ = _pad_xy(column, 1)
        lines.append(text(x + PAD // 2, GRID_TOP - 12, str(column), 11, MUTED))
    return lines


def _ring(x, y, size, dash):
    return (
        f'<rect x="{x}" y="{y}" width="{size}" height="{size}" rx="5" fill="none" '
        f'stroke="#ffffff" stroke-width="1.5" stroke-dasharray="{dash}"/>'
    )


def _bubble(cx, cy, label, size, width):
    # A dark pill behind the label keeps it readable on any light colour.
    height = size + 6
    return [
        f'<rect x="{cx - width // 2}" y="{cy - height // 2}" width="{width}" '
        f'height="{height}" rx="{height // 2}" fill="{BUBBLE}" '
        f'fill-opacity="{BUBBLE_OPACITY}"/>',
        text(cx, cy + size // 2 - 1, label, size, "#ffffff"),
    ]


def _block(label, columns, pads):
    # One outline around the region and one label in its centre.
    x, y = _pad_xy(columns[0], pads[0])
    width = len(columns) * STEP - GAP
    height = len(pads) * STEP - GAP
    return [
        f'<rect x="{x - 3}" y="{y - 3}" width="{width + 6}" height="{height + 6}" rx="6" '
        f'fill="none" stroke="{TEXT}" stroke-width="1" stroke-opacity="0.6"/>',
        *_bubble(x + width // 2, y + height // 2, label, 13, 8 * len(label) + 20),
    ]


def _instrument(frame):
    # Linnstrument Mode owns column 1 only; the rest of the surface is the player's instrument.
    if any(key[0] in INSTRUMENT_COLUMNS for key in frame):
        return []
    x, y = _pad_xy(INSTRUMENT_COLUMNS[0], 1)
    width = len(INSTRUMENT_COLUMNS) * STEP - GAP
    return [
        rect(x, y, width, GRID_HEIGHT, INSTRUMENT),
        text(x + width // 2, y + GRID_HEIGHT // 2 + 5, "Your instrument", 14, TEXT),
    ]


def _legend(y):
    x = MARGIN
    lines = []
    for blink, label in ((Blink.TEMPO, "Tempo blink"), (Blink.FAST, "Fast blink")):
        lines.append(rect(x, y, 16, 16, SWATCHES[OFF], radius=2))
        lines.append(_ring(x - 2, y - 2, 20, RINGS[blink]))
        lines.append(
            f'<text x="{x + 26}" y="{y + 12}" font-size="12" fill="{TEXT}">'
            f"{escape(label)}</text>"
        )
        x += 140
    return lines
