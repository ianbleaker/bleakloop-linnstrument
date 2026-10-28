"""Horizontal FX faders: one per pad row, in FX Mode and the Session and Mixer split views."""

import json
from dataclasses import replace

from . import layout
from .leds import BLUE, MAGENTA, OFF, ORANGE, YELLOW, Light
from .model import (
    BeginUndoStep,
    BindFader,
    EndUndoStep,
    SaveFaderBindings,
    SetFaderParameter,
    ShowMessage,
)
from .modes import FaderBinding, FaderTouch, Mode
from .values import X_COLUMN_WIDTH

ROWS = 8

# (odd pad rows, even pad rows) per source: alternating rows can be counted at a glance.
COLOURS = {"device": (MAGENTA, BLUE), "mapped": (ORANGE, YELLOW)}


def visible(state):
    if state.mode is not Mode.SESSION:
        return False
    return state.fx or (split_view(state) and not state.split_snapshots)


def split_view(state):
    # Session or Mixer Mode's split view is on; FX Mode has none.
    return state.mixer_split if state.mixer else state.split and not state.fx


def columns(state):
    return layout.FX_FADER_COLUMNS if state.fx else layout.SPLIT_FADER_COLUMNS


def centre(column):
    return X_COLUMN_WIDTH * (column - 0.5)


def norm(x, first, last):
    # Jump to the finger: the end pads' centres are 0 and 1, so both ends are easy to reach.
    position = (x - centre(first)) / (centre(last) - centre(first))
    return min(max(position, 0.0), 1.0)


def value(touch, position):
    result = touch.min + position * (touch.max - touch.min)
    return float(_round(result)) if touch.is_quantized else result


def lit(position, count):
    # The first pad is always lit for a live fader.
    return 1 + _round(position * (count - 1))


def holds(state, event):
    # The event is on the cell a touch's finger is on, wherever it slid to.
    return any((t.column, t.pad) == (event.column, event.pad) for t in state.fader_touches)


def press(state, event, snapshot):
    # Every fader-column pad, releases included.
    touch = _find(state.fader_touches, event.pad)
    if not event.pressed:
        # Releases count under Shift too, so no touch latches.
        if touch is None or touch.column != event.column:
            return state, []
        state = replace(state, fader_touches=_without(state.fader_touches, event.pad))
        if state.fader_touches or not state.fader_undo_open:
            return state, []
        return replace(state, fader_undo_open=False), [EndUndoStep()]
    if not visible(state) or state.shift or state.stop or state.copy:
        return state, []
    mapped = state.fader_source == "mapped"
    row = event.pad - 1
    if state.device_clip:
        if not mapped:
            return state, [ShowMessage("Shift + FX for Mapped FX")]
        return state, [BindFader(row)]
    if state.delete:
        return _unbind(state, row) if mapped else (state, [])
    view = _view(snapshot, event.pad)
    if touch is not None:
        return state, []
    if view is None:
        if mapped and state.fader_bindings[row] is not None:
            return state, [ShowMessage(f"Fader {event.pad}: parameter not found")]
        return state, []
    span = columns(state)
    touch = FaderTouch(
        event.pad,
        event.column,
        span[0],
        span[-1],
        view.name,
        view.min,
        view.max,
        view.is_quantized,
        view.macro,
    )
    return replace(state, fader_touches=state.fader_touches + (touch,)), []


def bound(state, event):
    # The adapter's answer to BindFader: a binding to store and save, or a refusal.
    if event.binding is None:
        return state, [ShowMessage(event.message)]
    bindings = _put_row(state.fader_bindings, event.row, event.binding)
    state = replace(state, fader_bindings=bindings)
    return state, [SaveFaderBindings(dump(bindings)), ShowMessage(event.message)]


def dump(bindings):
    def row(binding):
        return {
            "track": binding.track,
            "tn": binding.tn,
            "device": binding.device,
            "dn": binding.dn,
            "param": binding.param,
            "name": binding.name,
        }

    data = [None if binding is None else row(binding) for binding in bindings]
    return json.dumps({"v": 1, "rows": data}, separators=(",", ":"))


def parse(text):
    # Anything unreadable gives empty rows: a bad store never stops the script loading.
    empty = (None,) * ROWS
    try:
        data = json.loads(text)
        if data.get("v") != 1 or len(data["rows"]) != ROWS:
            return empty
        return tuple(
            None
            if item is None
            else FaderBinding(
                str(item["track"]),
                int(item["tn"]),
                None if item["device"] is None else str(item["device"]),
                int(item["dn"]),
                int(item["param"]),
                str(item["name"]),
            )
            for item in data["rows"]
        )
    except (ValueError, TypeError, KeyError, AttributeError):
        return empty


def _unbind(state, row):
    if state.fader_bindings[row] is None:
        return state, []
    bindings = _put_row(state.fader_bindings, row, None)
    state = replace(state, fader_bindings=bindings)
    return state, [SaveFaderBindings(dump(bindings)), ShowMessage(f"Fader {row + 1} unbound")]


def _put_row(rows, row, value):
    return rows[:row] + (value,) + rows[row + 1 :]


def x_axis(state, event):
    # At the firmware's scan rate: no snapshot, and a redraw only when the lit count changes.
    touch = _find(state.fader_touches, event.pad)
    if touch is None or touch.column != event.column:
        return state, [], False
    position = norm(event.value, touch.first, touch.last)
    if position == touch.norm:
        return state, [], False
    actions = []
    if not state.fader_undo_open:
        # A morph's undo step closes first; the morph carries on.
        if state.fx_undo_open:
            state = replace(state, fx_undo_open=False)
            actions.append(EndUndoStep())
        state = replace(state, fader_undo_open=True)
        actions.append(BeginUndoStep())
    if touch.norm is None and touch.macro is not None:
        state = _leave_morph(state, touch.macro)
    actions.append(SetFaderParameter(event.pad - 1, touch.name, value(touch, position)))
    count = touch.last - touch.first + 1
    redraw = touch.norm is None or lit(position, count) != lit(touch.norm, count)
    state = _put(state, replace(touch, norm=position))
    return state, actions, redraw


def slide(state, event):
    # The touch follows its finger into any column; whether a fader owns the slide.
    touch = _find(state.fader_touches, event.pad)
    if touch is None or touch.column != event.from_column:
        return state, False
    return _put(state, replace(touch, column=event.to_column)), True


def reset(state):
    # The faders stop showing: drop the touches and close an open undo step.
    state = replace(state, fader_touches=())
    if not state.fader_undo_open:
        return state, []
    return replace(state, fader_undo_open=False), [EndUndoStep()]


def render(state, snapshot):
    # Dark under Shift, as Mixer's faders. The bar follows the parameter, or the finger
    # while a row is touched.
    span = columns(state)
    frame = {(column, pad): Light(OFF) for column in span for pad in range(1, layout.ROWS + 1)}
    if state.shift and not state.copy and not state.delete:
        return frame
    odd, even = COLOURS[state.fader_source]
    for pad in range(1, layout.ROWS + 1):
        touch = _find(state.fader_touches, pad)
        view = _view(snapshot, pad)
        if touch is not None and touch.norm is not None:
            position = touch.norm
        elif view is not None:
            span_value = view.max - view.min
            position = (view.value - view.min) / span_value if span_value else 0.0
        else:
            continue
        colour = odd if pad % 2 else even
        for column in span[: lit(position, len(span))]:
            frame[(column, pad)] = Light(colour)
    return frame


def _leave_morph(state, macro):
    # A fader on a morphing macro takes it out of the morph; the rest carry on.
    morph = state.morph
    if morph is None:
        return state
    path, rack_name, index = macro
    macros = tuple(
        m
        for m in morph.macros
        if (m.path, m.rack_name, m.index) != (path, rack_name, index)
    )
    return replace(state, morph=replace(morph, macros=macros))


def _view(snapshot, pad):
    return snapshot.faders[pad - 1] if pad <= len(snapshot.faders) else None


def _round(x):
    # Halves up, not to even.
    return int(x + 0.5) if x >= 0 else -int(-x + 0.5)


def _find(touches, pad):
    return next((touch for touch in touches if touch.pad == pad), None)


def _without(touches, pad):
    return tuple(touch for touch in touches if touch.pad != pad)


def _put(state, touch):
    return replace(state, fader_touches=_without(state.fader_touches, touch.pad) + (touch,))
