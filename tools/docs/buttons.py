"""docs/buttons.md: every button's pad, label and function, and what each function says.

Generated from src/BleakLoop/buttons.toml by PYTHONPATH=src python3 -m tools.docs.
"""

from pathlib import Path

from BleakLoop.core import buttons, catalogue, layout

from .manual import positions

ROOT = Path(__file__).resolve().parents[2]
PATH = ROOT / "docs" / "buttons.md"

# (section, heading), in the order a player meets them. {column} is the column all the section's
# buttons are in.
SECTIONS = (
    ("global", "Global column: Session, Mixer and FX Mode"),
    ("global-shift", "Global column with Shift: Session, Mixer and FX Mode"),
    ("view", "{column}: Session, Mixer and FX Mode"),
    ("view-shift", "{column} with Shift"),
    ("navigation", "Navigation column: Session, Mixer and FX Mode"),
    ("navigation-shift", "Navigation column with Shift"),
    ("device-clip", "Device/Clip held"),
    ("fx", "FX Mode and the split views' snapshot panel"),
    ("linnstrument", "Global column: Linnstrument Mode"),
    ("linnstrument-shift", "Global column with Shift: Linnstrument Mode"),
    ("linnstrument-scenes", "Scene page: Linnstrument and Sequencer Mode"),
    ("sequencer-global", "Global column: Sequencer Mode"),
    ("sequencer-global-shift", "Global column with Shift: Sequencer Mode"),
    ("sequencer-nav", "Navigation column: Sequencer Mode"),
    ("sequencer-nav-shift", "Navigation column with Shift: Sequencer Mode"),
    ("sequencer-grid", "{column}: Sequencer Mode"),
    ("sequencer-settings", "Settings view: Sequencer Mode"),
)

HEADER = """# Buttons

<!-- Generated from src/BleakLoop/buttons.toml by PYTHONPATH=src python3 -m tools.docs. Edit that file, not this one. -->

Where every button is, and what it says in Live's status bar. Pads are column/pad: column 1 is
the Global column, pad 1 the far row. Refusals always show; a function with
`show = false` keeps its other messages quiet.
"""


def expected():
    return {PATH: text()}


def strays():
    return []


def text():
    parts = [HEADER]
    for section, heading in SECTIONS:
        parts.append(_section(section, heading))
    parts.append(_message_only())
    parts.append(_system())
    return "\n".join(parts)


def _cell(value):
    return value.replace("|", "\\|").replace("\n", " ")


def _messages(table):
    return "<br>".join(f"{key}: {_cell(text)}" for key, text in table.items())


def _section(section, heading):
    namespace = getattr(layout, section.upper().replace("-", "_"))
    rows = [
        "| Pad | Label | Function | Message | Outcomes | Refusals | Shown |",
        "|---|---|---|---|---|---|---|",
    ]
    for name, function, key, value in sorted(namespace.buttons(), key=lambda button: button.key):
        entry = buttons.function(function)
        pad = f"{key[0]}/{key[1]}"
        rows.append(
            "| "
            + " | ".join(
                (
                    pad,
                    _cell(buttons.label(function, section, value)),
                    f"`{function}`" + ("" if value is None else f" {value}"),
                    _cell(entry.get("message", "")),
                    _messages(entry.get("outcomes", {})),
                    _messages(entry.get("refusals", {})),
                    "yes" if entry.get("show", True) else "no",
                )
            )
            + " |"
        )
    if "{column}" in heading:
        heading = heading.format(column=positions.section_column(namespace))
    return f"## {heading}\n\n`{section}`\n\n" + "\n".join(rows) + "\n"


def _message_only():
    rows = ["| Function | Outcomes | Refusals | Shown |", "|---|---|---|---|"]
    for name in sorted(catalogue.MESSAGE_ONLY):
        entry = buttons.function(name)
        rows.append(
            f"| `{name}` | {_messages(entry.get('outcomes', {}))} | "
            f"{_messages(entry.get('refusals', {}))} | {'yes' if entry.get('show', True) else 'no'} |"
        )
    return "## Messages without a button\n\nThe faders' and timed scene launches' wording.\n\n" + "\n".join(rows) + "\n"


def _system():
    rows = ["| Key | Message |", "|---|---|"]
    for key, message in buttons.systems().items():
        rows.append(f"| `{key}` | {_cell(message)} |")
    return (
        "## System messages\n\nThe device setup, Device/Clip's track and device names, and why the button editor shows a function dark. These "
        "always show.\n\n" + "\n".join(rows) + "\n"
    )
