"""Button registry: position, label, manual text and messages per button, from buttons.toml."""

import tomllib
from pathlib import Path
from types import SimpleNamespace

from .model import ShowMessage

PATH = Path(__file__).parent.parent / "buttons.toml"

# The manual's section keys (tools/docs/manual/pads.py SECTIONS), plus the held-modifier
# sections that have combos but no manual section of their own.
SECTIONS = frozenset(
    {
        "global",
        "global-shift",
        "view",
        "view-shift",
        "navigation",
        "navigation-shift",
        "session",
        "session-shift",
        "split",
        "split-shift",
        "split-snapshots",
        "mixer",
        "mixer-shift",
        "mixer-split",
        "mixer-split-shift",
        "fx",
        "fx-shift",
        "device-clip",
        "linnstrument",
        "linnstrument-shift",
        "linnstrument-scenes",
        "sequencer-global",
        "sequencer-nav",
        "sequencer-global-shift",
        "sequencer-nav-shift",
        "sequencer-grid",
        "sequencer",
        "sequencer-settings",
        "sequencer-functions",
        "copy",
        "delete",
        "stop",
        "sequencer-copy",
        "sequencer-delete",
    }
)

# The sections live together, by layer: no two of a layer's buttons may share a pad, and none
# may sit on a fixed region of any of its sections. The first thirteen are the manual's maps
# (tools/docs/manual/pads.py LAYERS, kept equal by a test); the rest have no map.
LAYERS = {
    "SESSION": ("global", "view", "navigation", "session"),
    "SESSION_SHIFT": ("global-shift", "view-shift", "navigation-shift", "session-shift"),
    "SPLIT": ("global", "view", "navigation", "split"),
    "SPLIT_SNAPSHOTS": ("global", "view", "navigation", "split-snapshots"),
    "MIXER": ("global", "view", "navigation", "mixer"),
    "MIXER_SPLIT": ("global", "view", "navigation", "mixer-split"),
    "MIXER_SHIFT": ("global-shift", "view-shift", "navigation-shift", "mixer-shift"),
    "FX": ("global", "view", "navigation", "fx"),
    "FX_SHIFT": ("global-shift", "view-shift", "navigation-shift", "fx-shift"),
    "SEQUENCER": ("sequencer-global", "sequencer-nav", "sequencer"),
    "SEQUENCER_SETTINGS": ("sequencer-global", "sequencer-nav", "sequencer-grid", "sequencer-settings"),
    "SEQUENCER_SHIFT": ("sequencer-global-shift", "sequencer-nav-shift", "sequencer"),
    "SEQUENCER_DRUMS": ("sequencer-global", "sequencer-nav", "sequencer"),
    "SPLIT_SHIFT": ("global-shift", "view-shift", "navigation-shift", "split-shift"),
    "MIXER_SPLIT_SHIFT": ("global-shift", "view-shift", "navigation-shift", "mixer-split-shift"),
    "LINNSTRUMENT": ("linnstrument",),
    "LINNSTRUMENT_SHIFT": ("linnstrument-shift",),
    "LINNSTRUMENT_SCENES": ("linnstrument-scenes",),
}

# In Linnstrument Mode only the device's left split, column 1, reaches BleakLoop.
LEFT_SPLIT_SECTIONS = ("linnstrument", "linnstrument-shift", "linnstrument-scenes")

MAX_LABEL = 7
COLUMNS = range(1, 17)
PADS = range(1, 9)


def _is_int(value):
    return isinstance(value, int) and not isinstance(value, bool)


def _is_pad(value):
    return isinstance(value, list) and len(value) == 2 and all(_is_int(part) for part in value)


def _is_value(value):
    if isinstance(value, list):
        return all(_is_value(part) for part in value)
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _is_messages(value):
    return isinstance(value, dict) and all(isinstance(text, str) for text in value.values())


FIELDS = {
    "section": lambda value: isinstance(value, str),
    "pad": _is_pad,
    "label": lambda value: isinstance(value, str),
    "manual": lambda value: isinstance(value, str),
    "message": lambda value: isinstance(value, str),
    "show": lambda value: isinstance(value, bool),
    "group": lambda value: isinstance(value, str),
    "value": _is_value,
    "outcomes": _is_messages,
    "refusals": _is_messages,
}

TOP_LEVEL = {"manual_format": str, "system": dict}


class Registry:
    def __init__(self, data):
        self.data = data
        self.items = dict(_walk({key: value for key, value in data.items() if key not in TOP_LEVEL}))
        _validate(data, self.items)

    def entry(self, id):
        return self.items[id]

    def entries(self):
        return dict(self.items)

    def pos(self, id):
        column, pad = self.entry(id)["pad"]
        return (column, pad)

    def say(self, id, outcome=None, **values):
        # The button's message, or one of its outcomes; nothing when its show flag is off.
        item = self.entry(id)
        if not item.get("show", True):
            return []
        template = item["outcomes"][outcome] if outcome else item["message"]
        return [_message(id, template, values)]

    def refuse(self, id, key, **values):
        # Always shown, whatever the show flag says: a silent press that does nothing confuses.
        return [_message(id, self.entry(id)["refusals"][key], values)]

    def system(self, key, **values):
        return _format(self.data["system"][key], values)[0]

    def section(self, name):
        # Each button's position by its name, and each group as {position: value}. Mutable,
        # so a test or a mockup can move one button.
        found = SimpleNamespace()
        for id, item in self.items.items():
            if item["section"] != name or "pad" not in item:
                continue
            setattr(found, id.rsplit(".", 1)[1], self.pos(id))
            if "group" in item:
                group = item["group"]
                setattr(found, group.rsplit(".", 1)[1], self.group(group))
        return found

    def group(self, id):
        return {
            self.pos(key): _freeze(item["value"])
            for key, item in self.items.items()
            if item.get("group") == id
        }


def _format(template, values):
    # (text, problem): the raw template, and why, when a placeholder can't be filled.
    try:
        return template.format(**values), ""
    except (KeyError, IndexError, ValueError) as error:
        return template, f"{template!r} could not be formatted: {error!r}"


def _message(id, template, values):
    text, problem = _format(template, values)
    return ShowMessage(text, f"{id}: {problem}" if problem else "")


def _freeze(value):
    return tuple(_freeze(part) for part in value) if isinstance(value, list) else value


def _walk(table, prefix=""):
    # An entry is a table with a section. A table of tables nests further IDs.
    for key, value in table.items():
        id = f"{prefix}{key}"
        if not isinstance(value, dict):
            raise ValueError(f"{id}: not a table")
        if "section" in value:
            yield id, value
        elif all(isinstance(child, dict) for child in value.values()):
            yield from _walk(value, f"{id}.")
        else:
            raise ValueError(f"{id}: no section")


def _validate(data, items):
    for key, kind in TOP_LEVEL.items():
        if key in data and not isinstance(data[key], kind):
            raise ValueError(f"{key}: wrong type")
    if not _is_messages(data.get("system", {})):
        raise ValueError("system: every message must be a string")
    seen = {}
    regions = _regions()
    for id, item in items.items():
        for field, value in item.items():
            if field not in FIELDS:
                raise ValueError(f"{id}: unknown field {field!r}")
            if not FIELDS[field](value):
                raise ValueError(f"{id}: {field} has the wrong type")
        section = item["section"]
        if section not in SECTIONS:
            raise ValueError(f"{id}: unknown section {section!r}")
        if id.rsplit(".", 1)[0] != section.replace("-", "_"):
            raise ValueError(f"{id}: an ID starts with its section, as {section.replace('-', '_')}.")
        if len(item.get("label", "")) > MAX_LABEL:
            raise ValueError(f"{id}: label longer than {MAX_LABEL} characters")
        if "group" in item and not ("pad" in item and "value" in item):
            raise ValueError(f"{id}: a group member needs a pad and a value")
        if "pad" not in item:
            continue
        column, pad = item["pad"]
        if column not in COLUMNS or pad not in PADS:
            raise ValueError(f"{id}: pad {item['pad']} is off the surface")
        if section in LEFT_SPLIT_SECTIONS and column != 1:
            raise ValueError(f"{id}: in Linnstrument Mode only column 1 reaches BleakLoop")
        if (section, column, pad) in seen:
            raise ValueError(f"{id}: pad {item['pad']} is taken by {seen[section, column, pad]}")
        seen[section, column, pad] = id
        for columns, pads in regions.get(section, ()):
            if column in columns and pad in pads:
                raise ValueError(f"{id}: pad {item['pad']} is in a fixed region of {section}")
    _check_layers(items, regions)


def _check_layers(items, regions):
    for layer, sections in LAYERS.items():
        fixed = [region for section in sections for region in regions.get(section, ())]
        taken = {}
        for id, item in items.items():
            if item["section"] not in sections or "pad" not in item:
                continue
            column, pad = key = tuple(item["pad"])
            if key in taken:
                raise ValueError(f"{id}: pad {item['pad']} is taken by {taken[key]} in the {layer} layer")
            taken[key] = id
            for columns, pads in fixed:
                if column in columns and pad in pads:
                    raise ValueError(f"{id}: pad {item['pad']} is in a fixed region of the {layer} layer")


def _regions():
    # The fixed regions (clip grid, scene pads, faders, steps) live in each section: no button
    # may sit on them. Imported here: layout reads its positions from this module.
    from . import layout

    every = range(1, layout.ROWS + 1)
    scenes = range(1, layout.WINDOW_SCENES + 1)
    grid = ((layout.GRID_COLUMNS, every),)
    split_tracks = range(layout.GRID_COLUMNS[0], layout.GRID_COLUMNS[0] + layout.SPLIT_TRACKS)
    split = ((split_tracks, every), (layout.SPLIT_FADER_COLUMNS, every))
    steps = ((layout.SEQ_STEP_COLUMNS, every),)
    sequencer = (*steps, (layout.SEQ_NOTE_COLUMNS, every))
    return {
        "view": ((range(layout.SCENE_COLUMN, layout.SCENE_COLUMN + 1), scenes),),
        "view-shift": ((range(layout.SCENE_COLUMN, layout.SCENE_COLUMN + 1), scenes),),
        "session": grid,
        "session-shift": grid,
        "split": split,
        "split-shift": ((split_tracks, every),),
        "split-snapshots": ((split_tracks, every),),
        "mixer": grid,
        "mixer-shift": grid,
        "mixer-split": split,
        "mixer-split-shift": ((split_tracks, every),),
        "fx": ((layout.FX_FADER_COLUMNS, every),),
        "linnstrument-scenes": ((range(layout.GLOBAL_COLUMN, layout.GLOBAL_COLUMN + 1), scenes),),
        "sequencer-grid": steps,
        "sequencer": sequencer,
        "sequencer-functions": sequencer,
        "sequencer-settings": steps,
    }


def load(path):
    with open(path, "rb") as file:
        return Registry(tomllib.load(file))


# Loaded on first use: layout's fixed regions must exist before the registry validates.
_registry = None


def _get():
    global _registry
    if _registry is None:
        _registry = load(PATH)
    return _registry


def entry(id):
    return _get().entry(id)


def entries():
    return _get().entries()


def pos(id):
    return _get().pos(id)


def group(id):
    return _get().group(id)


def section(name):
    return _get().section(name)


def say(id, outcome=None, **values):
    return _get().say(id, outcome, **values)


def refuse(id, key, **values):
    return _get().refuse(id, key, **values)


def system(key, **values):
    return _get().system(key, **values)
