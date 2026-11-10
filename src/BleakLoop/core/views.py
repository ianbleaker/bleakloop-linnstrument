"""The views: what each mode shows, by section, and how its holds layer over it. Data only.

A view is a mode and its sub-state (Mixer, FX, a split view, Sequencer Mode's settings). Its
sections are the button sections live in it, in lookup order; its grid is the section that
holds its fixed regions and the manual's text for them. A hold layer, while its hold is down,
replaces some of the view's sections with its own: their buttons go dark and the layer's light
in their place. Section names are the buttons.toml keys, with hyphens for underscores.

Imports nothing from the core at module level: buttons and layout import this module.
"""

from dataclasses import dataclass, field

# Surface geometry, as layout gives it (tests/test_views.py keeps the two equal).
ROWS = range(1, 9)
COLUMNS = range(1, 17)
GLOBAL_COLUMN = range(1, 2)
GRID_COLUMNS = range(2, 15)
SCENE_COLUMN = range(15, 16)
SCENES = range(1, 7)
SPLIT_TRACK_COLUMNS = range(2, 10)
SPLIT_FADER_COLUMNS = range(10, 15)
FX_FADER_COLUMNS = range(2, 10)
SEQ_STEP_COLUMNS = range(3, 11)
SEQ_NOTE_COLUMNS = range(11, 15)

_GRID = ((GRID_COLUMNS, ROWS),)
_SPLIT_TRACKS = ((SPLIT_TRACK_COLUMNS, ROWS),)
_SPLIT = (*_SPLIT_TRACKS, (SPLIT_FADER_COLUMNS, ROWS))
_STEPS = ((SEQ_STEP_COLUMNS, ROWS),)
_SEQUENCER = (*_STEPS, (SEQ_NOTE_COLUMNS, ROWS))
_SCENES = ((SCENE_COLUMN, SCENES),)

# Each section's fixed regions (clip grid, scene pads, faders, steps): no button may sit on
# them, as (columns, pads) ranges.
REGIONS = {
    "view": _SCENES,
    "view-shift": _SCENES,
    "session": _GRID,
    "session-shift": _GRID,
    "split": _SPLIT,
    "split-shift": _SPLIT_TRACKS,
    "split-snapshots": _SPLIT_TRACKS,
    "mixer": _GRID,
    "mixer-shift": _GRID,
    "mixer-split": _SPLIT,
    "mixer-split-shift": _SPLIT_TRACKS,
    "fx": ((FX_FADER_COLUMNS, ROWS),),
    "linnstrument-scenes": ((GLOBAL_COLUMN, SCENES),),
    "sequencer-grid": _STEPS,
    "sequencer": _SEQUENCER,
    "sequencer-functions": _SEQUENCER,
    "sequencer-settings": _STEPS,
}


@dataclass(frozen=True)
class Layer:
    """A hold's layer: its sections take the place of the ones it replaces, at the first of
    them, and grid, when set, replaces the view's grid."""

    sections: tuple
    replaces: tuple
    grid: str | None = None


@dataclass(frozen=True)
class View:
    name: str
    mode: str  # the modes.Mode member's name
    sections: tuple  # the button sections live in it, in lookup order
    grid: str | None = None  # the section of its fixed regions, with no buttons of its own
    # The sections whose presses the mode's own code takes (FX Mode's slots, the settings).
    own: tuple = ()
    columns: range = COLUMNS  # the columns that reach BleakLoop
    # The hold layers, by the hold's function name; applied in this order.
    layers: dict = field(default_factory=dict)
    # The sections that keep working while Copy or Delete is held.
    copy_delete: tuple = ()
    # The manual's pad maps of this view: map name -> the holds down in it.
    maps: dict = field(default_factory=dict)


_SHIFT = ("global-shift", "view-shift", "navigation-shift")
_SESSION = ("global", "view", "navigation")
_DEVICE_CLIP = Layer(("device-clip",), ("navigation", "navigation-shift"))


def _session(name, grid, shift_grid, maps, sections=_SESSION, own=()):
    return View(
        name,
        "SESSION",
        sections,
        grid,
        own=own,
        layers={"shift": Layer(_SHIFT, _SESSION, shift_grid), "device_clip": _DEVICE_CLIP},
        maps=maps,
    )


_SEQUENCER_LAYERS = {
    "shift": Layer(("sequencer-global-shift", "sequencer-nav-shift"), ("sequencer-global", "sequencer-nav")),
    "device_clip": Layer(("device-clip",), ("sequencer-nav", "sequencer-nav-shift")),
    "scene_page": Layer(("linnstrument-scenes",), ("sequencer-global", "sequencer-global-shift")),
}
_SEQUENCER_NAV = ("sequencer-nav", "sequencer-nav-shift")

VIEWS = (
    _session("session", "session", "session-shift", {"SESSION": (), "SESSION_SHIFT": ("shift",)}),
    _session("split", "split", "split-shift", {"SPLIT": ()}),
    _session("split-snapshots", "split-snapshots", "split-shift", {"SPLIT_SNAPSHOTS": ()}),
    _session("mixer", "mixer", "mixer-shift", {"MIXER": (), "MIXER_SHIFT": ("shift",)}),
    _session("mixer-split", "mixer-split", "mixer-split-shift", {"MIXER_SPLIT": ()}),
    _session("fx", None, None, {"FX": (), "FX_SHIFT": ("shift",)}, (*_SESSION, "fx"), ("fx",)),
    View(
        "sequencer",
        "SEQUENCER",
        ("sequencer-global", "sequencer-nav", "sequencer-grid"),
        "sequencer",
        layers=_SEQUENCER_LAYERS,
        copy_delete=_SEQUENCER_NAV,
        maps={"SEQUENCER": (), "SEQUENCER_DRUMS": (), "SEQUENCER_SHIFT": ("shift",)},
    ),
    View(
        "sequencer-settings",
        "SEQUENCER",
        ("sequencer-global", "sequencer-nav", "sequencer-grid", "sequencer-settings"),
        own=("sequencer-settings",),
        layers=_SEQUENCER_LAYERS,
        copy_delete=_SEQUENCER_NAV,
        maps={"SEQUENCER_SETTINGS": ()},
    ),
    View(
        "linnstrument",
        "LINNSTRUMENT",
        ("linnstrument",),
        columns=GLOBAL_COLUMN,
        layers={
            "shift": Layer(("linnstrument-shift",), ("linnstrument",)),
            "scene_page": Layer(("linnstrument-scenes",), ("linnstrument", "linnstrument-shift")),
        },
    ),
)

BY_NAME = {view.name: view for view in VIEWS}


def view_of(state):
    # The view state shows. Mixer Mode's split snapshots show Mixer's split view's buttons.
    mode = state.mode.name
    if mode == "LINNSTRUMENT":
        return BY_NAME["linnstrument"]
    if mode == "SEQUENCER":
        return BY_NAME["sequencer-settings" if state.seq_settings else "sequencer"]
    if state.fx:
        return BY_NAME["fx"]
    if state.mixer:
        return BY_NAME["mixer-split" if state.mixer_split else "mixer"]
    if state.split:
        return BY_NAME["split-snapshots" if state.split_snapshots else "split"]
    return BY_NAME["session"]


def apply(sections, layer):
    # The sections with a layer over them.
    out, placed = [], False
    for section in sections:
        if section not in layer.replaces:
            out.append(section)
        elif not placed:
            out.extend(layer.sections)
            placed = True
    return tuple(out)


def live(view, held=()):
    # The view's button sections with the held layers over it, in lookup order.
    sections = view.sections
    for name, layer in view.layers.items():
        if name in held:
            sections = apply(sections, layer)
    return sections


def grid(view, held=()):
    out = view.grid
    for name, layer in view.layers.items():
        if name in held and layer.grid is not None:
            out = layer.grid
    return out


def layer_sections(view, held=()):
    # Everything live together: the buttons, then the grid.
    out = live(view, held)
    section = grid(view, held)
    return out if section is None else (*out, section)


# Held states whose sections live together: each one's buttons share no pad and sit on none of
# its fixed regions.
CHECKED = ((), ("shift",), ("device_clip",), ("shift", "device_clip"), ("scene_page",), ("shift", "scene_page"))


def layers():
    # {name: sections} for every view under every checked held state it has.
    out = {}
    for view in VIEWS:
        for held in CHECKED:
            if not set(held) <= set(view.layers):
                continue
            name = "_".join((view.name, *held)).replace("-", "_").upper()
            out[name] = layer_sections(view, held)
    return out


def maps():
    # {map name: sections} for the manual's pad maps.
    return {name: layer_sections(view, held) for view in VIEWS for name, held in view.maps.items()}


def button_sections():
    # Every section that holds buttons, in the views' order.
    out = []
    for view in VIEWS:
        for held in CHECKED:
            if set(held) <= set(view.layers):
                out += [section for section in live(view, held) if section not in out]
    return tuple(out)


def views_showing(section):
    return tuple(view for view in VIEWS if any(section in layer_sections(view, held) for held in CHECKED if set(held) <= set(view.layers)))


def modes(section):
    # The modes, by modes.Mode member name, whose views show a section.
    return frozenset(view.mode for view in views_showing(section))


def columns(section):
    # The columns a section's buttons may use: those every view showing it reaches.
    usable = set(COLUMNS)
    for view in views_showing(section):
        usable &= set(view.columns)
    return usable
