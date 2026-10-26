"""FX Mode: rack macro snapshots, their storage, recall and timed morphs."""

import json
import math
from dataclasses import replace

from . import layout, mixer
from .leds import CYAN, OFF, WHITE, Blink, Light
from .model import (
    BeginUndoStep,
    EndUndoStep,
    RecallFxSnapshot,
    SaveFxSnapshots,
    SetMacros,
    SetMixer,
    ShowMessage,
    StoreFxSnapshot,
)
from .modes import FxRack, Morph, MorphMacro
from .values import FX_TOUCH_TOLERANCE

SLOTS = 16


def keys(racks):
    # (track name, rack name, n) per rack, n counting the earlier racks with both names.
    seen = {}
    result = []
    for rack in racks:
        name = (rack.track_name, rack.rack_name)
        n = seen.get(name, 0)
        seen[name] = n + 1
        result.append((*name, n))
    return result


def capture(racks):
    return tuple(
        FxRack(track, rack, n, tuple(macro.value for macro in view.macros))
        for (track, rack, n), view in zip(keys(racks), racks)
    )


def dump(slots):
    def rack(item):
        return {"track": item.track, "rack": item.rack, "n": item.n, "macros": list(item.values)}

    data = [None if slot is None else [rack(item) for item in slot] for slot in slots]
    return json.dumps({"v": 1, "slots": data}, separators=(",", ":"))


def parse(text):
    # Anything unreadable gives empty slots: a bad store never stops the script loading.
    empty = (None,) * SLOTS
    try:
        data = json.loads(text)
        if data.get("v") != 1 or len(data["slots"]) != SLOTS:
            return empty
        return tuple(
            None
            if slot is None
            else tuple(
                FxRack(
                    str(item["track"]),
                    str(item["rack"]),
                    int(item["n"]),
                    tuple(float(value) for value in item["macros"]),
                )
                for item in slot
            )
            for slot in data["slots"]
        )
    except (ValueError, TypeError, KeyError, AttributeError):
        return empty


def _put(slots, slot, value):
    return slots[:slot] + (value,) + slots[slot + 1 :]



def toggle(state):
    if state.fx:
        return replace(state, fx=False, fx_length=None), [ShowMessage("FX Mode OFF")]
    # FX and Mixer Mode replace each other.
    actions = []
    if state.mixer:
        state, actions = mixer.reset(state)
        state = replace(state, mixer=False)
        actions.append(SetMixer(False))
    state = replace(state, fx=True, copy_source=None)
    return state, actions + [ShowMessage("FX Mode ON")]


def press(state, event, snapshot):
    # Every grid pad in FX Mode, releases included.
    key = (event.column, event.pad)
    if key in layout.FX_LENGTHS:
        bars = layout.FX_LENGTHS[key]
        if event.pressed:
            return replace(state, fx_length=bars), []
        if state.fx_length == bars:
            return replace(state, fx_length=None), []
        return state, []
    # Under Shift the grid is dark and does nothing, as Mixer's faders.
    if not event.pressed or state.shift or key not in layout.FX_SLOTS:
        return state, []
    slot = layout.FX_SLOTS.index(key)
    stored = state.fx_slots[slot] is not None
    # Copy over Delete, as in Session Mode.
    if state.copy or (not state.delete and not stored):
        return state, [StoreFxSnapshot(slot)]
    if state.delete:
        if not stored:
            return state, []
        slots = _put(state.fx_slots, slot, None)
        message = ShowMessage(f"Snapshot {slot + 1} cleared")
        return replace(state, fx_slots=slots), [SaveFxSnapshots(dump(slots)), message]
    return state, [RecallFxSnapshot(slot, state.fx_length)]


def render(state):
    # The grid columns in FX Mode; dark under Shift, as Mixer's faders.
    frame = {
        (column, pad): Light(OFF)
        for column in layout.GRID_COLUMNS
        for pad in range(1, layout.ROWS + 1)
    }
    if state.shift and not state.copy and not state.delete:
        return frame
    target = state.morph.slot if state.morph is not None else None
    for slot, key in enumerate(layout.FX_SLOTS):
        if slot == target:
            frame[key] = Light(CYAN, Blink.FAST)
        elif state.fx_slots[slot] is not None:
            frame[key] = Light(CYAN, Blink.TEMPO if slot == state.fx_landed else Blink.STEADY)
    for key, bars in layout.FX_LENGTHS.items():
        frame[key] = Light(WHITE, Blink.FAST if bars == state.fx_length else Blink.STEADY)
    return frame


def racks_read(state, event, snapshot):
    # The adapter's rack read after a store or a recall, in any mode.
    number = event.slot + 1
    if not event.recall:
        if not event.racks:
            return state, [ShowMessage("No racks to store")]
        slots = _put(state.fx_slots, event.slot, capture(event.racks))
        message = ShowMessage(f"Snapshot {number} stored ({_count(len(event.racks), 'rack')})")
        return replace(state, fx_slots=slots), [SaveFxSnapshots(dump(slots)), message]
    stored = state.fx_slots[event.slot]
    if stored is None:
        return state, []
    macros, missing = _match(stored, event.racks)
    note = f", {_count(missing, 'rack')} not found" if missing else ""
    if not macros:
        return state, [ShowMessage(f"Snapshot {number}: nothing to recall{note}")]
    # A new recall replaces a running morph and its undo step.
    actions = [EndUndoStep()] if state.fx_undo_open else []
    if event.bars is None or not snapshot.is_playing:
        writes = tuple((m.path, m.rack_name, m.index, m.target) for m in macros)
        actions += [BeginUndoStep(), SetMacros(writes), EndUndoStep()]
        state = replace(state, morph=None, fx_undo_open=False, fx_landed=event.slot)
        return state, actions + [ShowMessage(f"Snapshot {number} recalled{note}")]
    start = snapshot.song_beats
    morph = Morph(event.slot, start, end_beats(snapshot, event.bars), start, macros)
    state = replace(state, morph=morph, fx_undo_open=True)
    message = ShowMessage(f"Snapshot {number} in {_count(event.bars, 'bar')}{note}")
    return state, actions + [BeginUndoStep(), message]


def tick(state, transport, values):
    # On the 10 ms timer: values holds each morphing macro's live value, None if unreadable.
    morph = state.morph
    # A macro turned by hand, or gone, drops out and keeps its value.
    macros = [
        macro
        for macro, value in zip(morph.macros, values)
        if value is not None and abs(value - macro.written) <= FX_TOUCH_TOLERANCE * macro.span
    ]
    now = transport.song_beats
    # A stop or a backward jump lands at once: there's nothing to interpolate to.
    if not transport.is_playing or now >= morph.end_beats or now < morph.last_beats:
        writes = tuple((m.path, m.rack_name, m.index, m.target) for m in macros)
        actions = [SetMacros(writes)] if writes else []
        if state.fx_undo_open:
            actions.append(EndUndoStep())
        state = replace(state, morph=None, fx_undo_open=False, fx_landed=morph.slot)
        return state, actions, True
    # Linear in song beats; quantized macros switch only when the morph lands.
    fraction = (now - morph.start_beats) / (morph.end_beats - morph.start_beats)
    moved, writes = [], []
    for macro in macros:
        if not macro.quantized:
            value = macro.start + (macro.target - macro.start) * fraction
            if value != macro.written:
                writes.append((macro.path, macro.rack_name, macro.index, value))
                macro = replace(macro, written=value)
        moved.append(macro)
    state = replace(state, morph=replace(morph, macros=tuple(moved), last_beats=now))
    return state, [SetMacros(tuple(writes))] if writes else [], False


def end_beats(snapshot, bars):
    # The Nth bar line after now.
    bar = snapshot.signature_numerator * 4 / snapshot.signature_denominator
    return math.floor(snapshot.song_beats / bar) * bar + bars * bar


def _match(stored, racks):
    # MorphMacro per macro both the snapshot and the Set's rack have, and the missing count.
    current = dict(zip(keys(racks), racks))
    macros, missing = [], 0
    for item in stored:
        rack = current.get((item.track, item.rack, item.n))
        if rack is None:
            missing += 1
            continue
        for index, (value, view) in enumerate(zip(item.values, rack.macros)):
            target = min(max(value, view.min), view.max)
            macros.append(
                MorphMacro(
                    rack.path,
                    rack.rack_name,
                    index,
                    view.value,
                    target,
                    view.is_quantized,
                    view.value,
                    view.max - view.min,
                )
            )
    return tuple(macros), missing


def _count(n, noun):
    return f"{n} {noun}" if n == 1 else f"{n} {noun}s"
