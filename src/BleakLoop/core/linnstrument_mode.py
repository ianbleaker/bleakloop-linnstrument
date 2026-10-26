"""Linnstrument Mode: the surface is the player's instrument, except column 1."""

from . import column_1
from .model import PadPress


def handle(state, event, snapshot):
    if not isinstance(event, PadPress) or event.column != 1:
        return state, []
    return column_1.handle(state, event, snapshot)


def render(state, snapshot):
    # Column 1 only: the rest of the surface is the instrument.
    return column_1.render(state, snapshot)
