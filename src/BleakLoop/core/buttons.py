"""Button registry, from buttons.toml: where each button sits and the function it runs, and
each function's label, manual text and messages."""

import tomllib
from pathlib import Path

from . import userfile
from .catalogue import LINNSTRUMENT, MESSAGE_ONLY, MODES, SEQUENCER, SESSION
from .model import ShowMessage

PATH = Path(__file__).parent.parent / "buttons.toml"


def user_path(script):
    # The user's buttons file, in the User Library beside Remote Scripts, so an upgrade keeps
    # it. None unless the script sits in a Remote Scripts folder: a repo checkout never reads
    # a user's own file. Not resolved, as the developer install is a symlink.
    if script.parent.name != "Remote Scripts":
        return None
    return script.parent.parent / "BleakLoop" / "buttons.toml"


USER_PATH = user_path(Path(__file__).parent.parent)

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
    # Sequencer Mode's column 15 is live on both layers, beside its own columns.
    "SEQUENCER_BUTTONS": ("sequencer-global", "sequencer-nav", "sequencer-grid", "sequencer"),
    "SEQUENCER_SHIFT_BUTTONS": (
        "sequencer-global-shift",
        "sequencer-nav-shift",
        "sequencer-grid",
        "sequencer",
    ),
    "LINNSTRUMENT": ("linnstrument",),
    "LINNSTRUMENT_SHIFT": ("linnstrument-shift",),
    "LINNSTRUMENT_SCENES": ("linnstrument-scenes",),
}

# In Linnstrument Mode only the device's left split, column 1, reaches BleakLoop.
LEFT_SPLIT_SECTIONS = ("linnstrument", "linnstrument-shift", "linnstrument-scenes")

# A mode's section falls back to its base: the base's buttons it doesn't override on the same
# pad still work there, if their function runs in that mode, and are dark otherwise.
FALLBACK = {
    "linnstrument": "global",
    "linnstrument-shift": "global-shift",
    "sequencer-global": "global",
    "sequencer-global-shift": "global-shift",
    "sequencer-nav": "navigation",
    "sequencer-nav-shift": "navigation-shift",
}


def section_modes(section):
    # The modes a section's buttons work in.
    if section == "linnstrument-scenes":
        return frozenset({LINNSTRUMENT, SEQUENCER})
    if section.startswith("linnstrument"):
        return frozenset({LINNSTRUMENT})
    if section.startswith("sequencer"):
        return frozenset({SEQUENCER})
    if section == "device-clip":
        return frozenset({SESSION, SEQUENCER})
    return frozenset({SESSION})


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


def _is_text(value):
    return isinstance(value, str)


ENTRY_FIELDS = {
    "pad": _is_pad,
    "does": _is_text,
    "value": _is_value,
    "label": _is_text,
}

FUNCTION_FIELDS = {
    "label": _is_text,
    "manual": _is_text,
    "message": _is_text,
    "show": lambda value: isinstance(value, bool),
    "manual_in": _is_messages,  # the manual's text in one section, over manual
    "outcomes": _is_messages,
    "refusals": _is_messages,
}

TOP_LEVEL = {"manual_format": str, "system": dict, "functions": dict}


class Section:
    """One section's buttons: each by name as its (column, pad), each group by its function
    as {(column, pad): value}. Mutable, so a test or a mockup can move one button. A name the
    section doesn't have comes from its fallback, unless overridden there or unable to run."""

    def __init__(self, name, buttons, does, base=None):
        self.__dict__.update(buttons)
        self.__dict__["_name"] = name
        self.__dict__["_does"] = does
        self.__dict__["_base"] = base
        self.__dict__["_modes"] = section_modes(name)
        self.__dict__["_built"] = frozenset(buttons)

    def _refill(self, buttons, does):
        # A reload: new buttons in the same object, so whatever holds it (a fallback, a module
        # attribute) sees them. Name, fallback and modes stay.
        for key in [key for key in self.__dict__ if not key.startswith("_")]:
            del self.__dict__[key]
        self.__dict__.update(buttons)
        self.__dict__["_does"] = dict(does)
        self.__dict__["_built"] = frozenset(buttons)

    def __getattr__(self, attr):
        base = self.__dict__.get("_base")
        if attr.startswith("_") or base is None:
            raise AttributeError(attr)
        value = getattr(base, attr)
        if not MODES[base._does[attr]] & self._modes:
            raise AttributeError(f"{attr} doesn't run in {self._name}")
        mine = self._own_pads()
        if isinstance(value, dict):
            return {key: step for key, step in value.items() if key not in mine}
        if value in mine:
            raise AttributeError(f"{attr} is overridden in {self._name}")
        return value

    def __setattr__(self, attr, value):
        # Moving a fallback's button here overrides it; moving it back to the fallback's own
        # pad drops the override, so the section follows its fallback again.
        base, built = self._base, self._built
        if base is not None and attr not in built and attr in base._does:
            if value == getattr(base, attr, None):
                self.__dict__.pop(attr, None)
                return
            self._does[attr] = base._does[attr]
        self._does.setdefault(attr, attr)
        self.__dict__[attr] = value

    def _own(self):
        return {key: value for key, value in self.__dict__.items() if not key.startswith("_")}

    def _own_pads(self):
        return {key for _, _, key, _ in _expand(self._own(), self._does)}

    def buttons(self):
        # (name, function, (column, pad), value) for every button live in this section.
        mine = list(_expand(self._own(), self._does))
        taken = {key for _, _, key, _ in mine}
        inherited = []
        if self._base is not None:
            inherited = [
                button
                for button in self._base.buttons()
                if button[2] not in taken and MODES[button[1]] & self._modes
            ]
        return mine + inherited

    def at(self, key):
        # The button live on a pad, or None.
        return next((button for button in self.buttons() if button[2] == key), None)


def _expand(own, does):
    for name, value in own.items():
        if isinstance(value, dict):
            for key, step in value.items():
                yield name, name, key, step
        elif isinstance(value, tuple) and value and isinstance(value[0], tuple):
            for index, key in enumerate(value):
                yield name, name, key, index + 1
        else:
            yield name, does[name], value, None


class Registry:
    def __init__(self, data):
        self.data = data
        self.functions = data.get("functions", {})
        self.items = dict(_walk({key: value for key, value in data.items() if key not in TOP_LEVEL}))
        _validate(data, self.items)

    def entry(self, id):
        return self.items[id]

    def entries(self):
        return dict(self.items)

    def function(self, name):
        return self.functions.get(name, {})

    def label(self, name, section, value=None):
        # A pad's label: its own button's, for a group's pad, else its function's.
        while section is not None:
            for id, item in self.items.items():
                if item["section"] == section and _does(id, item) == name and "label" in item:
                    if value is None or _freeze(item.get("value")) == value:
                        return item["label"]
            section = FALLBACK.get(section)
        return self.function(name).get("label", name)

    def manual(self, name, section, label):
        # The manual's text for a function in a section, or the default built from its label.
        function = self.function(name)
        text = function.get("manual_in", {}).get(section) or function.get("manual")
        return text or self.data.get("manual_format", "{label}.").format(label=label)

    def pos(self, id):
        column, pad = self.entry(id)["pad"]
        return (column, pad)

    def say(self, name, outcome=None, /, **values):
        # The function's message, or one of its outcomes; nothing when its show flag is off.
        item = self.function(name)
        if not item.get("show", True):
            return []
        template = item["outcomes"][outcome] if outcome else item["message"]
        return [_message(name, template, values)]

    def refuse(self, name, key, /, **values):
        # Always shown, whatever the show flag says: a silent press that does nothing confuses.
        return [_message(name, self.function(name)["refusals"][key], values)]

    def system(self, key, /, **values):
        return _format(self.data["system"][key], values)[0]

    def section(self, name, base=None):
        prefix = name.replace("-", "_")
        buttons, does = {}, {}
        for id, item in self.items.items():
            if item["section"] != name:
                continue
            short = id[len(prefix) + 1 :]
            function = _does(id, item)
            if "value" in item:
                group = buttons.setdefault(function, {})
                group[tuple(item["pad"])] = _freeze(item["value"])
                does[function] = function
            else:
                buttons[short] = tuple(item["pad"])
                does[short] = function
        return Section(name, buttons, does, base)

    def group(self, section, function):
        return {
            tuple(item["pad"]): _freeze(item["value"])
            for id, item in self.items.items()
            if item["section"] == section and _does(id, item) == function and "value" in item
        }


def _does(id, item):
    return item.get("does", id.rsplit(".", 1)[1])


def _format(template, values):
    # (text, problem): the raw template, and why, when a placeholder can't be filled.
    try:
        return template.format(**values), ""
    except (KeyError, IndexError, ValueError) as error:
        return template, f"{template!r} could not be formatted: {error!r}"


def _message(name, template, values):
    text, problem = _format(template, values)
    return ShowMessage(text, f"{name}: {problem}" if problem else "")


def _freeze(value):
    return tuple(_freeze(part) for part in value) if isinstance(value, list) else value


def _walk(table):
    # [<section>.<button>]: the section's name with underscores for hyphens.
    for key, buttons in table.items():
        section = key.replace("_", "-")
        if section not in SECTIONS:
            raise ValueError(f"{key}: unknown section {section!r}")
        if not isinstance(buttons, dict) or not all(isinstance(b, dict) for b in buttons.values()):
            raise ValueError(f"{key}: a section holds button tables, as [{key}.<name>]")
        for name, item in buttons.items():
            yield f"{key}.{name}", {**item, "section": section}


def _validate(data, items):
    for key, kind in TOP_LEVEL.items():
        if key in data and not isinstance(data[key], kind):
            raise ValueError(f"{key}: wrong type")
    if not _is_messages(data.get("system", {})):
        raise ValueError("system: every message must be a string")
    for name, function in data.get("functions", {}).items():
        if name not in MODES and name not in MESSAGE_ONLY:
            raise ValueError(f"functions.{name}: no such function")
        if not isinstance(function, dict):
            raise ValueError(f"functions.{name}: not a table")
        for field, value in function.items():
            if field not in FUNCTION_FIELDS:
                raise ValueError(f"functions.{name}: unknown field {field!r}")
            if not FUNCTION_FIELDS[field](value):
                raise ValueError(f"functions.{name}: {field} has the wrong type")
        if len(function.get("label", "")) > MAX_LABEL:
            raise ValueError(f"functions.{name}: label longer than {MAX_LABEL} characters")
        for section in function.get("manual_in", {}):
            if section not in SECTIONS:
                raise ValueError(f"functions.{name}.manual_in: unknown section {section!r}")
    seen = {}
    regions = _regions()
    for id, item in items.items():
        section = item["section"]
        for field, value in item.items():
            if field == "section":
                continue
            if field not in ENTRY_FIELDS:
                raise ValueError(f"{id}: unknown field {field!r}")
            if not ENTRY_FIELDS[field](value):
                raise ValueError(f"{id}: {field} has the wrong type")
        if "pad" not in item:
            raise ValueError(f"{id}: no pad")
        function = _does(id, item)
        if function not in MODES:
            raise ValueError(f"{id}: no such function {function!r}")
        if not MODES[function] & section_modes(section):
            modes = ", ".join(sorted(MODES[function]))
            raise ValueError(f"{id}: {function} doesn't run in {section}, only in {modes}")
        if len(item.get("label", "")) > MAX_LABEL:
            raise ValueError(f"{id}: label longer than {MAX_LABEL} characters")
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


def _live(items, section):
    # (id, (column, pad)) for each button live in a section, its fallback's included.
    own = [(id, tuple(item["pad"])) for id, item in items.items() if item["section"] == section]
    taken = {key for _, key in own}
    base = FALLBACK.get(section)
    if base is None:
        return own
    modes = section_modes(section)
    inherited = [
        (id, key)
        for id, key in _live(items, base)
        if key not in taken and MODES[_does(id, items[id])] & modes
    ]
    return own + inherited


def _check_layers(items, regions):
    for layer, sections in LAYERS.items():
        fixed = [region for section in sections for region in regions.get(section, ())]
        taken = {}
        for section in sections:
            for id, key in _live(items, section):
                column, pad = key
                if key in taken:
                    raise ValueError(f"{id}: pad {list(key)} is taken by {taken[key]} in the {layer} layer")
                taken[key] = id
                for columns, pads in fixed:
                    if column in columns and pad in pads:
                        raise ValueError(f"{id}: pad {list(key)} is in a fixed region of the {layer} layer")


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


def _read(path):
    with open(path, "rb") as file:
        return tomllib.load(file)


def load(path, user_path=None):
    # The shipped file, with the user's file over it when there is one.
    data = _read(path)
    overlay, editor = {}, dict(userfile.EDITOR)
    if user_path is not None and Path(user_path).exists():
        try:
            try:
                overlay = _read(user_path)
            except OSError as error:
                raise ValueError(f"couldn't read it: {error.strerror}") from None
            data, editor = userfile.merge(data, overlay, str(user_path))
            registry = Registry(data)
        except ValueError as error:
            text = str(error)
            raise ValueError(text if text.startswith(str(user_path)) else f"{user_path}: {text}") from None
    else:
        registry = Registry(data)
    registry.overlay, registry.editor = overlay, editor
    return registry


# Loaded on first use: layout's fixed regions must exist before the registry validates.
_registry = None
# Why the user's file was left out at startup, for the surface to show; None when it loaded.
user_error = None


def _get():
    global _registry, user_error
    if _registry is None:
        try:
            _registry = load(PATH, USER_PATH)
        except ValueError as error:
            user_error = str(error)
            _registry = load(PATH)
    return _registry


def stamps(path=None, user_path=None):
    # Each file's (modification time, size), or None while it's missing: a change in either
    # means the files changed on disk.
    def stamp(file):
        try:
            info = Path(file).stat()
        except OSError:
            return None
        return info.st_mtime_ns, info.st_size

    user_path = user_path or USER_PATH
    return stamp(path or PATH), None if user_path is None else stamp(user_path)


def reload(path=None, user_path=None):
    # Loads the files again and refills layout's sections in place. A file that fails its
    # checks raises and leaves the current layout as it was.
    global _registry, user_error
    registry = load(path or PATH, user_path or USER_PATH)
    _registry, user_error = registry, None
    from . import layout

    layout.refresh()


def _neighbours(section):
    # The other sections live in a layer with this one.
    return sorted({other for names in LAYERS.values() if section in names for other in names} - {section})


def _pads(regions):
    return [[column, pad] for columns, pads in regions for column in columns for pad in pads]


def describe(registry=None):
    """The layout as plain data, for the editor: each live section's buttons, where each comes
    from and its fixed regions, every function's messages, the system messages and the user's
    changes."""
    from . import layout

    registry = registry or _get()
    overlay = getattr(registry, "overlay", {})
    regions = _regions()
    sections = []
    for live in layout.SECTIONS:
        name = live._name
        key = name.replace("-", "_")
        modes = section_modes(name)
        own = []
        for id, item in registry.items.items():
            if item["section"] != name:
                continue
            short = id[len(key) + 1 :]
            entry = {
                "id": id,
                "name": short,
                "function": _does(id, item),
                "pad": list(item["pad"]),
                "label": registry.label(_does(id, item), name, _freeze(item.get("value"))),
                "source": "user" if short in overlay.get(key, {}) else "shipped",
            }
            if "label" in item:
                entry["own_label"] = item["label"]
            if "value" in item:
                entry["value"] = item["value"]
            own.append(entry)
        taken = {tuple(entry["pad"]) for entry in own}
        inherited = []
        if name in FALLBACK:
            for id, pad in _live(registry.items, FALLBACK[name]):
                item = registry.items[id]
                if pad not in taken and MODES[_does(id, item)] & modes:
                    entry = {
                        "id": id,
                        "function": _does(id, item),
                        "pad": list(pad),
                        "label": registry.label(_does(id, item), item["section"], _freeze(item.get("value"))),
                        "source": "inherited",
                        "from": item["section"],
                    }
                    if "value" in item:
                        entry["value"] = item["value"]
                    inherited.append(entry)
        sections.append(
            {
                "name": name,
                "key": key,
                "modes": sorted(modes),
                "fallback": FALLBACK.get(name),
                "left_split": name in LEFT_SPLIT_SECTIONS,
                "entries": own + inherited,
                "regions": _pads(regions.get(name, ())),
                # Fixed or taken in a layer this section shares: a button can't go there.
                "locked": sorted(
                    {
                        tuple(pad)
                        for other in _neighbours(name)
                        for pad in _pads(regions.get(other, ()))
                    }
                    | {tuple(pad) for pad in _pads(regions.get(name, ()))}
                ),
                "others": [
                    {"id": id, "section": other, "pad": list(pad)}
                    for other in _neighbours(name)
                    for id, pad in _live(registry.items, other)
                    if registry.items[id]["section"] == other
                ],
                "functions": sorted(function for function, runs in MODES.items() if runs & modes),
            }
        )
    functions = {}
    for name in sorted(set(MODES) | set(registry.functions)):
        item = registry.function(name)
        described = {key: item[key] for key in userfile.FUNCTION_FIELDS if key in item}
        described.setdefault("label", name)
        functions[name] = described
    system = dict(registry.data.get("system", {}))
    return {
        "sections": sections,
        "layers": {layer: list(names) for layer, names in LAYERS.items()},
        "functions": functions,
        "system": system,
        "fixed_groups": sorted(userfile.FIXED_GROUPS),
        "open_groups": sorted(userfile.OPEN_GROUPS),
        "max_label": MAX_LABEL,
        "overlay": overlay,
        "shipped": _shipped(),
        "editor": getattr(registry, "editor", dict(userfile.EDITOR)),
        "shipped_path": str(PATH),
        "user_path": None if USER_PATH is None else str(USER_PATH),
    }


def _shipped():
    # The shipped file alone, by section key, for the editor to lay the user's changes over,
    # with the placeholders each of its messages may use.
    data = _read(PATH)
    sections = {
        key: [{"name": name, **item} for name, item in table.items()]
        for key, table in data.items()
        if key not in TOP_LEVEL
    }
    functions, placeholders = {}, {}
    for name, item in data.get("functions", {}).items():
        functions[name] = {key: value for key, value in item.items() if key in userfile.FUNCTION_FIELDS}
        allowed = {}
        if "message" in item:
            allowed["message"] = sorted(userfile.placeholders(item["message"]))
        for table in ("outcomes", "refusals"):
            if table in item:
                allowed[table] = {key: sorted(userfile.placeholders(text)) for key, text in item[table].items()}
        placeholders[name] = allowed
    system = data.get("system", {})
    return {
        "sections": sections,
        "functions": functions,
        "placeholders": placeholders,
        "system": system,
        "system_placeholders": {key: sorted(userfile.placeholders(text)) for key, text in system.items()},
    }


def editor_settings():
    return dict(_get().editor)


def entry(id):
    return _get().entry(id)


def entries():
    return _get().entries()


def function(name):
    return _get().function(name)


def pos(id):
    return _get().pos(id)


def label(name, section, value=None):
    return _get().label(name, section, value)


def manual(name, section, label):
    return _get().manual(name, section, label)


def group(section, function):
    return _get().group(section, function)


def section(name, base=None):
    return _get().section(name, base)


def say(name, outcome=None, /, **values):
    return _get().say(name, outcome, **values)


def refuse(name, key, /, **values):
    return _get().refuse(name, key, **values)


def system(key, /, **values):
    return _get().system(key, **values)


def systems():
    # Every [system] message, unformatted.
    return dict(_get().data.get("system", {}))
