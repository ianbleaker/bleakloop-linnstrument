"""The functions a button can run, by name: what a press does and how its pad lights.

Each feature module registers its own functions, one handler per name, which branches on the
mode where the function does different things in different modes. catalogue.REQUIREMENTS says
what each needs: unmet, the function is dark and does nothing. A button's section
(buttons.toml) picks the function, so any function can sit on any pad.
"""

from dataclasses import dataclass

from .catalogue import REQUIREMENTS, requirement_met
from .leds import OFF, Light


@dataclass(frozen=True)
class Hold:
    """A function pressed and released, which core/dispatch.py runs in its precedence."""

    # (state, event, snapshot) -> (state, actions): its own pad's press and release. None
    # when a mode's own code runs it (Bars, in the snapshot panel).
    handle: object = None
    down: object = None  # state -> whether it's held
    layer: str | None = None  # the views.py layer it shows while held
    # While held, its layer takes every press on the pads of the sections it replaces.
    takes: bool = False
    # Under the Shift layer, its press gives way to a Shift layer button on its pad.
    yields: bool = True
    hides: tuple = ()  # the layers hidden while it's held (Copy and Delete hide Shift's)
    # While held, the pads of the other held holds keep their light over its layer.
    shows_holds: bool = False
    # (state, event, snapshot) -> (state, actions): every other press while it's held.
    capture: object = None


@dataclass(frozen=True)
class Function:
    press: object  # (state, snapshot, value) -> (state, actions); None for a hold
    light: object  # (state, snapshot, value) -> Light
    hold: Hold | None = None


_FUNCTIONS = {}  # name -> Function


def register(name, light=None, hold=None):
    # A decorator: the function's press handler, None for a hold.
    if name not in REQUIREMENTS:
        raise ValueError(f"{name}: no such function in catalogue.REQUIREMENTS")

    def add(press):
        if press is None and hold is None:
            raise ValueError(f"{name}: only a hold registers without a press")
        if name in _FUNCTIONS:
            raise ValueError(f"{name} is registered twice")
        _FUNCTIONS[name] = Function(press, light or _dark, hold)
        return press

    return add


def register_hold(name, light=None, **hold):
    register(name, light, Hold(**hold))(None)


def _dark(state, snapshot, value):
    return Light(OFF)


def get(name, state):
    # The function, or None where its requirement isn't met.
    if not requirement_met(name, state):
        return None
    return _FUNCTIONS.get(name)


def hold(name, state):
    # The function's Hold, or None: not a hold, or its requirement isn't met.
    function = get(name, state)
    return None if function is None else function.hold


def holds(state):
    # {name: Hold} for every hold whose requirement is met, in registration order.
    found = {name: get(name, state) for name in _FUNCTIONS}
    return {name: function.hold for name, function in found.items() if function and function.hold}


def press(button, state, snapshot):
    # A button is a buttons.Button, as buttons.Section lists it.
    function = get(button.function, state)
    if function is None or function.press is None:
        return state, []
    return function.press(state, snapshot, button.value)


def light(button, state, snapshot):
    function = get(button.function, state)
    if function is None:
        return Light(OFF)
    return function.light(state, snapshot, button.value)


def paint(frame, buttons, state, snapshot):
    # Lights each button's pad into frame, in place.
    for button in buttons:
        frame[button.key] = light(button, state, snapshot)


def registered():
    return set(_FUNCTIONS)
