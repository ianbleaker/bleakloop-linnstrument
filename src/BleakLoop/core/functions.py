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
class Function:
    press: object  # (state, snapshot, value) -> (state, actions); None for a hold
    light: object  # (state, snapshot, value) -> Light


# Holds: pressed and released, in an order each mode's handle() keeps itself. A mode may run
# one as a tap instead (Sequencer Mode's Seq leaves it), through its press.
HOLDS = frozenset({"shift", "device_clip", "seq", "copy", "delete", "stop", "bars"})


_FUNCTIONS = {}  # name -> Function


def register(name, light=None):
    # A decorator: the function's press handler.
    if name not in REQUIREMENTS:
        raise ValueError(f"{name}: no such function in catalogue.REQUIREMENTS")

    def add(press):
        if press is None and name not in HOLDS:
            raise ValueError(f"{name}: only a hold registers without a press")
        if name in _FUNCTIONS:
            raise ValueError(f"{name} is registered twice")
        _FUNCTIONS[name] = Function(press, light or _dark)
        return press

    return add


def register_hold(name, light=None):
    register(name, light)(None)


def _dark(state, snapshot, value):
    return Light(OFF)


def get(name, state):
    # The function, or None where its requirement isn't met.
    if not requirement_met(name, state):
        return None
    return _FUNCTIONS.get(name)


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
