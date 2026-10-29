"""Chord Mode: hold quality and extension pads, then press a degree or piano key for a chord.

Live's Chord MIDI effect, inserted on the armed track, plays the chord: each chord pad is
translated to its chord's root, and the device's shifts build the rest around it. Track
indexes are song.tracks indexes.
"""

from . import column_1, layout
from .leds import OFF, Light
from .model import PadPress


def handle(state, event, snapshot):
    if not isinstance(event, PadPress):
        return state, []
    if event.column == 1:
        return column_1.handle(state, event, snapshot)
    return state, []


def sync(state, snapshot):
    # On every display tick in Chord Mode, and in Linnstrument Mode entered from it.
    return state, []


def render(state, snapshot):
    frame = {
        (column, pad): Light(OFF)
        for column in range(1, layout.COLUMNS)
        for pad in range(1, layout.ROWS + 1)
    }
    frame.update(column_1.render(state, snapshot))
    return frame
