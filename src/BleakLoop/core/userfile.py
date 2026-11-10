"""The user's buttons file: changes over the shipped buttons.toml, kept outside the script folder
so an upgrade keeps them. It lists only what differs; anything it leaves out comes from the
shipped file."""

import copy
import os
import string
from pathlib import Path

from .catalogue import REQUIREMENTS, met_in

# A group's buttons are read by index or hold fixed settings: they may move and be relabelled,
# never be added, removed or given another value.
FIXED_GROUPS = frozenset({"slots", "banks", "scene_slots", "pages", "bars", "rates"})
# A group the user may add to, remove from and give new values.
OPEN_GROUPS = frozenset({"tempo", "window", "tracks", "devices"})

BUTTON_FIELDS = frozenset({"pad", "does", "value", "label", "removed", "options"})
FUNCTION_FIELDS = frozenset({"label", "message", "show", "outcomes", "refusals"})
# Fields that only feed the repo's generated docs: a user file may repeat them unchanged.
DOCS_FIELDS = frozenset({"manual", "manual_in"})
EDITOR = {"enabled": True, "port": 47128}
# Top-level keys that aren't button sections.
RESERVED = ("editor", "functions", "system", "manual_format", "format")
# The user file's format: 2 since sections stopped falling back to Session Mode's. A file
# without it was written for format 1, and convert_v1 converts it.
FORMAT = 2


def _is_int(value):
    return isinstance(value, int) and not isinstance(value, bool)


def _does(id, item):
    return item.get("does", id.rsplit(".", 1)[1])


def placeholders(template):
    # The names a message template fills, as {name}, {name.attr} or {name[0]} all fill name.
    names = set()
    for _, field, _, _ in string.Formatter().parse(template):
        if field is not None:
            names.add(field.split(".", 1)[0].split("[", 1)[0])
    return names


def _check_template(where, template, shipped):
    if not isinstance(template, str):
        raise ValueError(f"{where}: must be a string")
    try:
        names = placeholders(template)
    except ValueError as error:
        raise ValueError(f"{where}: {error}") from None
    extra = names - placeholders(shipped)
    if extra:
        allowed = ", ".join(f"{{{name}}}" for name in sorted(placeholders(shipped))) or "none"
        unknown = ", ".join(f"{{{name}}}" for name in sorted(extra))
        raise ValueError(f"{where}: unknown placeholder {unknown}; it may use {allowed}")


_STEP_NAMES = {"tempo": "tempo", "tracks": "track", "devices": "device"}


def _check_value(id, function, value):
    if function in ("tempo", "tracks", "devices") and not (_is_int(value) and value != 0):
        raise ValueError(f"{id}: a {_STEP_NAMES[function]} step is a whole number other than 0")
    if function == "window" and not (
        isinstance(value, list) and len(value) == 2 and all(map(_is_int, value)) and any(value)
    ):
        raise ValueError(f"{id}: a window step is [tracks, scenes], not both 0")


def _merge_buttons(merged, shipped, user):
    for key, table in user.items():
        if key not in shipped:
            # A section the shipped file has no buttons in; Registry checks its name.
            merged[key] = {}
        if not isinstance(table, dict) or not all(isinstance(item, dict) for item in table.values()):
            raise ValueError(f"{key}: a section holds button tables, as [{key}.<name>]")
        section = merged[key]
        for name, item in table.items():
            id = f"{key}.{name}"
            unknown = set(item) - BUTTON_FIELDS
            if unknown:
                raise ValueError(f"{id}: unknown field {sorted(unknown)[0]!r}")
            old = shipped.get(key, {}).get(name)
            if "removed" in item:
                if item["removed"] is not True or len(item) > 1:
                    raise ValueError(f"{id}: removed = true stands alone")
                if old is None:
                    raise ValueError(f"{id}: no such button in the shipped file to remove")
                if _does(id, old) in FIXED_GROUPS:
                    raise ValueError(f"{id}: {_does(id, old)} buttons can't be removed")
                del section[name]
                continue
            if old is None:
                if "pad" not in item:
                    raise ValueError(f"{id}: a new button needs a pad")
                new = dict(item)
            else:
                new = {**old, **item}
            function, was = _does(id, new), old and _does(id, old)
            if was in FIXED_GROUPS and function != was:
                raise ValueError(f"{id}: {was} buttons can't run another function")
            if function in FIXED_GROUPS:
                if was != function:
                    raise ValueError(f"{id}: {function} buttons can't be added")
                if new.get("value") != old.get("value"):
                    raise ValueError(f"{id}: {function} values can't change")
            elif function in OPEN_GROUPS:
                if "value" not in new:
                    raise ValueError(f"{id}: a {function} button needs a value")
                _check_value(id, function, new["value"])
            elif "value" in new:
                if was in OPEN_GROUPS:
                    raise ValueError(f"{id}: remove it and add a new button to run {function}")
                raise ValueError(f"{id}: only tempo, window, track and device buttons take a value")
            section[name] = new


def _merge_functions(merged, shipped, user):
    if not isinstance(user, dict):
        raise ValueError("functions: not a table")
    for name, item in user.items():
        where = f"functions.{name}"
        if not isinstance(item, dict):
            raise ValueError(f"{where}: not a table")
        old = shipped.get(name, {})
        unknown = set(item) - FUNCTION_FIELDS - DOCS_FIELDS
        if unknown:
            raise ValueError(f"{where}: unknown field {sorted(unknown)[0]!r}")
        new = merged.setdefault(name, {})
        for field, value in item.items():
            if field in DOCS_FIELDS:
                # A copy of the shipped file carries them unchanged; a change would do nothing.
                if field not in old or value != old[field]:
                    raise ValueError(f"{where}: {field} feeds the repo's manual and can't be changed here")
            elif field == "message":
                if "message" not in old:
                    raise ValueError(f"{where}: has no message to change")
                _check_template(f"{where}.message", value, old["message"])
                new[field] = value
            elif field in ("outcomes", "refusals"):
                if not isinstance(value, dict):
                    raise ValueError(f"{where}.{field}: not a table")
                for key, text in value.items():
                    if key not in old.get(field, {}):
                        raise ValueError(f"{where}.{field}: no such message {key!r}")
                    _check_template(f"{where}.{field}.{key}", text, old[field][key])
                new[field] = {**old.get(field, {}), **value}
            else:
                new[field] = value


def _merge_system(merged, shipped, user):
    if not isinstance(user, dict):
        raise ValueError("system: not a table")
    for key, text in user.items():
        if key not in shipped:
            raise ValueError(f"system: no such message {key!r}")
        _check_template(f"system.{key}", text, shipped[key])
        merged[key] = text


def _editor(table):
    if not isinstance(table, dict):
        raise ValueError("editor: not a table")
    unknown = set(table) - set(EDITOR)
    if unknown:
        raise ValueError(f"editor: unknown field {sorted(unknown)[0]!r}")
    if not isinstance(table.get("enabled", True), bool):
        raise ValueError("editor: enabled is true or false")
    port = table.get("port", EDITOR["port"])
    if not (_is_int(port) and 1024 <= port <= 65535):
        raise ValueError("editor: port is a whole number from 1024 to 65535")
    return {**EDITOR, **table}


def merge(shipped, user, name="user buttons file"):
    """(merged, editor settings): the shipped file's data with the user's changes over it.
    Raises ValueError naming the user file. Registry checks the result as for the shipped file."""
    try:
        merged = copy.deepcopy(shipped)
        editor = dict(EDITOR)
        for key, value in user.items():
            if key == "editor":
                editor = _editor(value)
            elif key == "functions":
                _merge_functions(merged.setdefault("functions", {}), shipped.get("functions", {}), value)
            elif key == "system":
                _merge_system(merged.setdefault("system", {}), shipped.get("system", {}), value)
            elif key == "manual_format":
                if value != shipped.get("manual_format"):
                    raise ValueError("manual_format feeds the repo's manual and can't be changed here")
            elif key == "format":
                if value != FORMAT:
                    raise ValueError(f"format: {value!r} isn't a format BleakLoop reads; it reads {FORMAT}")
            elif not isinstance(value, dict):
                raise ValueError(f"{key}: not allowed in the user file")
        sections = {key: value for key, value in user.items() if key not in RESERVED}
        shipped_sections = {key: value for key, value in shipped.items() if key not in RESERVED}
        _merge_buttons(merged, shipped_sections, sections)
    except ValueError as error:
        raise ValueError(f"{name}: {error}") from None
    return merged, editor


HEADER = """\
# BleakLoop's user buttons: your changes over the shipped buttons.toml. Anything not listed
# here comes from the shipped file; delete this file to go back to it. BleakLoop applies a
# save within about a second. The editor at http://127.0.0.1:<port> rewrites this whole file
# on every save, so comments added here by hand are lost.
"""

_BARE = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-")


def _key(name):
    if name and set(name) <= _BARE:
        return name
    return _string(name)


def _string(text):
    out = []
    for char in text:
        if char == '"':
            out.append('\\"')
        elif char == "\\":
            out.append("\\\\")
        elif char == "\n":
            out.append("\\n")
        elif char == "\t":
            out.append("\\t")
        elif char == "\r":
            out.append("\\r")
        elif ord(char) < 0x20 or ord(char) == 0x7F:
            out.append(f"\\u{ord(char):04x}")
        else:
            out.append(char)
    return '"' + "".join(out) + '"'


def _value(value):
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            raise ValueError("numbers must be finite")
        return repr(value)
    if isinstance(value, str):
        return _string(value)
    if isinstance(value, list):
        return "[" + ", ".join(_value(part) for part in value) + "]"
    raise ValueError(f"can't write {type(value).__name__} values")


def _table(lines, name, table):
    # A table's plain values, then its nested tables as [name.key].
    lines.append(f"[{name}]")
    nested = []
    for key, value in table.items():
        if isinstance(value, dict):
            nested.append((key, value))
        else:
            lines.append(f"{_key(key)} = {_value(value)}")
    for key, value in nested:
        _table(lines, f"{name}.{_key(key)}", value)


def prune(value):
    # Drops empty tables, which TOML can't keep apart from missing ones.
    if not isinstance(value, dict):
        return value
    pruned = {key: prune(part) for key, part in value.items()}
    return {key: part for key, part in pruned.items() if part != {}}


def to_toml(overlay):
    """The user file's text for an overlay: editor, system, functions, then the buttons."""
    lines = [HEADER.rstrip("\n")]
    if "format" in overlay:
        lines += ["", f"format = {_value(overlay['format'])}"]
    order = [key for key in ("editor", "system", "functions") if key in overlay]
    order += [key for key in overlay if key not in ("editor", "system", "functions", "format")]
    for key in order:
        value = overlay[key]
        if not isinstance(value, dict):
            raise ValueError(f"{key}: not allowed in the user file")
        if key in ("editor", "system"):
            lines.append("")
            _table(lines, _key(key), value)
            continue
        for name, item in value.items():
            if not isinstance(item, dict):
                raise ValueError(f"{key}.{name}: not a table")
            lines.append("")
            _table(lines, f"{_key(key)}.{_key(name)}", item)
    return "\n".join(lines) + "\n"


def write_atomic(path, text):
    # A temporary file in the same folder, then a rename: a reader sees the old file or the
    # new one, never half of one.
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        with open(temporary, "w", encoding="utf-8") as file:
            file.write(text)
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


# Format 1: these sections fell back to their base, by its key, in the mode they show in. A
# base's button on a pad the section didn't use worked there too, if it ran in that mode.
_V1_FALLBACK = {
    "linnstrument": ("global", "LINNSTRUMENT"),
    "linnstrument_shift": ("global_shift", "LINNSTRUMENT"),
    "sequencer_global": ("global", "SEQUENCER"),
    "sequencer_global_shift": ("global_shift", "SEQUENCER"),
    "sequencer_nav": ("navigation", "SEQUENCER"),
    "sequencer_nav_shift": ("navigation_shift", "SEQUENCER"),
}
# Format 1 ran these in Session and Sequencer Mode only; they now run everywhere.
_V1_SESSION_AND_SEQUENCER = frozenset({"tracks", "devices", "device_clip", "window"})


def _v1_runs(function, mode):
    if function in _V1_SESSION_AND_SEQUENCER:
        return mode in ("SESSION", "SEQUENCER")
    return function in REQUIREMENTS and met_in(function, mode)


def _v1_live(merged, section, base, mode):
    # {name: item} for each button live in a format 1 section: its own, then its base's on the
    # pads it leaves free. A base's name the section already has gets a number.
    live = dict(merged.get(section, {}))
    taken = {tuple(item["pad"]) for item in live.values()}
    for name, item in merged.get(base, {}).items():
        if tuple(item["pad"]) in taken or not _v1_runs(_does(f"{base}.{name}", item), mode):
            continue
        live[_free(name, live)] = dict(item)
    return live


def _free(name, *taken):
    # name, or name_2, name_3, ...: the first that none of the tables has.
    candidate, n = name, 1
    while any(candidate in table for table in taken):
        n += 1
        candidate = f"{name}_{n}"
    return candidate


def _layout(section, items):
    # What a section's buttons do, whatever their names: (pad, function, value, label) each.
    def key(name, item):
        value = item.get("value")
        return (tuple(item["pad"]), _does(f"{section}.{name}", item), repr(value), item.get("label"))

    return sorted(key(name, item) for name, item in items.items())


def _section_overlay(section, shipped, wanted):
    # The user entries that turn the shipped section into wanted. A shipped button wanted as
    # something else, or without a field it has, is removed and wanted under a new name.
    out, extra = {}, {}
    for name, item in shipped.items():
        want = wanted.get(name)
        if want is None:
            out[name] = {"removed": True}
            continue
        same_function = _does(f"{section}.{name}", want) == _does(f"{section}.{name}", item)
        if not same_function or set(item) - set(want):
            out[name] = {"removed": True}
            extra[name] = want
            continue
        changes = {field: value for field, value in want.items() if item.get(field) != value}
        if changes:
            out[name] = changes
    for name, want in wanted.items():
        if name not in shipped:
            out[name] = dict(want)
    for name, want in extra.items():
        out[_free(name, shipped, wanted, out)] = dict(want)
    return out


def convert_v1(shipped, v1, user, name="user buttons file"):
    """The user file converted to format 2, or None when it needs nothing: written for format
    1 (no format key), its buttons over v1 (the frozen format 1 shipped file) gave each former
    fallback section a layout, and the converted file gives each the same over shipped. Raises
    ValueError naming the file when it can't be converted."""
    if "format" in user or not any(key not in RESERVED for key in user):
        return None
    try:
        old, _ = merge(v1, user, name)
    except ValueError:
        return None  # not written for format 1: read as it is
    new, _ = merge(shipped, user, name)
    out = copy.deepcopy(user)
    changed = False
    for section, (base, mode) in _V1_FALLBACK.items():
        wanted = _v1_live(old, section, base, mode)
        if _layout(section, wanted) == _layout(section, new.get(section, {})):
            continue
        changed = True
        out[section] = _section_overlay(section, shipped.get(section, {}), wanted)
        if not out[section]:
            del out[section]
    if not changed:
        return None
    out["format"] = FORMAT
    converted, _ = merge(shipped, out, name)
    for section, (base, mode) in _V1_FALLBACK.items():
        wanted = _v1_live(old, section, base, mode)
        if _layout(section, wanted) != _layout(section, converted.get(section, {})):
            raise ValueError(f"{name}: converting it from format 1, {section} couldn't keep its buttons")
    return out
