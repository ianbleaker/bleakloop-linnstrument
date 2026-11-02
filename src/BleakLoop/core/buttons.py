"""Button registry: position, label, manual text and messages per button, from buttons.toml."""

import tomllib
from pathlib import Path

PATH = Path(__file__).parent.parent / "buttons.toml"


class Registry:
    def __init__(self, data):
        self.data = data
        self.items = dict(_walk(data))

    def entry(self, id):
        return self.items[id]

    def entries(self):
        return dict(self.items)

    def pos(self, id):
        column, pad = self.entry(id)["pad"]
        return (column, pad)

    def group(self, id):
        return {self.pos(key): item["value"] for key, item in self.items.items() if item.get("group") == id}


def _walk(table, prefix=""):
    # An entry is a table with a section; anything else nests further IDs.
    for key, value in table.items():
        if not isinstance(value, dict) or key == "system":
            continue
        id = f"{prefix}{key}"
        if "section" in value:
            yield id, value
        else:
            yield from _walk(value, f"{id}.")


def load(path):
    with open(path, "rb") as file:
        return Registry(tomllib.load(file))


_registry = load(PATH)


def entry(id):
    return _registry.entry(id)


def entries():
    return _registry.entries()


def pos(id):
    return _registry.pos(id)


def group(id):
    return _registry.group(id)
