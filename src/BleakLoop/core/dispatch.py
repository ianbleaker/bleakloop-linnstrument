"""The buttons of the current view: which are live under the held layers, what a press on one
does, holds included, and how they light.

A view (core/views.py) lists its sections; a held hold's layer replaces some of them with its
own. Precedence, first match wins:
- a hold that takes every other press while it's held (Seq);
- a hold that never gives way (Shift);
- under the Shift layer, a press on a pad with a Shift layer button is that button's;
- a hold with a layer (Device/Clip), then that layer, which takes the pads it replaces;
- the other holds (Seq, Copy, Delete, Stop);
- the live layer's button. Copy and Delete hide the Shift layer, and while either is held only
  the view's copy_delete sections work.
"""

from . import functions, layout, views
from .leds import OFF, Light


def _sections(names, view):
    return [layout.section(name) for name in names if name not in view.own]


def _at(sections, key):
    # The button on a pad in the first section that has one, or None.
    for section in sections:
        button = section.at(key)
        if button is not None:
            return button
    return None


def _held(state):
    # {name: Hold} for each hold held now.
    return {name: hold for name, hold in functions.holds(state).items() if hold.down is not None and hold.down(state)}


def layers(state):
    # The layers shown over the view, in its order: those of the held holds, less any a held
    # hold hides.
    held = _held(state)
    hidden = {layer for hold in held.values() for layer in hold.hides}
    shown = {hold.layer for hold in held.values() if hold.layer is not None} - hidden
    return tuple(name for name in views.view_of(state).layers if name in shown)


def live_sections(state, held=None):
    # The view's live button sections, in lookup order, with the held layers over it.
    view = views.view_of(state)
    return _sections(views.live(view, layers(state) if held is None else held), view)


def button_at(state, key):
    # The button on a pad of the view with no layer over it, or None.
    return _at(live_sections(state, ()), key)


def held_pads(state, name):
    # The pads of a hold's buttons with no layer over the view.
    return {button.key for section in live_sections(state, ()) for button in section.buttons() if button.function == name}


def _layer_pads(view, layer):
    # The pads a layer takes: its own sections' and those it replaces.
    names = (*layer.sections, *layer.replaces)
    return {button.key for section in _sections(names, view) for button in section.buttons()}


def handle_button(state, event, snapshot):
    """A PadPress on a pad of the view's buttons, holds included: (state, actions), or None
    when no layer has a button there, for the mode's own code."""
    view = views.view_of(state)
    key = (event.column, event.pad)
    normal = button_at(state, key)
    hold = None if normal is None else functions.hold(normal.function, state)
    if event.pressed:
        for name, held in _held(state).items():
            if held.capture is not None and (normal is None or normal.function != name):
                return held.capture(state, event, snapshot)
    if hold is not None and not hold.yields:
        return hold.handle(state, event, snapshot)
    shown = layers(state)
    shift = view.layers.get("shift")
    shifted = (
        event.pressed and "shift" in shown and _at(_sections(shift.sections, view), key) is not None
    )
    if hold is not None and hold.layer is not None and not shifted:
        return hold.handle(state, event, snapshot)
    for held in _held(state).values():
        layer = view.layers.get(held.layer)
        if held.takes and layer is not None and event.pressed and key in _layer_pads(view, layer):
            button = _at(_sections(layer.sections, view), key)
            return (state, []) if button is None else functions.press(button, state, snapshot)
    if hold is not None and hold.handle is not None and not shifted:
        return hold.handle(state, event, snapshot)
    under = tuple(name for name in shown if name == "shift")
    if normal is None and _at(live_sections(state, ("shift",)), key) is None:
        return None
    if not event.pressed:
        return state, []
    sections = views.live(view, under)
    if state.copy or state.delete:
        sections = tuple(name for name in sections if name in view.copy_delete)
    button = _at(_sections(sections, view), key)
    return (state, []) if button is None else functions.press(button, state, snapshot)


def paint(frame, state, snapshot):
    # The view's buttons into frame, in place: every pad its layers use goes dark, then each
    # shown layer in turn darkens the pads of the sections it replaces and lights its own. A
    # held hold's pad keeps its light over its own layer, and over the other held holds' too
    # under one that shows them (Shift: a held Stop stays lit).
    view = views.view_of(state)
    every = set(view.sections).union(*((*layer.sections, *layer.replaces) for layer in view.layers.values()))
    for section in _sections(sorted(every), view):
        frame.update(dict.fromkeys((button.key for button in section.buttons()), Light(OFF)))
    base = live_sections(state, ())
    functions.paint(frame, (button for section in base for button in section.buttons()), state, snapshot)
    held = _held(state)
    for name in layers(state):
        layer = view.layers[name]
        frame.update(dict.fromkeys(_layer_pads(view, layer), Light(OFF)))
        functions.paint(frame, (b for s in _sections(layer.sections, view) for b in s.buttons()), state, snapshot)
        owner = [hold_name for hold_name, hold in held.items() if hold.layer == name]
        shows = any(held[hold_name].shows_holds for hold_name in owner)
        kept = set(held) if shows else set(owner)
        functions.paint(
            frame,
            (b for section in base for b in section.buttons() if b.function in kept),
            state,
            snapshot,
        )
