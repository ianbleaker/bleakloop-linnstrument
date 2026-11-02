"""Linnstrument Mode: the surface is the player's instrument, except the Global column."""

from . import global_column, layout
from .model import PadPress


def handle(state, event, snapshot):
    if not isinstance(event, PadPress) or event.column != layout.GLOBAL_COLUMN:
        return state, []
    return global_column.handle(state, event, snapshot)


def render(state, snapshot):
    # The Global column only: the rest of the surface is the instrument.
    return global_column.render(state, snapshot)
