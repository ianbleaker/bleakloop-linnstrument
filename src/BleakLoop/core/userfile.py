"""The user's buttons file: changes over the shipped buttons.toml, kept outside the script folder
so an upgrade keeps them. It lists only what differs; anything it leaves out comes from the
shipped file."""

import copy
import string

# A group's buttons are read by index or hold fixed settings: they may move and be relabelled,
# never be added, removed or given another value.
FIXED_GROUPS = frozenset({"slots", "scene_slots", "pages", "bars", "rates", "tracks", "devices"})
# A group the user may add to, remove from and give new values.
OPEN_GROUPS = frozenset({"tempo", "window"})

BUTTON_FIELDS = frozenset({"pad", "does", "value", "label", "removed"})
FUNCTION_FIELDS = frozenset({"label", "message", "show", "outcomes", "refusals"})
EDITOR = {"enabled": True, "port": 47128}


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


def _check_value(id, function, value):
    if function == "tempo" and not (_is_int(value) and value != 0):
        raise ValueError(f"{id}: a tempo step is a whole number other than 0")
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
                raise ValueError(f"{id}: only tempo and window buttons take a value")
            section[name] = new


def _merge_functions(merged, shipped, user):
    if not isinstance(user, dict):
        raise ValueError("functions: not a table")
    for name, item in user.items():
        where = f"functions.{name}"
        if not isinstance(item, dict):
            raise ValueError(f"{where}: not a table")
        unknown = set(item) - FUNCTION_FIELDS
        if unknown:
            field = sorted(unknown)[0]
            if field in ("manual", "manual_in"):
                raise ValueError(f"{where}: {field} feeds the repo's manual and can't be changed here")
            raise ValueError(f"{where}: unknown field {field!r}")
        old = shipped.get(name, {})
        new = merged.setdefault(name, {})
        for field, value in item.items():
            if field == "message":
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
                raise ValueError("manual_format feeds the repo's manual and can't be changed here")
            elif not isinstance(value, dict):
                raise ValueError(f"{key}: not allowed in the user file")
        sections = {key: value for key, value in user.items() if key not in ("editor", "functions", "system")}
        shipped_sections = {
            key: value for key, value in shipped.items() if key not in ("manual_format", "functions", "system")
        }
        _merge_buttons(merged, shipped_sections, sections)
    except ValueError as error:
        raise ValueError(f"{name}: {error}") from None
    return merged, editor
