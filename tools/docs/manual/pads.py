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


def _one(name, key, callout, label=None):
    return Item(name, {key: label or name}, callout)


def _scenes(column, callout):
    labels = {(column, pad): f"Scene {pad}" for pad in SCENE_PADS}
    return Item("Scenes", labels, callout)


# Built per mode: each mode's Global and Navigation column are their own buttons.
def _play(pads):
    return _one("Play", pads.play_stop, "Start/stop. Blinks on the beat while playing.")


def _metronome(pads):
    return _one("Metronome", pads.metronome, "Metronome on/off. Blinks while on.", label="Metro")


def _fixed_length(pads):
    return _one(
        "Fixed Length",
        pads.fixed_length,
        "Record new clips at exactly 1, 2, 4 or 8 bars. Each press steps to the next length, "
        "then off.",
        label="Length",
    )


def _undo(pads):
    return _one("Undo", pads.undo, "Undo.")


def _shift(pads):
    return _one("Shift", pads.shift, "Hold for the Shift layer.")


def _quantize(pads):
    return _one(
        "Quantize", pads.quantize, "Quantize the current MIDI clip to 1/16 notes.", label="Quant"
    )


def _launch_quantization(pads):
    return _one(
        "Launch quantization",
        pads.launch_quantization,
        "Launch quantization on/off; red while off.",
        label="LaunchQ",
    )


def _redo(pads):
    return _one("Redo", pads.redo, "Redo.")


# A held pad's label names it and says so, one word per line.
def _shift_held(pads):
    return Item("Shift", {pads.shift: "SHIFT\nHELD"}, "Held.", variant=False)


def _device_clip(pads):
    return _one(
        "Device/Clip",
        pads.device_clip,
        "Tap to flip Live between Device and Clip view. Hold for the Device/Clip layer: tracks "
        "and devices.",
        label="DevClip",
    )


def _tempo(pads):
    return Item(
        "Tempo",
        {key: "Tempo+" if step > 0 else "Tempo-" for key, step in pads.tempo.items()},
        "Tempo +1 or -1 BPM.",
    )


def _window_moves(pads):
    return Item(
        "Window directions",
        {
            key: {(0, -1): "Up", (0, 1): "Down", (-1, 0): "Left", (1, 0): "Right"}[step]
            for key, step in pads.window.items()
        },
        "Move the Ableton session ring in the selected direction.",
    )


def _fader_source(pads):
    return _one(
        "Fader source",
        pads.fader_source,
        "Switch the faders between Device FX and Mapped FX, in every mode but Linnstrument "
        "Mode. In Session and Mixer Mode, the split view's snapshots come third.",
        label="Source",
    )


# Columns 1, 15 and 16: the same in Session, Mixer and FX Mode.
_GLOBAL = (
    _play(layout.GLOBAL),
    _one(
        "Record",
        layout.GLOBAL.record,
        "Session Record on/off (Arrangement Record in Arrangement View). Blinks while "
        "recording. In Linnstrument Mode, records a new clip on the selected track.",
    ),
    _one(
        "Capture",
        layout.GLOBAL.capture,
        "Capture and Insert Scene. In Linnstrument Mode, captures MIDI.",
    ),
    _metronome(layout.GLOBAL),
    _fixed_length(layout.GLOBAL),
    _undo(layout.GLOBAL),
    _one("Linnstrument Mode", layout.GLOBAL.linnstrument_mode, "Switch to Linnstrument Mode.", label="Linn"),
    _shift(layout.GLOBAL),
)

_GLOBAL_SHIFT = (
    _one(
        "Stop all",
        layout.GLOBAL_SHIFT.stop_all,
        "Stop all clips. In Linnstrument Mode, stops the selected track's clips.",
        label="StopAll",
    ),
    _quantize(layout.GLOBAL_SHIFT),
    _launch_quantization(layout.GLOBAL_SHIFT),
    _redo(layout.GLOBAL_SHIFT),
    _shift_held(layout.GLOBAL),
)

_VIEW = (
    _scenes(layout.SCENE_COLUMN, "Launch a scene. Its FX snapshot, if it has one, lands as it starts."),
    _one(
        "Unmute all",
        layout.VIEW.unmute_all,
        "Unmute every track and return track in the Set. Orange while any is muted.",
        label="Unmute",
    ),
    _one(
        "Stop",
        layout.VIEW.stop,
        "Hold, then press a track's pad to stop that track's clips.",
    ),
)

_VIEW_SHIFT = (
    _scenes(layout.SCENE_COLUMN, "Launch with legato, leaving the FX snapshot alone."),
    _one(
        "Unsolo all",
        layout.VIEW_SHIFT.unsolo_all,
        "Unsolo every track and return track in the Set. Blue while any is soloed.",
        label="Unsolo",
    ),
    _one(
        "Unarm all",
        layout.VIEW_SHIFT.unarm_all,
        "Disarm every track in the Set. Red while any is armed.",
        label="Unarm",
    ),
)

_NAVIGATION = (
    _one(
        "Copy",
        layout.NAVIGATION.copy,
        "Hold, press a clip, then an empty slot.",
    ),
    _one("Delete", layout.NAVIGATION.delete, "Hold, then press a clip or scene to delete it."),
    _one("Session", layout.NAVIGATION.session, "Session Mode. In Session Mode, toggles the split view."),
    _one("Mixer", layout.NAVIGATION.mixer, "Mixer Mode. In Mixer Mode, toggles the split view."),
    _one("FX", layout.NAVIGATION.fx, "FX Mode. Press again for Session Mode."),
    _one(
        "Seq",
        layout.NAVIGATION.seq,
        "Hold and press a clip, or tap, for Sequencer Mode.",
    ),
    _device_clip(layout.NAVIGATION),
)

_NAVIGATION_SHIFT = (
    _window_moves(layout.NAVIGATION_SHIFT),
    _tempo(layout.NAVIGATION_SHIFT),
    _fader_source(layout.NAVIGATION_SHIFT),
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
        "Sixteen snapshots of every rack's macros: slots 1–8 in column 11, 9–16 in column 12. "
        "Press an empty slot to store, a stored one to recall.",
    ),
    Item(
        "Scene snapshots",
        {key: f"Scene {pad}" for key, pad in zip(layout.FX.scene_slots, SCENE_PADS)},
        "A snapshot per scene, scrolling with the scene pads. Press an empty one to store, a "
        "stored one to recall. Launching the scene morphs to it.",
    ),
    Item(
        "Bars",
        {key: f"{bars} bar" if bars == 1 else f"{bars} bars" for key, bars in layout.FX.bars.items()},
        "Hold one, then press a snapshot to morph to it over 1, 2, 4, 8 or 16 bars, or a "
        "scene to launch it on that bar line.",
    ),
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
    Item(
        "Tracks",
        {key: "Track-" if step < 0 else "Track+" for key, step in layout.DEVICE_CLIP.tracks.items()},
        "Select the previous or next track, through the returns and master, and give its "
        "first rack the blue hand.",
    ),
    Item(
        "Devices",
        {key: "Device-" if step < 0 else "Device+" for key, step in layout.DEVICE_CLIP.devices.items()},
        "Select the previous or next device on the selected track.",
    ),
    Item(
        "Device/Clip",
        {layout.NAVIGATION.device_clip: "DEV\nHELD"},
        "Hold it for this layer. A tap, pressing nothing else, flips Live between Device and "
        "Clip view instead.",
        variant=False,
    ),
)

def _record_clip(pads):
    return _one(
        "Record Clip", pads.record_clip, "Record a new clip on the selected track.", label="RecClip"
    )


def _capture_midi(pads):
    return _one("Capture MIDI", pads.capture_midi, "Capture MIDI.", label="CapMIDI")


def _stop_track(pads):
    return _one("Stop track", pads.stop_track, "Stop the selected track's clips.", label="StopTrk")


def _session_record(pads):
    return _one(
        "Record",
        pads.record,
        "Session Record on/off (Arrangement Record in Arrangement View). Blinks while "
        "recording.",
    )


def _scene_page(pads):
    return _one("Scene page", pads.scene_page, "Show the scene page.", label="Scenes")


def _player_shift(pads, normal):
    # Linnstrument and Sequencer Mode's Shift layer.
    return (
        _stop_track(pads),
        _session_record(pads),
        _quantize(pads),
        _launch_quantization(pads),
        _redo(pads),
        _scene_page(pads),
        _shift_held(normal),
    )


_LINNSTRUMENT = (
    _play(layout.LINNSTRUMENT),
    _record_clip(layout.LINNSTRUMENT),
    _capture_midi(layout.LINNSTRUMENT),
    _metronome(layout.LINNSTRUMENT),
    _fixed_length(layout.LINNSTRUMENT),
    _undo(layout.LINNSTRUMENT),
    _one("Back", layout.LINNSTRUMENT.back, "Back to the mode you came from: Session, Mixer, FX or Sequencer."),
    _shift(layout.LINNSTRUMENT),
)

_LINNSTRUMENT_SHIFT = _player_shift(layout.LINNSTRUMENT_SHIFT, layout.LINNSTRUMENT)

_LINNSTRUMENT_SCENES = (
    _scenes(layout.GLOBAL_COLUMN, "Launch a scene and its FX snapshot, and go back to the controls."),
    _one("Back", layout.LINNSTRUMENT_SCENES.back, "Back to the controls without launching."),
)

# Sequencer Mode: the Global column as in Linnstrument Mode, and its own columns 15 and 16.
_SEQUENCER_GLOBAL = (
    _play(layout.SEQUENCER_GLOBAL),
    _record_clip(layout.SEQUENCER_GLOBAL),
    _capture_midi(layout.SEQUENCER_GLOBAL),
    _metronome(layout.SEQUENCER_GLOBAL),
    _fixed_length(layout.SEQUENCER_GLOBAL),
    _undo(layout.SEQUENCER_GLOBAL),
    _one(
        "Linnstrument Mode",
        layout.SEQUENCER_GLOBAL.linnstrument_mode,
        "Switch to Linnstrument Mode, keeping the arm. Back returns here.",
        label="Linn",
    ),
    _shift(layout.SEQUENCER_GLOBAL),
)

SEQ_COPY = _one(
    "Copy", layout.SEQUENCER_NAV.copy, "Hold, press a step, then press steps to paste it onto."
)
SEQ_DELETE = _one(
    "Delete",
    layout.SEQUENCER_NAV.delete,
    "Hold, then press a step to clear it, or a note pad to remove that note from the clip.",
)

_SEQUENCER_NAV = (
    SEQ_COPY,
    SEQ_DELETE,
    _one("Session", layout.SEQUENCER_NAV.session, "Back to Session Mode."),
    _one("Mixer", layout.SEQUENCER_NAV.mixer, "Mixer Mode."),
    _one("FX", layout.SEQUENCER_NAV.fx, "FX Mode."),
    _one("Seq", layout.SEQUENCER_NAV.seq, "Back to Session Mode."),
    _device_clip(layout.SEQUENCER_NAV),
)

_SEQUENCER_GLOBAL_SHIFT = _player_shift(layout.SEQUENCER_GLOBAL_SHIFT, layout.SEQUENCER_GLOBAL)

_SEQUENCER_NAV_SHIFT = (
    _window_moves(layout.SEQUENCER_NAV_SHIFT),
    _tempo(layout.SEQUENCER_NAV_SHIFT),
    _fader_source(layout.SEQUENCER_NAV_SHIFT),
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
    _one("Double", layout.SEQUENCER_GRID.double, "Double the loop, notes and all."),
    _one("Halve", layout.SEQUENCER_GRID.halve, "Halve the loop. Notes past the new end stay in the clip."),
    _one(
        "Follow",
        layout.SEQUENCER_GRID.follow,
        "Follow on/off: the steps show the page that's playing. Blue while on.",
    ),
    Item(
        "Up/Down",
        {layout.SEQUENCER_GRID.up: "Up", layout.SEQUENCER_GRID.down: "Down"},
        "Move the note pads an octave up or down.",
    ),
    _one(
        "View",
        layout.SEQUENCER_GRID.view,
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
        "Choose the note the steps write: press a pad to select its note and hear it on the "
        "armed track. Hold steps and press a pad to add or remove that note on them.",
    ),
)

_SEQUENCER_SETTINGS = (
    Item(
        "Rates",
        dict(zip(layout.SEQUENCER_SETTINGS.rates, ("1/4", "1/8", "1/16", "1/32"))),
        "The step length: 1/4, 1/8, 1/16 or 1/32. The current one is blue.",
    ),
    _one("Triplet", layout.SEQUENCER_SETTINGS.triplet, "Triplet steps on/off: orange while on."),
    Block(
        "Pages",
        range(layout.SEQUENCER_SETTINGS.pages[0][0], layout.SEQUENCER_SETTINGS.pages[-1][0] + 1),
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
    "split-snapshots": _SPLIT_SNAPSHOTS,
    "mixer": _MIXER,
    "mixer-shift": _MIXER_SHIFT,
    "mixer-split": _MIXER_SPLIT,
    "mixer-split-shift": _MIXER_SPLIT_SHIFT,
    "fx": _FX,
    "fx-shift": (),  # the grid is dark under Shift
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

