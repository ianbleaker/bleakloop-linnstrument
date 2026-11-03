"""Button positions named in the manual's prose, rendered from the button registry.

A placeholder is {<kind>:<ref>[,<ref>...]}, a ref <section>.<attr>: {pad:view.stop} renders
"column 15, pad 8". A group the wording can't describe raises, so whoever moves a shipped button
rewrites the sentence instead of the generator inventing one.
"""

import re

from BleakLoop.core import layout
from BleakLoop.core.buttons import Section

PLACEHOLDER = re.compile(r"\{([a-z]+):([a-z_.,0-9]+)\}")


def fill(text):
    return PLACEHOLDER.sub(_render, text)


def _render(match):
    kind, refs = match.group(1), match.group(2).split(",")
    render = KINDS.get(kind)
    if render is None:
        raise ValueError(f"{match.group(0)}: unknown kind {kind}")
    try:
        return render(*refs)
    except ValueError as error:
        raise ValueError(f"{match.group(0)}: {error}") from None


def pad(*refs):
    column_number, pads = _column(refs)
    return f"column {column_number}, {_pads(pads)}"


def row(*refs):
    return _pads(_column(refs)[1])


def column(*refs):
    return f"column {_one_column(_pooled(refs), refs)}"


def runs(ref):
    keys, numbered = _group(ref)
    if not numbered:
        raise ValueError(f"{ref} isn't a numbered group")
    parts, seen = [], set()
    number = 1
    for column_number, pads in _by_column(keys):
        if column_number in seen:
            raise ValueError(f"{ref} returns to column {column_number}")
        seen.add(column_number)
        if pads != list(range(pads[0], pads[0] + len(pads))):
            raise ValueError(f"{ref} isn't one ascending run in column {column_number}")
        parts.append(f"{_span(number, number + len(pads) - 1)} in column {column_number}")
        number += len(pads)
    return ", ".join(parts)


def section_column(section):
    # A heading's "Column N", when every button of the section is in one column.
    keys = [key for _, _, key, _ in section.buttons()]
    return f"Column {_one_column(keys, (section._name,))}"


KINDS = {"pad": pad, "row": row, "column": column, "runs": runs}


def _resolve(ref):
    return _group(ref)[0]


def _group(ref):
    # The ref's pads as a list of (column, pad), and whether they're a group in number order.
    section_name, _, attr = ref.partition(".")
    section = getattr(layout, section_name.upper(), None)
    if not isinstance(section, Section) or not attr:
        raise ValueError(f"unknown ref {ref}")
    try:
        value = getattr(section, attr)
    except AttributeError:
        raise ValueError(f"unknown ref {ref}") from None
    if isinstance(value, dict):
        return sorted(value), False
    if isinstance(value, tuple) and value and isinstance(value[0], tuple):
        return list(value), True
    if isinstance(value, tuple) and len(value) == 2 and all(isinstance(part, int) for part in value):
        return [value], False
    raise ValueError(f"{ref} isn't a button or a group")


def _pooled(refs):
    return [key for ref in refs for key in _resolve(ref)]


def _one_column(keys, refs):
    columns = {column_number for column_number, _ in keys}
    if len(columns) != 1:
        raise ValueError(f"{', '.join(refs)} span columns {sorted(columns)}")
    return columns.pop()


def _column(refs):
    keys = _pooled(refs)
    column_number = _one_column(keys, refs)
    pads = sorted(pad_number for _, pad_number in keys)
    if pads != list(range(pads[0], pads[0] + len(pads))):
        raise ValueError(f"{', '.join(refs)} aren't one run of pads: {pads}")
    return column_number, pads


def _pads(pads):
    return f"pad {pads[0]}" if len(pads) == 1 else f"pads {_span(pads[0], pads[-1])}"


def _span(first, last):
    return str(first) if first == last else f"{first}–{last}"


def _by_column(keys):
    # Consecutive keys grouped by column: [(column, [pad, ...]), ...].
    groups = []
    for column_number, pad_number in keys:
        if groups and groups[-1][0] == column_number:
            groups[-1][1].append(pad_number)
        else:
            groups.append((column_number, [pad_number]))
    return groups
