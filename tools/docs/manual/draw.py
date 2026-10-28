"""Deterministic SVG pad maps: one per layer, labels over the lights."""

from dataclasses import dataclass
from xml.sax.saxutils import escape

from BleakLoop.core import engine, layout
from BleakLoop.core.leds import OFF, Blink

from ..svg import (
    BACKGROUND,
    GAP,
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
    Layer.SESSION_SHIFT: "Session Mode with Shift held",
    Layer.SPLIT: "Session Mode, split view",
    Layer.SPLIT_SNAPSHOTS: "Session Mode, split view with the snapshots",
    Layer.MIXER: "Mixer Mode",
    Layer.MIXER_SPLIT: "Mixer Mode, split view",
    Layer.MIXER_SHIFT: "Mixer Mode with Shift held",
    Layer.FX: "FX Mode",
    Layer.FX_SHIFT: "FX Mode with Shift held",
    Layer.SEQUENCER: "Sequencer Mode",
    Layer.SEQUENCER_SETTINGS: "Sequencer Mode, settings",
    Layer.SEQUENCER_SHIFT: "Sequencer Mode with Shift held",
    Layer.SEQUENCER_DRUMS: "Sequencer Mode on a Drum Rack",
}

CAPTION = 20
CAPTION_MARGIN = 16  # extra side margin so a held panel's caption fits
LEGEND_STEP = 140

# Per held or toggled pad: the words, a background tint a shade off BACKGROUND, and the
# words' colour.
HOLDS = {
    "shift": ("SHIFT HELD", "#1b1d30", "#a3abff"),
    "device-clip": ("DEV HELD", "#281e14", "#ffb46b"),
    "view": ("VIEW TOGGLED", "#12252a", "#6fdde6"),
}


@dataclass(frozen=True)
class Panel:
    # A run of columns drawn side by side, each at its real column number.
    frame: dict
    columns: tuple
    labels: dict
    blocks: tuple
    caption: str | None
    dimmed: tuple
    held: str | None  # a HOLDS key: the pad held in this panel's frame


def panel(frame, columns, labels, blocks, caption=None, dimmed=(), held=None):
    return Panel(
        frame, tuple(columns), dict(labels), tuple(blocks), caption, tuple(dimmed), held
    )


def held_of(state):
    # The held or toggled pad a frame shows: Device/Clip's layer sits over Shift's.
    if state.device_clip:
        return "device-clip"
    if state.shift:
        return "shift"
    return "view" if state.seq_settings else None


def map_svg(layer):
    state, snapshot = SCENES[layer]
    frame = engine.render(state, snapshot)
    columns = range(1, 17)
    return figure(
        TITLES[layer],
        [
            panel(
                frame,
                columns,
                labels(layer),
                blocks(layer),
                dimmed=DIMMED.get(layer, ()),
                held=held_of(state),
            )
        ],
    )


def figure(title, panels):
    # Panels left to right, one STEP apart; the legend once, under them all. A single held
    # panel tints the whole figure and says so opposite the legend; several panels each tint
    # their own backdrop and say so in their caption.
    whole = panels[0].held if len(panels) == 1 else None
    captioned = [p for p in panels if p.caption or (p.held and not whole)]
    margin = MARGIN + (CAPTION_MARGIN if captioned else 0)
    top = GRID_TOP + (CAPTION if captioned else 0)
    width = 2 * margin + sum(len(p.columns) * STEP for p in panels) + (len(panels) - 1) * STEP
    width -= GAP
    legend_rows = 1 if MARGIN + 2 * LEGEND_STEP <= width else 2
    height = top + GRID_HEIGHT + 56 + (legend_rows - 1) * 24
    background = HOLDS[whole][1] if whole else BACKGROUND
    lines = _open(title, width, height, background)
    x = margin
    for p in panels:
        lines += _panel(p, x, top, tinted=not whole)
        x += (len(p.columns) + 1) * STEP
    legend_y = top + GRID_HEIGHT + 20
    lines += _legend(legend_y, legend_rows)
    if whole:
        words, _, colour = HOLDS[whole]
        lines.append(
            f'<text x="{width - MARGIN}" y="{legend_y + 12}" font-size="13" font-weight="bold" '
            f'fill="{colour}" text-anchor="end" letter-spacing="1">{escape(words)}</text>'
        )
    return "\n".join(lines + ["</svg>"]) + "\n"


def _panel(p, left, top, tinted):
    def xy(column, pad):
        return left + p.columns.index(column) * STEP, top + (pad - 1) * STEP

    lines = []
    width = len(p.columns) * STEP - GAP
    if p.held and tinted:
        words, tint, colour = HOLDS[p.held]
        lines.append(rect(left - 10, top - 50, width + 20, GRID_HEIGHT + 60, tint, radius=8))
        lines.append(text(left + width // 2, top - 32, p.caption or words, 12, colour))
    elif p.caption:
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
    return lines


def _open(title, width, height, background):
    return [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" font-family="Helvetica, Arial, sans-serif">',
        f"<title>{escape(title)}</title>",
        rect(0, 0, width, height, background, radius=8),
    ]


def _ring(x, y, size, dash):
    return (
        f'<rect x="{x}" y="{y}" width="{size}" height="{size}" rx="5" fill="none" '
        f'stroke="#ffffff" stroke-width="1.5" stroke-dasharray="{dash}"/>'
    )


def _bubble(cx, cy, label, size, width):
    # A dark pill behind the label keeps it readable on any light colour.
    if "\n" in label:
        return _stacked(cx, cy, label.split("\n"), size, width)
    height = size + 6
    return [
        f'<rect x="{cx - width // 2}" y="{cy - height // 2}" width="{width}" '
        f'height="{height}" rx="{height // 2}" fill="{BUBBLE}" '
        f'fill-opacity="{BUBBLE_OPACITY}"/>',
        text(cx, cy + size // 2 - 1, label, size, "#ffffff"),
    ]


def _stacked(cx, cy, lines, size, width):
    # A held pad's label, one word per line in a rounded box.
    step = size + 2
    height = len(lines) * step + 6
    top = cy - height // 2
    return [
        f'<rect x="{cx - width // 2}" y="{top}" width="{width}" height="{height}" rx="5" '
        f'fill="{BUBBLE}" fill-opacity="{BUBBLE_OPACITY}"/>',
        *(
            text(cx, top + 3 + size + i * step, line, size, "#ffffff")
            for i, line in enumerate(lines)
        ),
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
