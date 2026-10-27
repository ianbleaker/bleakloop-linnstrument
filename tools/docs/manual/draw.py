"""Deterministic SVG pad maps: one per layer, labels over the lights."""

from dataclasses import dataclass
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
GRID_HEIGHT = layout.ROWS * STEP - GAP

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
CAPTION = 20
LEGEND_STEP = 140


@dataclass(frozen=True)
class Panel:
    # A run of columns drawn side by side, each at its real column number.
    frame: dict
    columns: tuple
    labels: dict
    blocks: tuple
    caption: str | None
    dimmed: tuple


def panel(frame, columns, labels, blocks, caption=None, dimmed=()):
    return Panel(frame, tuple(columns), dict(labels), tuple(blocks), caption, tuple(dimmed))


def map_svg(layer):
    frame = engine.render(*SCENES[layer])
    columns = range(1, 17)
    return figure(
        TITLES[layer],
        [panel(frame, columns, labels(layer), blocks(layer), dimmed=DIMMED.get(layer, ()))],
    )


def figure(title, panels):
    # Panels left to right, one STEP apart; the legend once, under them all.
    top = GRID_TOP + (CAPTION if any(p.caption for p in panels) else 0)
    width = 2 * MARGIN + sum(len(p.columns) * STEP for p in panels) + (len(panels) - 1) * STEP
    width -= GAP
    legend_rows = 1 if MARGIN + 2 * LEGEND_STEP <= width else 2
    height = top + GRID_HEIGHT + 56 + (legend_rows - 1) * 24
    lines = _open(title, width, height)
    x = MARGIN
    for p in panels:
        lines += _panel(p, x, top)
        x += (len(p.columns) + 1) * STEP
    lines += _legend(top + GRID_HEIGHT + 20, legend_rows)
    return "\n".join(lines + ["</svg>"]) + "\n"


def _panel(p, left, top):
    def xy(column, pad):
        return left + p.columns.index(column) * STEP, top + (pad - 1) * STEP

    lines = []
    if p.caption:
        width = len(p.columns) * STEP - GAP
        lines.append(text(left + width // 2, top - 32, p.caption, 12, MUTED))
    for column in p.columns:
        x, _ = xy(column, 1)
        lines.append(text(x + PAD // 2, top - 12, str(column), 11, MUTED))
    for key in sorted(k for k in p.frame if k[0] in p.columns):
        light = p.frame[key]
        x, y = xy(*key)
        if key[0] in p.dimmed:
            lines.append(rect(x, y, PAD, PAD, SWATCHES[light.colour], opacity="0.18"))
            continue
        lines.append(rect(x, y, PAD, PAD, SWATCHES[light.colour]))
        if light.blink in RINGS:
            lines.append(_ring(x - 2, y - 2, PAD + 4, RINGS[light.blink]))
    for key, label in sorted(p.labels.items()):
        if key[0] in p.columns:
            x, y = xy(*key)
            lines += _bubble(x + PAD // 2, y + PAD // 2, label, 9, PAD - 4)
    for block in p.blocks:
        columns = [column for column in block.columns if column in p.columns]
        if columns:
            lines += _block(block.name, xy(columns[0], block.pads[0]), len(columns), block.pads)
    lines += _instrument(p, xy)
    return lines


def _open(title, width, height):
    return [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" font-family="Helvetica, Arial, sans-serif">',
        f"<title>{escape(title)}</title>",
        rect(0, 0, width, height, BACKGROUND, radius=8),
    ]


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


def _block(label, origin, column_count, pads):
    # One outline around the region and one label in its centre.
    x, y = origin
    width = column_count * STEP - GAP
    height = len(pads) * STEP - GAP
    return [
        f'<rect x="{x - 3}" y="{y - 3}" width="{width + 6}" height="{height + 6}" rx="6" '
        f'fill="none" stroke="{TEXT}" stroke-width="1" stroke-opacity="0.6"/>',
        *_bubble(x + width // 2, y + height // 2, label, 13, 8 * len(label) + 20),
    ]


def _instrument(p, xy):
    # Linnstrument Mode owns column 1 only; the rest of the surface is the player's instrument.
    columns = [column for column in p.columns if column in INSTRUMENT_COLUMNS]
    if not columns or any(key[0] in INSTRUMENT_COLUMNS for key in p.frame):
        return []
    x, y = xy(columns[0], 1)
    width = len(columns) * STEP - GAP
    return [
        rect(x, y, width, GRID_HEIGHT, INSTRUMENT),
        text(x + width // 2, y + GRID_HEIGHT // 2 + 5, "Your instrument", 14, TEXT),
    ]


def _legend(y, rows):
    # On one row, or one item per row when the figure is too narrow.
    x = MARGIN
    lines = []
    for blink, label in ((Blink.TEMPO, "Tempo blink"), (Blink.FAST, "Fast blink")):
        lines.append(rect(x, y, 16, 16, SWATCHES[OFF], radius=2))
        lines.append(_ring(x - 2, y - 2, 20, RINGS[blink]))
        lines.append(
            f'<text x="{x + 26}" y="{y + 12}" font-size="12" fill="{TEXT}">'
            f"{escape(label)}</text>"
        )
        if rows == 1:
            x += LEGEND_STEP
        else:
            y += 24
    return lines
