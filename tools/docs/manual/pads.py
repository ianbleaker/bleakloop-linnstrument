"""The manual's pad labels: short labels for the pad map, grouped into items for the list."""

from dataclasses import dataclass

from BleakLoop.core import layout

from .scenes import Layer


@dataclass(frozen=True)
class Item:
    # One or more pads that share a callout: Scenes 1-7, the track switch modes.
    name: str
    labels: dict  # (column, pad) -> label of at most 7 characters
    callout: str
    variant: bool = True  # on a Shift layer: noted on the normal layer's item

    @property
    def keys(self):
        return sorted(self.labels)


@dataclass(frozen=True)
class Block:
    # A repeating region drawn with one label, such as the clip slots.
    name: str
    columns: range
    pads: range
    callout: str
    variant: bool = True

    @property
    def keys(self):
        return [(column, pad) for column in self.columns for pad in self.pads]


SLOT_PADS = range(1, layout.ROWS)
SWITCH_PADS = range(layout.ROWS, layout.ROWS + 1)
ALL_PADS = range(1, layout.ROWS + 1)
SCENE_PADS = range(1, layout.WINDOW_SCENES + 1)


def _one(name, key, callout, label=None):
    return Item(name, {key: label or name}, callout)


def _scenes(column, callout):
    labels = {(column, pad): f"Scene {pad}" for pad in SCENE_PADS}
    return Item("Scenes", labels, callout)


# Column 1: the same pads in every mode.
PLAY = _one("Play", layout.PLAY_STOP, "Start/stop. Blinks on the beat while playing.")
METRONOME = _one(
    "Metronome", layout.METRONOME, "Metronome on/off. Blinks while on.", label="Metro"
)
FIXED_LENGTH = _one(
    "Fixed Length",
    layout.FIXED_LENGTH,
    "Record new clips at exactly 1, 2, 4 or 8 bars. Each press steps to the next length, "
    "then off.",
    label="Length",
)
UNDO = _one("Undo", layout.UNDO, "Undo.")
SHIFT = _one("Shift", layout.SHIFT, "Hold for the Shift layer.")
QUANTIZE = _one(
    "Quantize",
    layout.QUANTIZE,
    "Quantize the current MIDI clip to 1/16 notes.",
    label="Quant",
)
LAUNCH_QUANTIZATION = _one(
    "Launch quantization",
    layout.LAUNCH_QUANTIZATION,
    "Launch quantization on/off; red while off.",
    label="LaunchQ",
)
REDO = _one("Redo", layout.UNDO, "Redo.")
SHIFT_HELD = Item("Shift", {layout.SHIFT: "Shift"}, "Held.", variant=False)

# Columns 1, 15 and 16: the same in Session and Mixer Mode.
_SIDE = (
    PLAY,
    _one(
        "Record",
        layout.RECORD,
        "Session Record on/off (Arrangement Record in Arrangement View). Blinks while "
        "recording. In Linnstrument Mode, records a new clip on the selected track.",
    ),
    _one(
        "Capture",
        layout.CAPTURE,
        "Capture and Insert Scene. In Linnstrument Mode, captures MIDI.",
    ),
    METRONOME,
    FIXED_LENGTH,
    UNDO,
    _one("Linnstrument Mode", layout.MODE_PAD, "Switch to Linnstrument Mode.", label="Linn"),
    SHIFT,
    _one(
        "Copy",
        layout.COPY,
        "Hold, press a clip, then an empty slot.",
    ),
    _one("Delete", layout.DELETE, "Hold, then press a clip or scene to delete it."),
    _one("Mixer", layout.MIXER, "Mixer Mode on/off. Blinks while on."),
    Item(
        "Track switch mode",
        {key: name.title() for key, name in layout.TRACK_CONTROL_PADS.items()},
        "What the track switches do: Mute, Solo or Arm. The chosen one blinks.",
    ),
    _scenes(layout.SCENE_COLUMN, "Launch a scene."),
)

_SIDE_SHIFT = (
    _one(
        "Stop all",
        layout.PLAY_STOP,
        "Stop all clips. In Linnstrument Mode, stops the selected track's clips.",
        label="StopAll",
    ),
    QUANTIZE,
    LAUNCH_QUANTIZATION,
    REDO,
    *(
        _one(f"Window {name.lower()}", key, f"Move the window {name.lower()}.", label=name)
        for key, name in {(15, 1): "Up", (15, 2): "Down", (15, 3): "Left", (15, 4): "Right"}.items()
    ),
    Item(
        "Tempo",
        {(15, 7): "Tempo+", (15, 8): "Tempo-"},
        "Tempo +1 BPM on Solo, -1 BPM on Arm.",
    ),
    _scenes(layout.SCENE_COLUMN, "Launch with legato."),
    SHIFT_HELD,
)

_SESSION = (
    Block(
        "Clip slots",
        layout.GRID_COLUMNS,
        SLOT_PADS,
        "Launch a clip. On an armed track, an empty slot records.",
    ),
    Block(
        "Track switches",
        layout.GRID_COLUMNS,
        SWITCH_PADS,
        "Mute, solo or arm the track, as set by the track switch mode.",
    ),
)

_SESSION_SHIFT = (
    Block("Clip slots: legato", layout.GRID_COLUMNS, SLOT_PADS, "Launch with legato."),
    Block(
        "Track switches: stop",
        layout.GRID_COLUMNS,
        SWITCH_PADS,
        "Stop the track's clips, in Mute mode.",
    ),
)

_MIXER = (
    Block(
        "Faders",
        layout.GRID_COLUMNS,
        ALL_PADS,
        "One volume fader per track.",
    ),
)

_LINNSTRUMENT = (
    PLAY,
    _one(
        "Record Clip",
        layout.RECORD,
        "Record a new clip on the selected track.",
        label="RecClip",
    ),
    _one("Capture MIDI", layout.CAPTURE, "Capture MIDI.", label="CapMIDI"),
    METRONOME,
    FIXED_LENGTH,
    UNDO,
    _one("Session Mode", layout.MODE_PAD, "Back to Session Mode.", label="Session"),
    SHIFT,
)

_LINNSTRUMENT_SHIFT = (
    _one(
        "Stop track", layout.PLAY_STOP, "Stop the selected track's clips.", label="StopTrk"
    ),
    _one(
        "Record",
        layout.RECORD,
        "Session Record on/off (Arrangement Record in Arrangement View). Blinks while "
        "recording.",
    ),
    QUANTIZE,
    LAUNCH_QUANTIZATION,
    REDO,
    _one("Scene page", layout.SCENE_PAGE, "Show the scene page.", label="Scenes"),
    SHIFT_HELD,
)

_LINNSTRUMENT_SCENES = (
    _scenes(1, "Launch a scene and go back to the controls."),
    _one("Back", layout.SHIFT, "Back to the controls without launching."),
)

# The manual's sections, by marker slug.
SECTIONS = {
    "side": _SIDE,
    "side-shift": _SIDE_SHIFT,
    "session": _SESSION,
    "session-shift": _SESSION_SHIFT,
    "mixer": _MIXER,
    "linnstrument": _LINNSTRUMENT,
    "linnstrument-shift": _LINNSTRUMENT_SHIFT,
    "linnstrument-scenes": _LINNSTRUMENT_SCENES,
}

# The sections the manual lists, each with the section holding its Shift layer.
LISTS = {
    "side": "side-shift",
    "session": "session-shift",
    "mixer": None,
    "linnstrument": "linnstrument-shift",
    "linnstrument-scenes": None,
}

# The sections each map is drawn from.
LAYERS = {
    Layer.SESSION: ("side", "session"),
    Layer.SIDE: ("side",),
    Layer.SESSION_SHIFT: ("side-shift", "session-shift"),
    Layer.MIXER: ("side", "mixer"),
    Layer.LINNSTRUMENT: ("linnstrument",),
    Layer.LINNSTRUMENT_SHIFT: ("linnstrument-shift",),
    Layer.LINNSTRUMENT_SCENES: ("linnstrument-scenes",),
}

# Columns a map shows dimmed and unlabelled: the side columns map dims the grid.
DIMMED = {Layer.SIDE: layout.GRID_COLUMNS}


def items(layer):
    return [item for section in LAYERS[layer] for item in SECTIONS[section]]


def ordered(section):
    # Left to right, then far to near, by each item's first pad.
    return sorted(SECTIONS[section], key=lambda item: item.keys[0])


def labels(layer):
    return {
        key: label
        for item in items(layer)
        if isinstance(item, Item)
        for key, label in item.labels.items()
    }


def blocks(layer):
    return [item for item in items(layer) if isinstance(item, Block)]


def shift_note(section, item):
    # What the item's pads do under Shift, from the Shift layer's items.
    shifted = LISTS[section]
    if shifted is None:
        return None
    notes = [
        other.callout.rstrip(".")
        for other in ordered(shifted)
        if other.variant and set(other.keys) & set(item.keys)
    ]
    return "; ".join(notes) or None
