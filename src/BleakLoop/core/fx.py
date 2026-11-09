"""FX Mode: rack macro snapshots, their storage, recall and timed morphs."""

import json
import math
from dataclasses import replace

from . import buttons, faders, functions, layout, mixer
from .leds import CYAN, LIME, OFF, ORANGE, PINK, RED, WHITE, Blink, Light
from .model import (
    BeginUndoStep,
    BindSelectedParameter,
    EndUndoStep,
    FireScene,
    RecallFxSnapshot,
    SaveFxScenes,
    SaveFxSnapshots,
    SetMacros,
    SetMixer,
    StoreFxSnapshot,
)
from .modes import BindHold, BoundRead, BoundSlot, FaderBinding, FxRack, Mode, Morph, MorphMacro, PendingLaunch, SlideParam, SlotHold
from .values import BEAT_EPSILON, BIND_UNDO_MS, FX_TOUCH_TOLERANCE, LOOP_WRAP_TOLERANCE, SLIDE_START, STATUS_MAX, X_COLUMN_WIDTH

# A slide's travel to 100%, in columns: four pads to the right of its slot.
SLIDE_COLUMNS = 4

# Launch quantization values (global_column.QUANTIZATION_NAMES) to their length: bars, then beats.
LAUNCH_BARS = {1: 8, 2: 4, 3: 2, 4: 1}
LAUNCH_BEATS = {5: 2, 6: 4 / 3, 7: 1, 8: 2 / 3, 9: 1 / 2, 10: 1 / 3, 11: 1 / 4, 12: 1 / 6, 13: 1 / 8}


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


# The slot count each store version holds: v1 is bank 1 alone, from before banks.
STORE_SLOTS = {1: layout.FX_SLOTS, 2: layout.FX_SNAPSHOTS}


def dump(slots):
    # v2: every bank's slots by global index; a bound slot as {"bound": [locator, ...]}.
    data = {"v": 2, "slots": [_encode_slot(slot) for slot in slots]}
    return json.dumps(data, separators=(",", ":"))


def parse(text):
    # The slots. Anything unreadable gives empty slots: a bad store never stops the script
    # loading. A v1 store loads as bank 1, with banks 2-8 empty. #104's "scoped" slots, one
    # rack's macros with values, become bound slots of those macros, without the values.
    return _parse(text) or (None,) * layout.FX_SNAPSHOTS


def readable(text):
    # The store parses as a whole: v1 or v2, with every slot decoding.
    return _parse(text) is not None


def _parse(text):
    try:
        data = json.loads(text)
        count = STORE_SLOTS.get(data.get("v"))
        if count is None or len(data["slots"]) != count:
            return None
        slots = list(_decode_slot(slot) for slot in data["slots"])
    except (ValueError, TypeError, KeyError, AttributeError):
        return None
    scoped = data.get("scoped")
    for i in scoped if isinstance(scoped, list) else ():
        if isinstance(i, int) and not isinstance(i, bool) and 0 <= i < count:
            if isinstance(slots[i], tuple):
                slots[i] = bind_racks(slots[i])
    return tuple(slots) + (None,) * (layout.FX_SNAPSHOTS - count)


def bind_racks(racks):
    # A bound slot of every macro of these racks, matched by index: #104's scoped snapshot.
    params = tuple(
        FaderBinding(rack.track, 0, rack.rack, rack.n, index + 1, f"Macro {index + 1}")
        for rack in racks
        for index in range(len(rack.values))
    )
    return _bound_slot(params, ())


def _bound_slot(params, values):
    # A bound slot of these parameters and their punch-in values (None where there's none), or
    # None with no parameters. All None is stored as ().
    if not params:
        return None
    values = tuple(values)
    return BoundSlot(tuple(params), values if any(v is not None for v in values) else ())


def _values(slot):
    # A bound slot's punch-in value per parameter, None where there's none.
    values = slot.values[: len(slot.params)]
    return tuple(values) + (None,) * (len(slot.params) - len(values))


LOCATOR_FIELDS = ("track", "tn", "device", "dn", "param", "name")


def _encode_slot(slot):
    # A bound locator's punch-in value goes in its entry as "value", left out when it has none.
    if isinstance(slot, BoundSlot):
        return {"bound": [_encode_locator(p, v) for p, v in zip(slot.params, _values(slot))]}
    return _encode(slot)


def _encode_locator(locator, value):
    item = {field: getattr(locator, field) for field in LOCATOR_FIELDS}
    if value is not None:
        item["value"] = value
    return item


def _decode_slot(slot):
    # A bound slot's bad entries are dropped with their values; with none left, the slot is
    # empty. A bad value is dropped alone.
    if isinstance(slot, dict):
        entries = [(_locator(item), _value(item)) for item in slot["bound"]]
        kept = [(p, v) for p, v in entries if p is not None]
        return _bound_slot([p for p, _ in kept], [v for _, v in kept])
    return _decode(slot)


def _value(item):
    value = item.get("value") if isinstance(item, dict) else None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return None


def _locator(item):
    if not isinstance(item, dict):
        return None
    track, tn, device, dn, param, name = (item.get(field) for field in LOCATOR_FIELDS)
    counts = (tn, dn, param)
    if not all(isinstance(n, int) and not isinstance(n, bool) and n >= 0 for n in counts):
        return None
    if not isinstance(track, str) or not isinstance(name, str):
        return None
    if device is not None and not isinstance(device, str):
        return None
    return FaderBinding(track, tn, device, dn, param, name)


def is_bound(slot):
    return isinstance(slot, BoundSlot)


def dump_scenes(scenes):
    # Exactly the entries given: callers fit them to the Set's scene count first.
    data = [_encode(snapshot) for snapshot in scenes]
    return json.dumps({"v": 1, "scenes": data}, separators=(",", ":"))


def parse_scenes(text):
    # Any length; anything unreadable gives no scene snapshots.
    try:
        data = json.loads(text)
        if data.get("v") != 1 or not isinstance(data["scenes"], list):
            return ()
        return tuple(_decode(snapshot) for snapshot in data["scenes"])
    except (ValueError, TypeError, KeyError, AttributeError):
        return ()


def scene_snapshot(state, scene):
    return state.fx_scenes[scene] if scene < len(state.fx_scenes) else None


def scene_origins(old, new, duplicate):
    # (origin, copies) per new scene, or None when no scene is kept: a different Set.
    # duplicate(i) says whether new scene i has scene i - 1's clips, as Live's Duplicate
    # inserts it.
    origin = tuple(next((i for i, scene in enumerate(old) if scene == item), None) for item in new)
    if all(i is None for i in origin):
        return None
    # Live re-creates a dragged scene as a new object. With the count unchanged, the scenes
    # that vanished are the ones that moved: pair them, in order, with the new ones.
    if len(old) == len(new):
        vanished = iter(i for i in range(len(old)) if i not in origin)
        origin = tuple(next(vanished) if i is None else i for i in origin)
    copies = tuple(
        origin[i - 1]
        if origin[i] is None and i > 0 and origin[i - 1] is not None and duplicate(i)
        else None
        for i in range(len(new))
    )
    return origin, copies


def scenes_changed(state, event):
    # A moved scene keeps its snapshot, a deleted one's goes, a duplicate copies its source's.
    def kept(old):
        return scene_snapshot(state, old) if old is not None else None

    scenes = tuple(
        kept(old) if old is not None else kept(copy)
        for old, copy in zip(event.origin, event.copies)
    )
    moved = {old: new for new, old in enumerate(event.origin) if old is not None}
    morph = state.morph
    if morph is not None and morph.scene and morph.slot is not None:
        morph = replace(morph, slot=moved.get(morph.slot))
    landed = state.fx_landed_scene
    if landed is not None:
        landed = moved.get(landed)
    # A pending launch follows its scene, and goes with it.
    pending = state.pending_launch
    if pending is not None:
        scene = moved.get(pending.scene)
        pending = None if scene is None else replace(pending, scene=scene)
    # Copy's picked scene snapshot follows its scene, and goes with it.
    source = state.fx_copy_source
    if source is not None and source[1]:
        scene = moved.get(source[0])
        source = None if scene is None else (scene, True)
    changed = scenes != _fit(state.fx_scenes, len(scenes))
    state = replace(
        state,
        fx_scenes=scenes,
        morph=morph,
        fx_landed_scene=landed,
        pending_launch=pending,
        fx_copy_source=source,
    )
    return state, [SaveFxScenes(dump_scenes(scenes))] if changed else []


def copy_scene(state, source, target, scene_count):
    # Session Mode's scene copy: the target takes the source's snapshot, if it has one.
    snapshot = scene_snapshot(state, source)
    if snapshot is None:
        return state, []
    state, save = _set(state, target, True, snapshot, scene_count)
    return state, [save]


def _encode(snapshot):
    if snapshot is None:
        return None
    return [
        {"track": item.track, "rack": item.rack, "n": item.n, "macros": list(item.values)}
        for item in snapshot
    ]


def _decode(snapshot):
    if snapshot is None:
        return None
    return tuple(
        FxRack(
            str(item["track"]),
            str(item["rack"]),
            int(item["n"]),
            tuple(float(value) for value in item["macros"]),
        )
        for item in snapshot
    )


def _put(slots, slot, value):
    return slots[:slot] + (value,) + slots[slot + 1 :]


def _fit(scenes, count):
    # One entry per scene in the Set, as each save writes.
    return (tuple(scenes) + (None,) * count)[:count]


def _stored(state, slot, scene):
    return scene_snapshot(state, slot) if scene else state.fx_slots[slot]


def _set(state, slot, scene, value, scene_count):
    # The state with the snapshot set or cleared, and the save.
    if scene:
        padded = state.fx_scenes + (None,) * (slot + 1 - len(state.fx_scenes))
        scenes = _fit(_put(padded, slot, value), scene_count)
        return replace(state, fx_scenes=scenes), SaveFxScenes(dump_scenes(scenes))
    return _save_slots(state, _put(state.fx_slots, slot, value))


def _save_slots(state, slots):
    return replace(state, fx_slots=slots), SaveFxSnapshots(dump(slots))


def _owner(scene):
    # The function whose wording a snapshot message uses.
    return "scene_slots" if scene else "slots"


def _name(slot, scene):
    # slot is the global slot: its number within its bank, and the bank past bank 1.
    if scene:
        return f"Scene {slot + 1} snapshot"
    bank, n = divmod(slot, layout.FX_SLOTS)
    return f"Snapshot {n + 1}" if bank == 0 else f"Snapshot {n + 1}, bank {bank + 1}"


def _landed(state, slot, scene):
    # Only the last Set-wide snapshot to land blinks, global or scene. A scoped one moves a
    # single rack, so it leaves the blink where it was.
    if not scene and is_bound(state.fx_slots[slot]):
        return state
    if scene:
        return replace(state, fx_landed=None, fx_landed_scene=slot)
    return replace(state, fx_landed=slot, fx_landed_scene=None)


def panel_visible(state):
    # Session or Mixer Mode's split view shows the snapshots in columns 10-14.
    return state.mode is Mode.SESSION and faders.split_view(state) and state.split_snapshots


def toggle(state):
    if state.fx:
        state, actions = faders.reset(state)
        state = replace(state, fx=False, fx_length=None)
        return state, actions + buttons.say("fx", "off")
    # FX and Mixer Mode replace each other. Split view faders give way to FX Mode's.
    state, actions = faders.reset(state)
    if state.mixer:
        state, more = mixer.reset(state)
        actions += more
        state = replace(state, mixer=False)
        actions.append(SetMixer(False))
    state = replace(state, fx=True, copy_source=None, fx_copy_source=None)
    return state, actions + buttons.say("fx", "on")


def press(state, event, snapshot):
    # Every grid pad in FX Mode, and the split views' snapshot panel, releases included.
    button = layout.FX.at((event.column, event.pad))
    if button is None:
        return state, []
    if button.function == "bars":
        # A hold: a timed recall or launch waits on it.
        bars = button.value
        if event.pressed:
            return replace(state, fx_length=bars), buttons.say("bars", bars=_count(bars, "bar"))
        if state.fx_length == bars:
            return replace(state, fx_length=None), []
        return state, []
    if not event.pressed:
        return state, []
    # The Shift layer (Copy and Delete come first): a slot's hold binds a parameter to it.
    # Scene snapshots and the other pads do nothing.
    if state.shift and not state.copy and not state.delete:
        if button.function == "slots" and state.fx_bind_hold is None:
            hold = BindHold(event.pad, event.column, _global(state, button.value))
            return replace(state, fx_bind_hold=hold), []
        return state, []
    # Device/Clip + a stored slot punches it in, over a held Bars pad; Copy and Delete come
    # first. An empty slot or a scene snapshot does nothing.
    if state.device_clip and not (state.copy or state.delete):
        if button.function == "slots":
            slot = _global(state, button.value)
            if state.fx_slots[slot] is None:
                return state, []
            return _hold(state, event, slot, punch=True)
        if button.function == "scene_slots":
            return state, []
    if button.function == "slots" and not (state.copy or state.delete):
        slot = _global(state, button.value)
        if state.fx_length and is_bound(state.fx_slots[slot]):
            # A bound slot holds no values to morph to.
            return state, []
        if not state.fx_length and state.fx_slots[slot] is not None:
            return _hold(state, event, slot)
    return functions.press(button, state, snapshot)


# Binding: Shift + a slot adds Live's selected parameter to it, or removes it if it's there.


def binding(state, event):
    hold = state.fx_bind_hold
    return hold is not None and (hold.pad, hold.column) == (event.pad, event.column)


def bind_release(state):
    hold = state.fx_bind_hold
    state = replace(state, fx_bind_hold=None)
    if hold.used:
        return state, []
    return state, [BindSelectedParameter(hold.slot)]


def parameter_bound(state, event):
    # The adapter's answer: the selected parameter, or why it can't be bound.
    name = _name(event.slot, False)
    if event.refusal == "select":
        return state, buttons.refuse("slots", "no_parameter")
    if event.refusal is not None:
        return state, buttons.refuse("slots", "cannot_hold", name=name, parameter=event.parameter)
    return bind(state, event.slot, event.binding, event.value, event.text)


def bind(state, slot, locator, value=None, text=""):
    # A parameter the slot doesn't hold is added, with its value now as its punch-in value. One
    # it holds takes its value now as its new punch-in value, or, when that is already its
    # punch-in value (or there's no value now), is removed with it. A Set-wide slot refuses.
    stored = state.fx_slots[slot]
    name = _name(slot, False)
    if stored is not None and not is_bound(stored):
        return state, buttons.refuse("slots", "set_wide", name=name)
    params = stored.params if stored is not None else ()
    values = _values(stored) if stored is not None else ()
    same = [p for p in params if _same(p, locator)]
    if same:
        old = next(v for p, v in zip(params, values) if _same(p, locator))
        if value is not None and value != old:
            new = [value if _same(p, locator) else v for p, v in zip(params, values)]
            state, save = _save_slots(state, _put(state.fx_slots, slot, _bound_slot(params, new)))
            state = _remember(state, slot, same[0], old, UPDATED)
            param = f"{describe(same[0])} {text or _number(value)}"
            return state, [save, *buttons.say("slots", "updated", name=name, param=param)]
        kept = [(p, v) for p, v in zip(params, values) if not _same(p, locator)]
        bound_slot = _bound_slot([p for p, _ in kept], [v for _, v in kept])
        state, save = _save_slots(state, _put(state.fx_slots, slot, bound_slot))
        state = _remember(state, slot, same[0], old, REMOVED)
        return state, [save, *buttons.say("slots", "removed", name=name, param=describe(same[0]))]
    state = _remember(state, slot, locator, value, ADDED)
    bound_slot = _bound_slot(params + (locator,), values + (value,))
    state, save = _save_slots(state, _put(state.fx_slots, slot, bound_slot))
    items = labels([(p.device or p.track, p.name) for p in bound_slot.params])
    if text:
        # The new parameter, last, with its value.
        items[-1] = f"{describe(locator)} {text}"
    return state, [save, *listed(items, lambda text: buttons.say("slots", "bound", name=name, params=text))]


def labels(params):
    # Each (owner, name) as the parameter's name, or "Owner Name" where two share a name.
    names = [name for _, name in params]
    return [f"{owner} {name}" if names.count(name) > 1 else name for owner, name in params]


def listed(items, say):
    # say(text) with as many items as fit in STATUS_MAX characters, then "+N" for the rest.
    for keep in range(len(items), 0, -1):
        text = ", ".join(items[:keep]) + (f", +{len(items) - keep}" if keep < len(items) else "")
        message = say(text)
        if not message or len(message[0].text) <= STATUS_MAX:
            return message
    return message


# What a bind did, for the Undo pad.
ADDED, REMOVED, UPDATED = "added", "removed", "updated"


def _remember(state, slot, locator, value, kind):
    # For the Undo pad, with the parameter's punch-in value (before an update, the old one):
    # the window starts again at the next tick.
    entry = (slot, locator, value, kind)
    return replace(state, bind_undo=state.bind_undo + (entry,), bind_undo_at=None)


def bind_undo_open(state):
    # The Undo pad would reverse a bind: one is remembered and its window hasn't run out.
    if not state.bind_undo:
        return False
    at, now = state.bind_undo_at, state.bind_undo_now
    return at is None or now is None or now - at < BIND_UNDO_MS


def unbind_last(state):
    # The Undo pad: the newest bind, removal or update reversed, without Live's Undo; a removed
    # parameter comes back with its punch-in value, an updated one gets its old value back.
    # Its window starts again for the next.
    (slot, locator, value, kind), rest = state.bind_undo[-1], state.bind_undo[:-1]
    state = replace(state, bind_undo=rest, bind_undo_at=None)
    stored = state.fx_slots[slot]
    params = stored.params if is_bound(stored) else ()
    values = _values(stored) if is_bound(stored) else ()
    name, param = _name(slot, False), describe(locator)
    if kind == UPDATED:
        if not any(_same(p, locator) for p in params):
            return state, []
        new = [value if _same(p, locator) else v for p, v in zip(params, values)]
        state, save = _save_slots(state, _put(state.fx_slots, slot, _bound_slot(params, new)))
        return state, [save, *buttons.say("slots", "restored", name=name, param=param)]
    if kind == ADDED:
        kept = [(p, v) for p, v in zip(params, values) if not _same(p, locator)]
        bound_slot = _bound_slot([p for p, _ in kept], [v for _, v in kept])
        state, save = _save_slots(state, _put(state.fx_slots, slot, bound_slot))
        return state, [save, *buttons.say("slots", "unbound", name=name, param=param)]
    if stored is not None and not is_bound(stored):
        return state, []
    bound_slot = _bound_slot(params + (locator,), values + (value,))
    state, save = _save_slots(state, _put(state.fx_slots, slot, bound_slot))
    return state, [save, *buttons.say("slots", "rebound", name=name, param=param)]


def bind_tick(state, now_ms):
    # On the 10 ms timer while a bind is remembered: stamp it, and forget it once its window
    # has run out.
    at = now_ms if state.bind_undo_at is None else state.bind_undo_at
    if now_ms - at >= BIND_UNDO_MS:
        return replace(state, bind_undo=(), bind_undo_at=None, bind_undo_now=None)
    return replace(state, bind_undo_at=at, bind_undo_now=now_ms)


def _same(a, b):
    # The same parameter: a rack macro's name may have changed since it was bound.
    return (a.track, a.tn, a.device, a.dn, a.param) == (b.track, b.tn, b.device, b.dn, b.param)


def describe(locator):
    # "Auto Filter Frequency", or a mixer parameter's "Bass Track Volume".
    return f"{locator.device or locator.track} {locator.name}"


# Held slots: a tap recalls on the lift, a slide right blends towards the slot.


def holding(state, event):
    # The release ends a slot hold: on its row, at the column its finger is on now.
    return _held(state, event.pad, event.column) is not None


def _held(state, pad, column=None):
    return next(
        (h for h in state.fx_holds if h.pad == pad and (column is None or h.column == column)),
        None,
    )


def _hold(state, event, slot, punch=False):
    # One hold per row. The read is taken now, so a slide's origins are the press's values.
    if _held(state, event.pad) is not None:
        return state, []
    stored = state.fx_slots[slot]
    bound = is_bound(stored)
    hold = SlotHold(event.pad, event.column, slot, bound=bound, punch=punch)
    locators = stored.params if bound else ()
    values = _values(stored) if bound else ()
    read = RecallFxSnapshot(slot, None, hold=True, locators=locators, values=values)
    return replace(state, fx_holds=state.fx_holds + (hold,)), [read]


def _drop_hold(state, pad):
    return replace(state, fx_holds=tuple(h for h in state.fx_holds if h.pad != pad))


def _put_hold(state, old, new):
    return replace(state, fx_holds=tuple(new if h is old else h for h in state.fx_holds))


def release(state, event, snapshot):
    # A held slot's lift: a tap recalls, a slide keeps where it got to.
    hold = _held(state, event.pad, event.column)
    if hold.read is None:
        # The read hasn't landed: it decides.
        return _put_hold(state, hold, replace(hold, lifted=True)), []
    state = _drop_hold(state, hold.pad)
    if hold.slid:
        return _end_slide(state, hold)
    return _tap(state, hold)


def slide(state, event):
    # The hold follows its finger into any column; whether a hold owns the slide.
    hold = _held(state, event.pad, event.from_column)
    if hold is None:
        return state, False
    return _put_hold(state, hold, replace(hold, column=event.to_column)), True


def x_axis(state, event):
    # An X report on a held slot's finger: the first sets the zero, a quarter column either way
    # makes it a slide, and a slide blends by how far right it is, 4 columns to 100%.
    hold = _held(state, event.pad, event.column)
    if hold.x0 is None:
        return _put_hold(state, hold, replace(hold, x0=event.value)), [], False
    columns = (event.value - hold.x0) / X_COLUMN_WIDTH
    new = hold
    if not hold.slid:
        if abs(columns) < SLIDE_START:
            return state, [], False
        count = state.fx_slide_count + 1
        state = replace(state, fx_slide_count=count)
        new = replace(new, slid=True, order=count)
    # A bound slot slides both ways; a Set-wide one only towards its snapshot.
    low = -1.0 if hold.bound else 0.0
    new = replace(new, f=min(max(columns / SLIDE_COLUMNS, low), 1.0))
    if new == hold:
        return state, [], False
    state = _put_hold(state, hold, new)
    redraw = not hold.slid or meter(hold.f) != meter(new.f)
    if new.read is None or (hold.slid and new.f == hold.f):
        return state, [], redraw
    before = value_meter(state, new) if new.bound else None
    state, actions = _blend(state, new)
    if new.bound:
        redraw = redraw or value_meter(state, _held(state, new.pad)) != before
    return state, actions, redraw


def render_meters(state):
    # Each slide's fill: the pads right of its slot to its 100% pad, in the slot's colour, one
    # per 25%. Until the lift, they hide whatever those pads show.
    frame = {}
    for hold in state.fx_holds:
        column = layout.FX.slots[hold.slot % layout.FX_SLOTS][0]
        if hold.bound:
            frame.update(_value_meter(state, hold, column))
            continue
        if not hold.slid:
            continue
        colour = PINK if is_bound(state.fx_slots[hold.slot]) else CYAN
        lit = meter(hold.f)
        for k in range(1, SLIDE_COLUMNS + 1):
            if column + k < layout.COLUMNS:
                frame[(column + k, hold.pad)] = Light(colour if k <= lit else OFF)
    return frame


def _value_meter(state, hold, column):
    # A bound slot, held: the 4 pads right of it show where its parameters sit on average
    # between their mins (none lit) and maxes (all 4), in the slot's pink.
    if not hold.read:
        return {}
    lit = value_meter(state, hold)
    return {
        (column + k, hold.pad): Light(PINK if k <= lit else OFF)
        for k in range(1, SLIDE_COLUMNS + 1)
        if column + k < layout.COLUMNS
    }


def value_meter(state, hold):
    # The lit pads: the mean of each parameter's position in its range, dropped ones and ones
    # without a range left out.
    positions = []
    for read in hold.read:
        if read.key in hold.dropped or not read.span:
            continue
        param = _param(state, read.key)
        value = param.written if param is not None else read.start
        positions.append(min(max((value - read.low) / read.span, 0.0), 1.0))
    if not positions:
        return 0
    return round(sum(positions) / len(positions) * SLIDE_COLUMNS)


def meter(f):
    # The meter's lit pads past the slot: one per 25%, the first as soon as f is above 0.
    return sum(f > k / SLIDE_COLUMNS for k in range(SLIDE_COLUMNS))


def slide_tick(state, values):
    # On the 10 ms timer: values holds each slide parameter's live value, None if unreadable.
    # One turned by hand, or gone, leaves every slide and keeps its value.
    gone = {
        p.key
        for p, value in zip(state.fx_slide_params, values)
        if value is None or abs(value - p.written) > FX_TOUCH_TOLERANCE * p.span
    }
    return faders.leave_slides(state, gone) if gone else state


def _hold_read(state, event, snapshot):
    hold = next((h for h in state.fx_holds if h.slot == event.slot and h.read is None), None)
    stored = state.fx_slots[event.slot]
    if hold is None or stored is None:
        return state, []
    if hold.bound:
        macros = tuple(p for p in event.params if p is not None)
        missing = len(event.params) - len(macros)
        note = f", {_count(missing, 'parameter')} not found" if missing else ""
    else:
        macros, missing = _match(stored, event.racks)
        note = f", {_count(missing, 'rack')} not found" if missing else ""
    read = replace(hold, read=macros, note=note)
    state = _put_hold(state, hold, read)
    if not read.lifted:
        return _blend(state, read) if read.slid else (state, [])
    if not read.slid:
        return _tap(_drop_hold(state, read.pad), read)
    # Lifted after a slide: the final blend, kept.
    state, actions = _blend(state, read)
    final = _held(state, read.pad)
    state, more = _end_slide(_drop_hold(state, read.pad), final)
    return state, actions + more


def _tap(state, hold):
    # The tap's recall, at once, from the press's read.
    name = _name(hold.slot, False)
    if not hold.read:
        return state, buttons.refuse("slots", "nothing", name=name, note=hold.note)
    if hold.bound:
        # Nothing to recall: the tap names the parameters, their values and their punch-in
        # values.
        names = labels([(p.owner, p.name) for p in hold.read])
        items = [_named(label, p) for label, p in zip(names, hold.read)]
        return state, listed(
            items, lambda text: buttons.say("slots", "named", name=name, params=text, note=hold.note)
        )
    state, actions = _recall_now(state, hold.read)
    state = _landed(state, hold.slot, False)
    return state, actions + buttons.say("slots", "recalled", name=name, note=hold.note)


def _named(label, read):
    # "Frequency 1.20 kHz → 3.40 kHz", or without a punch-in value "Frequency 1.20 kHz".
    item = f"{label} {read.text or _number(read.start)}"
    if read.target is None:
        return item
    return f"{item} → {read.target_text or _number(read.target)}"


def _recall_now(state, macros):
    # A recall that writes at once. With slides held it takes their shared parameters and joins
    # their undo step; otherwise it is its own step, closing a fader's or a morph's.
    writes = tuple((m.key, m.target) for m in macros)
    if any(h.slid for h in state.fx_holds):
        state = faders.leave_slides(state, {m.key for m in macros})
    if state.fx_slide_undo_open:
        actions = [SetMacros(writes)]
        if state.fx_undo_open:
            actions.insert(0, EndUndoStep())
        return replace(state, morph=None, fx_undo_open=False), actions
    state, actions = _close_steps(state)
    actions += [BeginUndoStep(), SetMacros(writes), EndUndoStep()]
    return replace(state, morph=None, fx_undo_open=False), actions


def _close_steps(state):
    # A recall or a slide closes a fader gesture's undo step and a running morph's.
    actions = []
    if state.fader_undo_open:
        state = replace(state, fader_undo_open=False)
        actions.append(EndUndoStep())
    if state.fx_undo_open:
        state = replace(state, fx_undo_open=False)
        actions.append(EndUndoStep())
    return state, actions


def _slide_owner(state, key):
    # The latest started slide holding the parameter, or None.
    holders = [h for h in state.fx_holds if h.slid and _holds_key(h, key)]
    return max(holders, key=lambda h: h.order, default=None)


def _holds_key(hold, key):
    return bool(hold.read) and key not in hold.dropped and any(m.key == key for m in hold.read)


def _param(state, key):
    return next((p for p in state.fx_slide_params if p.key == key), None)


def _blend(state, hold, keys=None):
    # The hold's parameters it owns (or just keys) written at its f: continuous ones in
    # proportion, quantized ones at the nearest step to that. The first actual write
    # opens the slides' undo step, closing a fader's or a morph's, and cancels a running morph.
    if not hold.read:
        return state, []
    later = [
        _keys(h) for h in state.fx_holds if h.slid and h is not hold and h.order > hold.order
    ]
    params = {p.key: p for p in state.fx_slide_params}
    writes = []
    for macro in hold.read:
        key = macro.key
        if key in hold.dropped or (keys is not None and key not in keys):
            continue
        if any(key in owned for owned in later):
            continue
        param = params.get(key)
        if param is None:
            param = params[key] = SlideParam(key, macro.start, macro.start, macro.span)
        value = _slid_value(macro, param.origin, hold.f)
        if value != param.written:
            writes.append((key, value))
            params[key] = replace(param, written=value)
    state = replace(state, fx_slide_params=tuple(params.values()))
    if not writes:
        return state, []
    actions = []
    if not state.fx_slide_undo_open:
        state, actions = _close_steps(state)
        actions.append(BeginUndoStep())
        state = replace(state, fx_slide_undo_open=True)
    if not hold.wrote:
        state = _put_hold(state, hold, replace(hold, wrote=True))
        if state.morph is not None:
            if state.fx_undo_open:
                actions.append(EndUndoStep())
            state = replace(state, morph=None, fx_undo_open=False)
    return state, actions + [SetMacros(tuple(writes))]


def _keys(hold):
    return {m.key for m in hold.read or ()} - hold.dropped


def _end_slide(state, hold):
    # The lift after a slide: the values stay. The parameters it owned go back to the latest
    # remaining slide holding them, at that slide's f; the last slide's lift closes the step.
    actions = []
    if hold.read:
        handed = {}
        for key in _keys(hold):
            owner = _slide_owner(state, key) if _param(state, key) is not None else None
            if owner is not None:
                handed.setdefault(owner.pad, set()).add(key)
        for pad, keys in handed.items():
            state, more = _blend(state, _held(state, pad), keys)
            actions += more
        state = _rebase(state)
    if state.fx_slide_undo_open and not any(h.slid for h in state.fx_holds):
        state = replace(state, fx_slide_undo_open=False)
        actions.append(EndUndoStep())
    percent = round(hold.f * 100)
    name = _name(hold.slot, False)
    if hold.bound:
        message = listed(
            labels([(p.owner, p.name) for p in hold.read or ()]),
            lambda text: buttons.say(
                "slots", "slid_bound", name=name, percent=percent, params=text, note=hold.note
            ),
        )
    else:
        message = buttons.say("slots", "slid", name=name, percent=percent, note=hold.note)
    return state, actions + message


def _slid_value(entry, origin, f):
    # A Set-wide slot's macro blends towards its snapshot value. A bound slot's parameter moves
    # from its origin by f of its range either way, stopping at its ends. An on/off or chooser
    # takes the nearest step, halves away from its origin; anything else is a macro's mapping
    # in Live.
    if isinstance(entry, BoundRead):
        move = f * entry.span
        if entry.quantized:
            move = faders.round_half(move)
        return min(max(origin + move, entry.low), entry.high)
    move = f * (entry.target - origin)
    return origin + (faders.round_half(move) if entry.quantized else move)


def _number(value):
    return f"{value:.2f}".rstrip("0").rstrip(".")


def _rebase(state):
    # A parameter no slide owns keeps its last write as the origin for the next to take it,
    # and is forgotten once no hold holds it.
    params = []
    for param in state.fx_slide_params:
        if not any(_holds_key(h, param.key) for h in state.fx_holds):
            continue
        if _slide_owner(state, param.key) is None:
            param = replace(param, origin=param.written)
        params.append(param)
    return replace(state, fx_slide_params=tuple(params))


def _global(state, slot):
    # A slot pad's value (1-16) in the selected bank, as the global slot index.
    return state.fx_bank * layout.FX_SLOTS + slot - 1


@functions.register("slots", light=lambda state, snapshot, slot: _slot_light(state, _global(state, slot)))
def _slot(state, snapshot, slot):
    return _slot_press(state, _global(state, slot), False, snapshot)


@functions.register(
    "banks", light=lambda state, snapshot, bank: Light(ORANGE if bank - 1 == state.fx_bank else OFF)
)
def _bank(state, snapshot, bank):
    # One value for the whole Set, held in memory only: a set_data write would put a dead
    # step on Live's Undo (#63).
    return replace(state, fx_bank=bank - 1), buttons.say("banks", "selected", bank=bank)


@functions.register(
    "scene_slots", light=lambda state, snapshot, row: _scene_slot_light(state, snapshot, row - 1)
)
def _scene_slot(state, snapshot, row):
    # Column 14 follows the scene pads.
    scene = state.window.scene + row - 1
    if scene < snapshot.scene_count:
        return _slot_press(state, scene, True, snapshot)
    return state, []


functions.register_hold(
    "bars",
    light=lambda state, snapshot, bars: Light(WHITE, Blink.FAST if bars == state.fx_length else Blink.STEADY),
)


def _slot_light(state, slot):
    # Pink for one rack's snapshot, cyan for the Set's; Copy's source blinks red.
    if state.fx_copy_source == (slot, False):
        return Light(RED, Blink.FAST)
    colour = PINK if is_bound(state.fx_slots[slot]) else CYAN
    if any(h.slot == slot and h.slid for h in state.fx_holds):
        return Light(colour, Blink.FAST)
    morph = state.morph
    if morph is not None and not morph.scene and morph.slot == slot:
        return Light(colour, Blink.FAST)
    if state.fx_slots[slot] is not None:
        return Light(colour, Blink.TEMPO if slot == state.fx_landed else Blink.STEADY)
    return Light(OFF)


def _scene_slot_light(state, snapshot, row):
    scene = state.window.scene + row
    if scene >= snapshot.scene_count:
        return Light(OFF)
    if state.fx_copy_source == (scene, True):
        return Light(RED, Blink.FAST)
    morph = state.morph
    if morph is not None and morph.scene and morph.slot == scene:
        return Light(LIME, Blink.FAST)
    if scene_snapshot(state, scene) is not None:
        return Light(LIME, Blink.TEMPO if scene == state.fx_landed_scene else Blink.STEADY)
    return Light(OFF)


def _slot_press(state, slot, scene, snapshot):
    # Copy over Delete, as in Session Mode.
    if state.copy:
        return _copy(state, slot, scene, snapshot)
    stored = _stored(state, slot, scene) is not None
    if not state.delete and not stored:
        return state, [StoreFxSnapshot(slot, scene=scene)]
    if state.delete:
        if not stored:
            return state, []
        state, save = _set(state, slot, scene, None, snapshot.scene_count)
        return state, [save, *buttons.say(_owner(scene), "cleared", name=_name(slot, scene))]
    return state, [RecallFxSnapshot(slot, state.fx_length, scene=scene)]


def _copy(state, slot, scene, snapshot):
    # Copy, as in Session Mode: a stored snapshot is the source, then an empty slot or scene
    # snapshot the target. Slots and scene snapshots copy both ways, but a scene snapshot can't
    # be bound.
    source = state.fx_copy_source
    value = _stored(state, slot, scene)
    if source is None:
        if value is None:
            return state, buttons.refuse("copy", "empty_snapshot")
        return replace(state, fx_copy_source=(slot, scene)), buttons.say("copy", "picked_snapshot")
    dropped = replace(state, fx_copy_source=None)
    if value is not None:
        return dropped, buttons.refuse("copy", "target_full")
    copied = _stored(state, *source)
    if copied is None:
        return dropped, []
    if scene and is_bound(copied):
        return dropped, buttons.refuse("copy", "bound_scene")
    dropped, save = _set(dropped, slot, scene, copied, snapshot.scene_count)
    message = buttons.say("copy", "snapshot_copied", source=_name(*source), target=_name(slot, scene))
    return dropped, [save, *message]


def render(state, snapshot):
    # The grid columns right of the faders in FX Mode, and the split views' snapshot panel,
    # lit under Shift too: the player sees what's there.
    frame = {
        (column, pad): Light(OFF)
        for column in layout.GRID_COLUMNS
        if column not in layout.FX_FADER_COLUMNS
        for pad in range(1, layout.ROWS + 1)
    }
    functions.paint(frame, layout.FX.buttons(), state, snapshot)
    return frame


def racks_read(state, event, snapshot):
    # The adapter's rack read after a store or a recall, in any mode.
    if event.hold:
        return _hold_read(state, event, snapshot)
    name, owner = _name(event.slot, event.scene), _owner(event.scene)
    if not event.recall:
        if not event.racks:
            return state, buttons.refuse(owner, "no_racks")
        value = capture(event.racks)
        state, save = _set(state, event.slot, event.scene, value, snapshot.scene_count)
        racks = _count(len(event.racks), "rack")
        return state, [save, *buttons.say(owner, "stored", name=name, racks=racks)]
    stored = _stored(state, event.slot, event.scene)
    if stored is None:
        return state, []
    macros, missing = _match(stored, event.racks)
    note = f", {_count(missing, 'rack')} not found" if missing else ""
    if not macros:
        return state, buttons.refuse(owner, "nothing", name=name, note=note)
    launch = event.end_beats is not None
    if launch:
        # The press decided the landing: the follow-up's transport may already have started.
        instant = snapshot.song_beats >= event.end_beats
    else:
        instant = event.bars is None or not snapshot.is_playing
    if instant:
        state, actions = _recall_now(state, macros)
        state = _landed(state, event.slot, event.scene)
        return state, actions + buttons.say(owner, "recalled", name=name, note=note)
    start = snapshot.song_beats
    end = event.end_beats if launch else end_beats(snapshot, event.bars)
    morph = Morph(event.slot, start, end, start, macros, scene=event.scene, launch=launch)
    timing = "on launch" if launch else f"in {_count(event.bars, 'bar')}"
    message = buttons.say(owner, "morphing", name=name, timing=timing, note=note)
    if any(h.slid for h in state.fx_holds):
        # Slides are held: the morph takes the parameters it shares.
        state = faders.leave_slides(state, {m.key for m in macros})
    if state.fx_slide_undo_open:
        # ...and joins their step once they have written. A morph it replaces closes its own.
        actions = [EndUndoStep()] if state.fx_undo_open else []
        return replace(state, morph=morph, fx_undo_open=False), actions + message
    # A recall closes a fader gesture's undo step, and replaces a running morph and its step;
    # the finger carries on in a new one.
    state, actions = _close_steps(state)
    state = replace(state, morph=morph, fx_undo_open=True)
    return state, actions + [BeginUndoStep(), *message]


def tick(state, transport, values, triggered=None):
    # On the 10 ms timer: values holds each morphing macro's live value, None if unreadable;
    # triggered is live_state.read_launch_triggered's.
    morph = state.morph
    # A macro turned by hand, or gone, drops out and keeps its value.
    macros = [
        macro
        for macro, value in zip(morph.macros, values)
        if value is not None and abs(value - macro.written) <= FX_TOUCH_TOLERANCE * macro.span
    ]
    now = transport.song_beats
    played = advance(transport, morph.last_beats)
    if played is not None and played != now:
        # The loop wrapped: the morph's times move back with the song time.
        shift = played - now
        start, end = morph.start_beats - shift, morph.end_beats - shift
        morph = replace(morph, start_beats=start, end_beats=end, wrapped=True)
    if morph.launch and triggered:
        morph = replace(morph, triggered=True)
    elif morph.launch and triggered is None:
        # Another scene's launch took the wait over, or the scene went: the predicted time.
        morph = replace(morph, triggered=False)
    # A stop or a backward jump lands at once: there's nothing to interpolate to.
    if played is None or _lands(morph, now, triggered):
        writes = tuple((m.key, m.target) for m in macros)
        actions = [SetMacros(writes)] if writes else []
        if state.fx_undo_open:
            actions.append(EndUndoStep())
        state = _landed(replace(state, morph=None, fx_undo_open=False), morph.slot, morph.scene)
        return state, actions, True
    # Linear in song beats; quantized macros switch only when the morph lands. A launch
    # morph whose scene starts late holds at its targets until it does.
    fraction = min((now - morph.start_beats) / (morph.end_beats - morph.start_beats), 1.0)
    moved, writes = [], []
    for macro in macros:
        if not macro.quantized:
            value = macro.start + (macro.target - macro.start) * fraction
            if value != macro.written:
                writes.append((macro.key, value))
                macro = replace(macro, written=value)
        moved.append(macro)
    state = replace(state, morph=replace(morph, macros=tuple(moved), last_beats=now))
    return state, [SetMacros(tuple(writes))] if writes else [], False


def _lands(morph, now, triggered):
    # After a wrap, a launch morph lands as its scene stops waiting, which is Live starting
    # it. Unseen waiting (an unquantized launch, or a deleted scene) keeps the predicted time,
    # as does every morph without a wrap: then the prediction is Live's own boundary, and
    # another scene's launch, which cancels this one's wait, leaves the morph alone.
    if morph.launch and morph.wrapped and morph.triggered:
        return triggered is False
    return now >= morph.end_beats


def advance(transport, last):
    # Song time now as if it ran on from last: past the loop's end after a wrap of the
    # Arrangement loop. None for a stop or a backward jump.
    now = transport.song_beats
    if not transport.is_playing:
        return None
    if now >= last:
        return now
    if not transport.loop:
        return None
    start = transport.loop_start
    end = start + transport.loop_length
    gap = max(end - last, 0.0) + (now - start)
    if last < start or now < start or gap > LOOP_WRAP_TOLERANCE:
        return None
    return last + gap


def end_beats(snapshot, bars):
    # The Nth bar line after now.
    bar = snapshot.bar_beats
    return math.floor(snapshot.song_beats / bar) * bar + bars * bar


def launch_step(snapshot):
    # Launch quantization's length in beats, None when launches are unquantized.
    q = snapshot.launch_quantization
    if q in LAUNCH_BARS:
        return LAUNCH_BARS[q] * snapshot.bar_beats
    return LAUNCH_BEATS.get(q)


def launch_end_beats(snapshot):
    # When a scene launched now starts: the next quantization boundary strictly after now.
    # None when launches are unquantized.
    step = launch_step(snapshot)
    if step is None:
        return None
    return (math.floor(snapshot.song_beats / step) + 1) * step


def scene_launch(state, scene, snapshot):
    # After a scene launch from the pads, with the press's snapshot: the scene's snapshot lands
    # as the scene starts, or at once when stopped or unquantized. A Bars pad held is ignored.
    if scene_snapshot(state, scene) is None:
        return []
    end = launch_end_beats(snapshot) if snapshot.is_playing else None
    return [RecallFxSnapshot(scene, None, scene=True, end_beats=end)]


def timed_launch(state, scene, snapshot):
    # A scene pressed with a Bars pad held starts on the Nth bar line, or on the first launch
    # quantization boundary at or after it, and its snapshot lands as it starts. Stopped, it
    # launches at once.
    if not snapshot.is_playing:
        return state, [FireScene(scene, legato=False), *scene_launch(state, scene, snapshot)]
    bars = state.fx_length
    start = end_beats(snapshot, bars)
    step = launch_step(snapshot)
    if step is None:
        fire = start
    else:
        # Any time in the last step before it starts it there: the earliest is clearest of
        # a late tick.
        start = math.ceil(start / step - BEAT_EPSILON) * step
        fire = start - step
    actions = []
    if scene_snapshot(state, scene) is not None:
        actions.append(RecallFxSnapshot(scene, None, scene=True, end_beats=start))
    if fire <= snapshot.song_beats:
        # Live's launch quantization already starts it on time.
        return state, [FireScene(scene, legato=False), *actions]
    pending = PendingLaunch(scene, fire, snapshot.song_beats)
    message = buttons.say("scenes", "timed", scene=scene + 1, bars=_count(bars, "bar"))
    return replace(state, pending_launch=pending), [*message, *actions]


def launch_tick(state, transport):
    # On the 10 ms timer: fire the pending launch at its time, counted across a wrap of the
    # loop. A stop or a backward jump cancels it, as either lands a morph at once. Returns
    # whether to redraw.
    pending = state.pending_launch
    now = transport.song_beats
    played = advance(transport, pending.last_beats)
    if played is None:
        message = buttons.say("scenes", "cancelled", scene=pending.scene + 1)
        return replace(state, pending_launch=None), message, True
    # After a wrap of the loop, the fire time moves back with the song time.
    fire = pending.fire_beats - (played - now)
    if now >= fire:
        return replace(state, pending_launch=None), [FireScene(pending.scene, legato=False)], True
    return replace(state, pending_launch=replace(pending, fire_beats=fire, last_beats=now)), [], False


def _match(stored, racks):
    # MorphMacro per macro both the snapshot and the Set's rack have, and the missing count.
    if is_bound(stored):
        return (), 0
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
                    (rack.path, rack.rack_name, index),
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
