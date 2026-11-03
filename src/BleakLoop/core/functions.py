"""The functions a button can run, by name and mode: what a press does and how its pad lights.

Each feature module registers its own functions; catalogue.MODES says which modes each runs
in. A button's section (buttons.toml) picks the function, so any function can sit on any pad
of a mode it runs in.
"""

from dataclasses import dataclass

from .catalogue import LINNSTRUMENT, MODES, SEQUENCER, SESSION
from .leds import OFF, Light
from .modes import Mode


@dataclass(frozen=True)
class Function:
    press: object  # (state, snapshot, value) -> (state, actions); None for a hold
    light: object  # (state, snapshot, value) -> Light


# Holds: pressed and released, in an order each mode's handle() keeps itself. A mode may run
# one as a tap instead (Sequencer Mode's Seq leaves it), registering its press.
HOLDS = frozenset({"shift", "device_clip", "seq", "copy", "delete", "stop", "bars"})


_FUNCTIONS = {}  # (name, mode) -> Function

MODE_NAMES = {Mode.SESSION: SESSION, Mode.LINNSTRUMENT: LINNSTRUMENT, Mode.SEQUENCER: SEQUENCER}


def register(name, modes=None, light=None):
    # A decorator: the press handler for a function in some of its modes (all, by default).
    modes = MODES[name] if modes is None else frozenset(modes)
    if not modes <= MODES[name]:
        raise ValueError(f"{name} doesn't run in {sorted(modes - MODES[name])}")

    def add(press):
        if press is None and name not in HOLDS:
            raise ValueError(f"{name}: only a hold registers without a press")
        for mode in modes:
            if (name, mode) in _FUNCTIONS:
                raise ValueError(f"{name} is registered twice in {mode}")
            _FUNCTIONS[name, mode] = Function(press, light or _dark)
        return press

    return add


def register_hold(name, modes=None, light=None):
    register(name, modes, light)(None)


def _dark(state, snapshot, value):
    return Light(OFF)


def get(name, state):
    return _FUNCTIONS.get((name, MODE_NAMES[state.mode]))


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


def registered():
    return set(_FUNCTIONS)
