"""The manual's pad labels: short labels for the pad map, grouped into items for the list."""

from dataclasses import dataclass, replace

from BleakLoop.core import buttons, layout

from . import positions
from .scenes import Layer


@dataclass(frozen=True)
class Item:
    # One or more pads that share a callout: Scenes 1-6, the tempo steps.
    name: str
    labels: dict  # (column, pad) -> label of at most 7 characters
    callout: str
    variant: bool = True  # on a Shift layer: listed under the normal list, with Shift held

    @property
    def keys(self):
        return sorted(self.labels)


@dataclass(frozen=True)
class Gesture:
    # A list-only line for a way of playing pads, not a pad: listed after the pads.
    name: str
    callout: str
    variant: bool = False
    keys = ()


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


SLOT_PADS = range(1, layout.WINDOW_SCENES + 1)
MUTE_PADS = range(layout.MUTE_ROW, layout.MUTE_ROW + 1)
SELECT_PADS = range(layout.SELECT_ROW, layout.SELECT_ROW + 1)
ALL_PADS = range(1, layout.ROWS + 1)
SCENE_PADS = range(1, layout.WINDOW_SCENES + 1)


def _ns(section):
    return getattr(layout, section.upper().replace("-", "_"))


def _one(name, section, button):
    # One pad: its label and the manual's text come from buttons.toml.
    key = getattr(_ns(section), button)
    function = _ns(section).at(key)[1]
    label = buttons.label(function, section)
    return Item(name, {key: label}, buttons.manual(function, section, label))


def _group(name, section, *functions):
    # A function's pads, or several functions' (Up/Down): each pad's label, the first's text.
    labels = {}
    for function in functions:
        pads = getattr(_ns(section), function)
        if isinstance(pads, dict):
            pairs = pads.items()
        elif pads and isinstance(pads[0], tuple):
            pairs = ((key, index + 1) for index, key in enumerate(pads))
        else:
            pairs = [(pads, None)]
        labels.update({key: buttons.label(function, section, value) for key, value in pairs})
    return Item(name, labels, buttons.manual(functions[0], section, None))


def _scenes(column, callout):
    labels = {(column, pad): f"Scene {pad}" for pad in SCENE_PADS}
    return Item("Scenes", labels, callout)


# A held pad's label names it and says so, one word per line.
def _shift_held(section):
    return Item("Shift", {getattr(_ns(section), "shift"): "SHIFT\nHELD"}, "Held.", variant=False)


def _global(section, record, capture, mode):
    # The Global column: Session Mode's, or a mode's own over it.
    return (
        _one("Play", section, "play_stop"),
        _one(*record),
        _one(*capture),
        _one("Metronome", section, "metronome"),
        _one("Fixed Length", section, "fixed_length"),
        _one("Undo", section, "undo"),
        _one(*mode),
        _one("Shift", section, "shift"),
    )


def _player_shift(section, normal):
    # Linnstrument and Sequencer Mode's Shift layer.
    return (
        _one("Stop track", section, "stop_track"),
        _one("Record", section, "record"),
        _one("Quantize", section, "quantize"),
        _one("Launch quantization", section, "launch_quantization"),
        _one("Redo", section, "redo"),
        _one("Scene page", section, "scene_page"),
        _shift_held(normal),
    )


def _navigation(section):
    return (
        _one("Copy", section, "copy"),
        _one("Delete", section, "delete"),
        _one("Session", section, "session"),
        _one("Mixer", section, "mixer"),
        _one("FX", section, "fx"),
        _one("Seq", section, "seq"),
        _one("Device/Clip", section, "device_clip"),
    )


def _navigation_shift(section):
    return (
        _group("Window directions", section, "window"),
        _group("Tempo", section, "tempo"),
        _one("Fader source", section, "fader_source"),
    )


# Columns 1, 15 and 16: the same in Session, Mixer and FX Mode.
_GLOBAL = _global(
    "global",
    ("Record", "global", "record"),
    ("Capture", "global", "capture"),
    ("Linnstrument Mode", "global", "linnstrument_mode"),
)

_GLOBAL_SHIFT = (
    _one("Stop all", "global-shift", "stop_all"),
    _one("Quantize", "global-shift", "quantize"),
    _one("Launch quantization", "global-shift", "launch_quantization"),
    _one("Redo", "global-shift", "redo"),
    _shift_held("global"),
)

_VIEW = (
    _scenes(layout.SCENE_COLUMN, "Launch a scene. Its FX snapshot, if it has one, lands as it starts."),
    _one("Unmute all", "view", "unmute_all"),
    _one("Stop", "view", "stop"),
)

_VIEW_SHIFT = (
    _scenes(layout.SCENE_COLUMN, "Launch with legato, leaving the FX snapshot alone."),
    _one("Unsolo all", "view-shift", "unsolo_all"),
    _one("Unarm all", "view-shift", "unarm_all"),
)

_NAVIGATION = _navigation("navigation")

_NAVIGATION_SHIFT = _navigation_shift("navigation-shift")

MUTE = Block(
    "Mute",
    layout.GRID_COLUMNS,
    MUTE_PADS,
    "Mute or unmute the track: pink while audible, orange while muted.",
)
SELECT = Block(
    "Select and arm",
    layout.GRID_COLUMNS,
    SELECT_PADS,
    "Select the track, arm it alone and give its first rack the blue hand.",
)
SOLO = Block(
    "Solo",
    layout.GRID_COLUMNS,
    MUTE_PADS,
    "Solo or unsolo the track, as Live's Exclusive Solo preference says: cyan, blue while "
    "soloed.",
)
ARM = Block(
    "Arm",
    layout.GRID_COLUMNS,
    SELECT_PADS,
    "Arm or disarm the track alone, keeping the selection.",
)

_SESSION = (
    Block(
        "Clip slots",
        layout.GRID_COLUMNS,
        SLOT_PADS,
        "Launch a clip. On an armed track, an empty slot records.",
    ),
    MUTE,
    SELECT,
)

# The split view: 8 tracks, then the faders.
SPLIT_TRACK_COLUMNS = range(layout.GRID_COLUMNS[0], layout.GRID_COLUMNS[0] + layout.SPLIT_TRACKS)

_SPLIT = (
    *(replace(block, columns=SPLIT_TRACK_COLUMNS) for block in _SESSION),
    Block(
        "Faders",
        layout.SPLIT_FADER_COLUMNS,
        ALL_PADS,
        "One fader per row, as in FX Mode, from the source Shift + FX picks. Its third "
        "choice shows the snapshots instead.",
    ),
)

_SESSION_SHIFT = (
    Block("Clip slots: legato", layout.GRID_COLUMNS, SLOT_PADS, "Launch with legato."),
    SOLO,
    ARM,
)

_MIXER = (
    Block(
        "Faders",
        layout.GRID_COLUMNS,
        SLOT_PADS,
        "One volume fader per track.",
    ),
    MUTE,
    SELECT,
)

# Not drawn: the Shift notes of the split view's list.
_SPLIT_SHIFT = tuple(replace(block, columns=SPLIT_TRACK_COLUMNS) for block in _SESSION_SHIFT)

# The faders are dark under Shift.
_MIXER_SHIFT = (SOLO, ARM)

_FX = (
    Block(
        "Faders",
        layout.FX_FADER_COLUMNS,
        ALL_PADS,
        "One fader per row: touch or slide along a row to set the selected device's macro "
        "or parameter.",
    ),
    Block(
        "Snapshots",
        range(layout.FX.slots[0][0], layout.FX.slots[-1][0] + 1),
        ALL_PADS,
        f"Sixteen snapshots of every rack's macros: slots {positions.runs('fx.slots')}. "
        "Press an empty slot to store, a stored one to recall. Shift + an empty slot stores "
        "the selected rack alone, in pink.",
    ),
    _group("Scene snapshots", "fx", "scene_slots"),
    _group("Bars", "fx", "bars"),
)

# The split views' snapshot panel: FX Mode's columns 11-14, column 10 dark.
_SNAPSHOT_PANEL = _FX[1:]

_SPLIT_SNAPSHOTS = (
    *_SPLIT[:-1],
    *_SNAPSHOT_PANEL,
)

_MIXER_SPLIT = (
    replace(_MIXER[0], name="Volume faders", columns=SPLIT_TRACK_COLUMNS),
    *(replace(block, columns=SPLIT_TRACK_COLUMNS) for block in _MIXER[1:]),
    replace(_SPLIT[-1], name="Panel"),
)

# Not drawn: the Shift notes of Mixer's split view's list.
_MIXER_SPLIT_SHIFT = tuple(replace(block, columns=SPLIT_TRACK_COLUMNS) for block in _MIXER_SHIFT)

_DEVICE_CLIP = (
    _group("Tracks", "device-clip", "tracks"),
    _group("Devices", "device-clip", "devices"),
    Item(
        "Device/Clip",
        {layout.NAVIGATION.device_clip: "DEV\nHELD"},
        "Hold it for this layer. A tap, pressing nothing else, flips Live between Device and "
        "Clip view instead.",
        variant=False,
    ),
)

_LINNSTRUMENT = _global(
    "linnstrument",
    ("Record Clip", "linnstrument", "record_clip"),
    ("Capture MIDI", "linnstrument", "capture_midi"),
    ("Back", "linnstrument", "back"),
)

_LINNSTRUMENT_SHIFT = _player_shift("linnstrument-shift", "linnstrument")

_LINNSTRUMENT_SCENES = (
    _scenes(layout.GLOBAL_COLUMN, "Launch a scene and its FX snapshot, and go back to the controls."),
    _one("Back", "linnstrument-scenes", "back"),
)

# Sequencer Mode: the Global column as in Linnstrument Mode, and its own columns 15 and 16.
_SEQUENCER_GLOBAL = _global(
    "sequencer-global",
    ("Record Clip", "sequencer-global", "record_clip"),
    ("Capture MIDI", "sequencer-global", "capture_midi"),
    ("Linnstrument Mode", "sequencer-global", "linnstrument_mode"),
)

_SEQUENCER_NAV = _navigation("sequencer-nav")
SEQ_COPY, SEQ_DELETE = _SEQUENCER_NAV[:2]

_SEQUENCER_GLOBAL_SHIFT = _player_shift("sequencer-global-shift", "sequencer-global")

_SEQUENCER_NAV_SHIFT = _navigation_shift("sequencer-nav-shift")

# Steps and column 15, the same in both views.
_SEQUENCER_GRID = (
    Block(
        "Steps",
        layout.SEQ_STEP_COLUMNS,
        ALL_PADS,
        "64 steps, top row first. Tap to add or remove the selected note. Hold a step and "
        "press a later one for one long note, or slide along the row to change its "
        "velocity.",
    ),
    _one("Double", "sequencer-grid", "double"),
    _one("Halve", "sequencer-grid", "halve"),
    _one("Follow", "sequencer-grid", "follow"),
    _group("Up/Down", "sequencer-grid", "up", "down"),
    _one("View", "sequencer-grid", "view"),
)

_SEQUENCER = (
    *_SEQUENCER_GRID,
    Block(
        "Notes",
        layout.SEQ_NOTE_COLUMNS,
        ALL_PADS,
        "Choose the note the steps write: press a pad to select its note and hear it on the "
        "armed track. Hold steps and press a pad to add or remove that note on them.",
    ),
)

_SEQUENCER_SETTINGS = (
    _group("Rates", "sequencer-settings", "rates"),
    _one("Triplet", "sequencer-settings", "triplet"),
    Block(
        "Pages",
        range(layout.SEQUENCER_SETTINGS.pages[0][0], layout.SEQUENCER_SETTINGS.pages[-1][0] + 1),
        ALL_PADS,
        f"Pages 1–16 of 64 steps: {positions.runs('sequencer_settings.pages')}. Press one to "
        "show it, or hold one and press another to loop both.",
    ),
)

# The manual's sections, by marker slug.
SECTIONS = {
    "global": _GLOBAL,
    "global-shift": _GLOBAL_SHIFT,
    "view": _VIEW,
    "view-shift": _VIEW_SHIFT,
    "navigation": _NAVIGATION,
    "navigation-shift": _NAVIGATION_SHIFT,
    "session": _SESSION,
    "session-shift": _SESSION_SHIFT,
    "split": _SPLIT,
    "split-shift": _SPLIT_SHIFT,
    "split-snapshots": _SPLIT_SNAPSHOTS,
    "mixer": _MIXER,
    "mixer-shift": _MIXER_SHIFT,
    "mixer-split": _MIXER_SPLIT,
    "mixer-split-shift": _MIXER_SPLIT_SHIFT,
    "fx": _FX,
    "fx-shift": _FX,  # the grid works as without Shift
    "device-clip": _DEVICE_CLIP,
    "linnstrument": _LINNSTRUMENT,
    "linnstrument-shift": _LINNSTRUMENT_SHIFT,
    "linnstrument-scenes": _LINNSTRUMENT_SCENES,
    "sequencer-global": _SEQUENCER_GLOBAL,
    "sequencer-nav": _SEQUENCER_NAV,
    "sequencer-global-shift": _SEQUENCER_GLOBAL_SHIFT,
    "sequencer-nav-shift": _SEQUENCER_NAV_SHIFT,
    "sequencer-grid": _SEQUENCER_GRID,
    "sequencer": _SEQUENCER,
    "sequencer-settings": _SEQUENCER_SETTINGS,
    # Listed, not drawn: Sequencer Mode's own pads, after its first map. Column 16's mode
    # pads are in the Navigation column's list.
    "sequencer-functions": (
        *_SEQUENCER,
        SEQ_COPY,
        SEQ_DELETE,
        Gesture(
            "Press and hold a step",
            "Change the velocity by sliding left (lower) or right (higher).",
        ),
        Gesture(
            "Shift + press and hold a step",
            "Nudge the note forward or backward by sliding left and right.",
        ),
    ),
}

# When each of controls.SCENE_LIGHTS shows, for the manual's Reading the lights.
SCENE_LIGHTS = {
    "waiting": "while a held Bars pad holds their launch back to its bar line",
    "launching": "once launched, until they start at the next quantization boundary",
    "full": "while all their clips play",
    "playing": "while some of their clips play",
    "clips": "if they hold clips",
}

# The sections the manual lists, each with the section holding its Shift layer.
LISTS = {
    "global": "global-shift",
    "view": "view-shift",
    "navigation": "navigation-shift",
    "session": "session-shift",
    "split": "split-shift",
    "split-snapshots": "split-shift",
    "mixer": "mixer-shift",
    "mixer-split": "mixer-split-shift",
    "fx": None,
    "device-clip": None,
    "linnstrument": "linnstrument-shift",
    "linnstrument-scenes": None,
    "sequencer-functions": None,
    "sequencer-settings": None,
}

# The sections each map is drawn from.
LAYERS = {
    Layer.SESSION: ("global", "view", "navigation", "session"),
    Layer.SESSION_SHIFT: ("global-shift", "view-shift", "navigation-shift", "session-shift"),
    Layer.SPLIT: ("global", "view", "navigation", "split"),
    Layer.SPLIT_SNAPSHOTS: ("global", "view", "navigation", "split-snapshots"),
    Layer.MIXER: ("global", "view", "navigation", "mixer"),
    Layer.MIXER_SPLIT: ("global", "view", "navigation", "mixer-split"),
    Layer.MIXER_SHIFT: ("global-shift", "view-shift", "navigation-shift", "mixer-shift"),
    Layer.FX: ("global", "view", "navigation", "fx"),
    Layer.FX_SHIFT: ("global-shift", "view-shift", "navigation-shift", "fx-shift"),
    Layer.SEQUENCER: ("sequencer-global", "sequencer-nav", "sequencer"),
    Layer.SEQUENCER_SETTINGS: (
        "sequencer-global",
        "sequencer-nav",
        "sequencer-grid",
        "sequencer-settings",
    ),
    Layer.SEQUENCER_SHIFT: ("sequencer-global-shift", "sequencer-nav-shift", "sequencer"),
    Layer.SEQUENCER_DRUMS: ("sequencer-global", "sequencer-nav", "sequencer"),
}

# Columns a map shows dimmed and unlabelled, per layer: none at present.
DIMMED = {}


def items(layer):
    return [item for section in LAYERS[layer] for item in SECTIONS[section]]


def ordered(section):
    # Left to right, then far to near, by each item's first pad; gestures last, as written.
    pads = [item for item in SECTIONS[section] if item.keys]
    gestures = [item for item in SECTIONS[section] if not item.keys]
    return sorted(pads, key=lambda item: item.keys[0]) + gestures


def labels(layer):
    return {key: label for section in LAYERS[layer] for key, label in section_labels(section).items()}


def section_labels(section):
    return {
        key: label
        for item in SECTIONS[section]
        if isinstance(item, Item)
        for key, label in item.labels.items()
    }


def blocks(layer):
    return [item for item in items(layer) if isinstance(item, Block)]

