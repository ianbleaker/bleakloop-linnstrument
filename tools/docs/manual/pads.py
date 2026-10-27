"""The manual's pad labels: short labels for the pad map, grouped into items for the list."""

from dataclasses import dataclass, replace

from BleakLoop.core import layout

from .scenes import Layer


@dataclass(frozen=True)
class Item:
    # One or more pads that share a callout: Scenes 1-6, the tempo steps.
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


SLOT_PADS = range(1, layout.WINDOW_SCENES + 1)
MUTE_PADS = range(layout.MUTE_ROW, layout.MUTE_ROW + 1)
SELECT_PADS = range(layout.SELECT_ROW, layout.SELECT_ROW + 1)
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
DEVICE_CLIP = _one(
    "Device/Clip",
    layout.DEVICE_CLIP,
    "Tap to flip Live between Device and Clip view. Hold for the Device/Clip layer: tracks, "
    "devices and the fader source.",
    label="DevClip",
)
TEMPO = Item(
    "Tempo",
    {key: "Tempo+" if step > 0 else "Tempo-" for key, step in layout.TEMPO_STEPS.items()},
    "Tempo +1 or -1 BPM.",
)

WINDOW_MOVES = tuple(
    _one(f"Window {name.lower()}", key, f"Move the window {name.lower()}.", label=name)
    for key, name in zip(layout.WINDOW_MOVES, ("Up", "Down", "Left", "Right"))
)

# Columns 1, 15 and 16: the same in Session, Mixer and FX Mode.
_GLOBAL = (
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
)

_GLOBAL_SHIFT = (
    _one(
        "Stop all",
        layout.PLAY_STOP,
        "Stop all clips. In Linnstrument Mode, stops the selected track's clips.",
        label="StopAll",
    ),
    QUANTIZE,
    LAUNCH_QUANTIZATION,
    REDO,
    SHIFT_HELD,
)

_VIEW = (
    _scenes(layout.SCENE_COLUMN, "Launch a scene. Its FX snapshot, if it has one, lands as it starts."),
    _one(
        "Unmute all",
        layout.UNMUTE_ALL,
        "Unmute every track and return track in the Set. Orange while any is muted.",
        label="Unmute",
    ),
    _one(
        "Stop",
        layout.STOP,
        "Hold, then press a track's pad to stop that track's clips.",
    ),
)

_VIEW_SHIFT = (
    _scenes(layout.SCENE_COLUMN, "Launch with legato, leaving the FX snapshot alone."),
    _one(
        "Unsolo all",
        layout.UNMUTE_ALL,
        "Unsolo every track and return track in the Set. Blue while any is soloed.",
        label="Unsolo",
    ),
    _one(
        "Unarm all",
        layout.STOP,
        "Disarm every track in the Set. Red while any is armed.",
        label="Unarm",
    ),
)

_NAVIGATION = (
    _one(
        "Copy",
        layout.COPY,
        "Hold, press a clip, then an empty slot.",
    ),
    _one("Delete", layout.DELETE, "Hold, then press a clip or scene to delete it."),
    _one("Session", layout.SESSION, "Session Mode. In Session Mode, toggles the split view."),
    _one("Mixer", layout.MIXER, "Mixer Mode. Press again for Session Mode."),
    _one("FX", layout.FX, "FX Mode. Press again for Session Mode."),
    _one(
        "Seq",
        layout.SEQ,
        "Hold and press a clip, or tap, for Sequencer Mode.",
    ),
    DEVICE_CLIP,
)

_NAVIGATION_SHIFT = (
    *WINDOW_MOVES,
    TEMPO,
)

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
    "Select the track and arm it alone. Press the selected, armed track to disarm it.",
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
        "One fader per row, as in FX Mode, from the source Device/Clip + Fader source picks.",
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
        range(layout.FX_SLOTS[0][0], layout.FX_SLOTS[-1][0] + 1),
        ALL_PADS,
        "Sixteen snapshots of every rack's macros: slots 1–8 in column 11, 9–16 in column 12. "
        "Press an empty slot to store, a stored one to recall.",
    ),
    Item(
        "Scene snapshots",
        {key: f"Scene {pad}" for key, pad in zip(layout.FX_SCENE_SLOTS, SCENE_PADS)},
        "A snapshot per scene, scrolling with the scene pads. Press an empty one to store, a "
        "stored one to recall. Launching the scene morphs to it.",
    ),
    Block(
        "Bars",
        range(min(layout.FX_LENGTHS)[0], min(layout.FX_LENGTHS)[0] + 1),
        range(1, len(layout.FX_LENGTHS) + 1),
        "Hold one, then press a snapshot to morph to it over 1, 2, 4, 8 or 16 bars.",
    ),
)

_DEVICE_CLIP = (
    Item(
        "Tracks",
        {key: "Track-" if step < 0 else "Track+" for key, step in layout.DEVICE_CLIP_TRACK_STEPS.items()},
        "Select the previous or next track, through the returns and master.",
    ),
    Item(
        "Devices",
        {key: "Device-" if step < 0 else "Device+" for key, step in layout.DEVICE_CLIP_DEVICE_STEPS.items()},
        "Select the previous or next device on the selected track.",
    ),
    _one(
        "Fader source",
        layout.DEVICE_CLIP_SOURCE,
        "Switch the faders between Device FX and Mapped FX.",
        label="Source",
    ),
    Item("Device/Clip", {layout.DEVICE_CLIP: "DevClip"}, "Held.", variant=False),
)

RECORD_CLIP = _one(
    "Record Clip",
    layout.RECORD,
    "Record a new clip on the selected track.",
    label="RecClip",
)
CAPTURE_MIDI = _one("Capture MIDI", layout.CAPTURE, "Capture MIDI.", label="CapMIDI")

_LINNSTRUMENT = (
    PLAY,
    RECORD_CLIP,
    CAPTURE_MIDI,
    METRONOME,
    FIXED_LENGTH,
    UNDO,
    _one("Back", layout.MODE_PAD, "Back to the mode you came from: Session, Mixer, FX or Sequencer."),
    SHIFT,
)

STOP_TRACK = _one(
    "Stop track", layout.PLAY_STOP, "Stop the selected track's clips.", label="StopTrk"
)
SESSION_RECORD = _one(
    "Record",
    layout.RECORD,
    "Session Record on/off (Arrangement Record in Arrangement View). Blinks while recording.",
)
SCENE_PAGE = _one("Scene page", layout.SCENE_PAGE, "Show the scene page.", label="Scenes")

_LINNSTRUMENT_SHIFT = (
    STOP_TRACK,
    SESSION_RECORD,
    QUANTIZE,
    LAUNCH_QUANTIZATION,
    REDO,
    SCENE_PAGE,
    SHIFT_HELD,
)

_LINNSTRUMENT_SCENES = (
    _scenes(1, "Launch a scene and its FX snapshot, and go back to the controls."),
    _one("Back", layout.SHIFT, "Back to the controls without launching."),
)

# Sequencer Mode: column 1 as in Linnstrument Mode, and its own columns 15 and 16.
_SEQUENCER_SIDE = (
    PLAY,
    RECORD_CLIP,
    CAPTURE_MIDI,
    METRONOME,
    FIXED_LENGTH,
    UNDO,
    _one(
        "Linnstrument Mode",
        layout.MODE_PAD,
        "Switch to Linnstrument Mode, keeping the arm. Back returns here.",
        label="Linn",
    ),
    SHIFT,
    _one("Copy", layout.COPY, "Hold, press a step, then press steps to paste it onto."),
    _one(
        "Delete",
        layout.DELETE,
        "Hold, then press a step to clear it, or a note pad to remove that note from the clip.",
    ),
    _one("Session", layout.SESSION, "Back to Session Mode."),
    _one("Mixer", layout.MIXER, "Mixer Mode."),
    _one("FX", layout.FX, "FX Mode."),
    _one("Seq", layout.SEQ, "Back to Session Mode."),
    DEVICE_CLIP,
)

_SEQUENCER_SHIFT = (
    STOP_TRACK,
    SESSION_RECORD,
    QUANTIZE,
    LAUNCH_QUANTIZATION,
    REDO,
    SCENE_PAGE,
    *WINDOW_MOVES,
    TEMPO,
    SHIFT_HELD,
)

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
    _one("Double", layout.SEQ_DOUBLE, "Double the loop, notes and all."),
    _one("Halve", layout.SEQ_HALVE, "Halve the loop. Notes past the new end stay in the clip."),
    _one(
        "Follow",
        layout.SEQ_FOLLOW,
        "Follow on/off: the steps show the page that's playing. Blue while on.",
    ),
    Item(
        "Up/Down",
        {layout.SEQ_UP: "Up", layout.SEQ_DOWN: "Down"},
        "Move the note pads an octave up or down.",
    ),
    _one(
        "Notes/Settings",
        layout.SEQ_VIEW,
        "Switch columns 11–14 between the note pads and the settings.",
        label="View",
    ),
)

_SEQUENCER = (
    *_SEQUENCER_GRID,
    Block(
        "Notes",
        layout.SEQ_NOTE_COLUMNS,
        ALL_PADS,
        "Press to pick the note the steps edit, and hear it. Hold steps and press a note "
        "to add or remove it on them.",
    ),
)

_SEQUENCER_SETTINGS = (
    Item(
        "Rates",
        dict(zip(layout.SEQ_RATES, ("1/4", "1/8", "1/16", "1/32"))),
        "The step length: 1/4, 1/8, 1/16 or 1/32. The current one is blue.",
    ),
    _one("Triplet", layout.SEQ_TRIPLET, "Triplet steps on/off: orange while on."),
    Block(
        "Pages",
        range(layout.SEQ_PAGES[0][0], layout.SEQ_PAGES[-1][0] + 1),
        ALL_PADS,
        "Pages 1–16 of 64 steps: 1–8 in column 12, 9–16 in column 13. Press one to show it, "
        "or hold one and press another to loop both.",
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
    "mixer": _MIXER,
    "mixer-shift": _MIXER_SHIFT,
    "fx": _FX,
    "fx-shift": (),  # the grid is dark under Shift
    "device-clip": _DEVICE_CLIP,
    "linnstrument": _LINNSTRUMENT,
    "linnstrument-shift": _LINNSTRUMENT_SHIFT,
    "linnstrument-scenes": _LINNSTRUMENT_SCENES,
    "sequencer-side": _SEQUENCER_SIDE,
    "sequencer-shift": _SEQUENCER_SHIFT,
    "sequencer-grid": _SEQUENCER_GRID,
    "sequencer": _SEQUENCER,
    "sequencer-settings": _SEQUENCER_SETTINGS,
}

# The sections the manual lists, each with the section holding its Shift layer.
LISTS = {
    "global": "global-shift",
    "view": "view-shift",
    "navigation": "navigation-shift",
    "session": "session-shift",
    "split": "split-shift",
    "mixer": "mixer-shift",
    "fx": None,
    "device-clip": None,
    "linnstrument": "linnstrument-shift",
    "linnstrument-scenes": None,
    "sequencer-side": "sequencer-shift",
    "sequencer": None,
    "sequencer-settings": None,
}

# The sections each map is drawn from.
LAYERS = {
    Layer.SESSION: ("global", "view", "navigation", "session"),
    Layer.SESSION_SHIFT: ("global-shift", "view-shift", "navigation-shift", "session-shift"),
    Layer.SPLIT: ("global", "view", "navigation", "split"),
    Layer.MIXER: ("global", "view", "navigation", "mixer"),
    Layer.MIXER_SHIFT: ("global-shift", "view-shift", "navigation-shift", "mixer-shift"),
    Layer.FX: ("global", "view", "navigation", "fx"),
    Layer.FX_SHIFT: ("global-shift", "view-shift", "navigation-shift", "fx-shift"),
    Layer.MAPPED_FX: ("global", "view", "navigation", "fx"),
    Layer.LINNSTRUMENT: ("linnstrument",),
    Layer.LINNSTRUMENT_SHIFT: ("linnstrument-shift",),
    Layer.LINNSTRUMENT_SCENES: ("linnstrument-scenes",),
    Layer.SEQUENCER: ("sequencer-side", "sequencer"),
    Layer.SEQUENCER_SETTINGS: ("sequencer-side", "sequencer-grid", "sequencer-settings"),
    Layer.SEQUENCER_SHIFT: ("sequencer-shift", "sequencer"),
    Layer.SEQUENCER_DRUMS: ("sequencer-side", "sequencer"),
}

# Columns a map shows dimmed and unlabelled, per layer: none at present.
DIMMED = {}


def items(layer):
    return [item for section in LAYERS[layer] for item in SECTIONS[section]]


def ordered(section):
    # Left to right, then far to near, by each item's first pad.
    return sorted(SECTIONS[section], key=lambda item: item.keys[0])


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
