"""Adapter: carry out core actions on Live objects. No decisions."""

from .core.model import EnterMode, ToggleMetronome, TogglePlay


def apply(action, song, surface):
    if isinstance(action, ToggleMetronome):
        song.metronome = not song.metronome
    elif isinstance(action, TogglePlay):
        if song.is_playing:
            song.stop_playing()
        else:
            song.start_playing()
    elif isinstance(action, EnterMode):
        surface.enter_mode(action.mode)
    else:
        raise TypeError(f"unknown action: {action!r}")
