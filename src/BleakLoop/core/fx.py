"""FX Mode: rack macro snapshots, their storage, recall and timed morphs."""

import json
import math
from dataclasses import replace

from . import buttons, faders, functions, layout, mixer
from .leds import CYAN, LIME, OFF, ORANGE, PINK, WHITE, Blink, Light
from .model import (
    BeginUndoStep,
    EndUndoStep,
    FireScene,
    RecallFxSnapshot,
    SaveFxScenes,
    SaveFxSnapshots,
    SetMacros,
    SetMixer,
    StoreFxSnapshot,
)
from .modes import FxRack, Mode, Morph, MorphMacro, PendingLaunch, SlideParam, SlotHold
from .values import BEAT_EPSILON, FX_TOUCH_TOLERANCE, LOOP_WRAP_TOLERANCE, SLIDE_START, X_COLUMN_WIDTH

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


def dump(slots, scoped):
    # v2: every bank's slots by global index. The scoped slots go in their own key, only when
    # there are any.
    data = {"v": 2, "slots": [_encode(slot) for slot in slots]}
    if scoped:
        data["scoped"] = sorted(scoped)
    return json.dumps(data, separators=(",", ":"))


def parse(text):
    # (slots, scoped). Anything unreadable gives empty slots: a bad store never stops the
    # script loading. A bad "scoped" entry is dropped, leaving its slot Set-wide. A v1 store
    # loads as bank 1, with banks 2-8 empty.
    return _parse(text) or ((None,) * layout.FX_SNAPSHOTS, frozenset())


def readable(text):
    # The store parses as a whole: v1 or v2, with every slot decoding.
    return _parse(text) is not None


def _parse(text):
    try:
        data = json.loads(text)
        count = STORE_SLOTS.get(data.get("v"))
        if count is None or len(data["slots"]) != count:
            return None
        slots = tuple(_decode(slot) for slot in data["slots"])
    except (ValueError, TypeError, KeyError, AttributeError):
        return None
    slots += (None,) * (layout.FX_SNAPSHOTS - count)
    scoped = data.get("scoped")
    if not isinstance(scoped, list):
        return slots, frozenset()
    return slots, frozenset(
        i
        for i in scoped
        if isinstance(i, int) and not isinstance(i, bool) and 0 <= i < count and slots[i] is not None
    )


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
    changed = scenes != _fit(state.fx_scenes, len(scenes))
    state = replace(
        state, fx_scenes=scenes, morph=morph, fx_landed_scene=landed, pending_launch=pending
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
    # A Set-wide store or a clear leaves the slot unscoped.
    return _save_slots(state, _put(state.fx_slots, slot, value), state.fx_scoped - {slot})


def _save_slots(state, slots, scoped):
    state = replace(state, fx_slots=slots, fx_scoped=frozenset(scoped))
    return state, SaveFxSnapshots(dump(slots, state.fx_scoped))


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
    if not scene and slot in state.fx_scoped:
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
    state = replace(state, fx=True, copy_source=None)
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
    # The Shift layer (Copy and Delete come first): an empty slot stores the selected rack
    # alone. Scene snapshots stay Set-wide, and the other pads do nothing.
    if state.shift and not state.copy and not state.delete:
        if button.function == "slots" and state.fx_slots[_global(state, button.value)] is None:
            return state, [StoreFxSnapshot(_global(state, button.value), scoped=True)]
        return state, []
    if button.function == "slots" and not (state.copy or state.delete or state.fx_length):
        slot = _global(state, button.value)
        if state.fx_slots[slot] is not None:
            return _hold(state, event, slot)
    return functions.press(button, state, snapshot)


# Held slots: a tap recalls on the lift, a slide right blends towards the slot.


def holding(state, event):
    # The release ends a slot hold: on its row, at the column its finger is on now.
    return _held(state, event.pad, event.column) is not None


def _held(state, pad, column=None):
    return next(
        (h for h in state.fx_holds if h.pad == pad and (column is None or h.column == column)),
        None,
    )


def _hold(state, event, slot):
    # One hold per row. The read is taken now, so a slide's origins are the press's values.
    if _held(state, event.pad) is not None:
        return state, []
    hold = SlotHold(event.pad, event.column, slot)
    return replace(state, fx_holds=state.fx_holds + (hold,)), [RecallFxSnapshot(slot, None, hold=True)]


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
    new = replace(new, f=min(max(columns / SLIDE_COLUMNS, 0.0), 1.0))
    if new == hold:
        return state, [], False
    state = _put_hold(state, hold, new)
    redraw = not hold.slid or meter(hold.f) != meter(new.f)
    if new.read is None or (hold.slid and new.f == hold.f):
        return state, [], redraw
    state, actions = _blend(state, new)
    return state, actions, redraw


def meter(f):
    # The meter's lit pads past the slot: one per 25%, the first as soon as f is above 0.
    return sum(f > k / SLIDE_COLUMNS for k in range(SLIDE_COLUMNS))


def _hold_read(state, event, snapshot):
    hold = next((h for h in state.fx_holds if h.slot == event.slot and h.read is None), None)
    stored = state.fx_slots[event.slot]
    if hold is None or stored is None:
        return state, []
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
    state, actions = _recall_now(state, hold.read)
    state = _landed(state, hold.slot, False)
    return state, actions + buttons.say("slots", "recalled", name=name, note=hold.note)


def _recall_now(state, macros):
    # A recall that writes at once. With slides held it takes their shared parameters and joins
    # their undo step; otherwise it is its own step, closing a fader's or a morph's.
    writes = tuple((m.key, m.target) for m in macros)
    if state.fx_slide_undo_open:
        state = _leave_slides(state, {m.key for m in macros})
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


def _leave_slides(state, keys):
    # These parameters leave every held slide, and stay where they are.
    holds = tuple(replace(h, dropped=h.dropped | keys) for h in state.fx_holds)
    params = tuple(p for p in state.fx_slide_params if p.key not in keys)
    return replace(state, fx_holds=holds, fx_slide_params=params)


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
    # proportion, quantized ones at the slot's value from switch_at on.
    if not hold.read:
        return state, []
    actions = []
    if not state.fx_slide_undo_open:
        state, actions = _close_steps(state)
        actions.append(BeginUndoStep())
        state = replace(state, fx_slide_undo_open=True)
    if not hold.wrote:
        # A slide's first write cancels a running morph.
        new = replace(hold, wrote=True)
        state, hold = _put_hold(state, hold, new), new
        if state.morph is not None:
            if state.fx_undo_open:
                actions.append(EndUndoStep())
            state = replace(state, morph=None, fx_undo_open=False)
    switch_at = buttons.switch_at()
    params = list(state.fx_slide_params)
    writes = []
    for macro in hold.read:
        key = macro.key
        if key in hold.dropped or (keys is not None and key not in keys):
            continue
        if _slide_owner(state, key) is not hold:
            continue
        param = _param(state, key)
        if param is None:
            param = SlideParam(key, macro.start, macro.start, macro.span)
            params.append(param)
        if macro.quantized:
            value = macro.target if hold.f >= switch_at else param.origin
        else:
            value = param.origin + hold.f * (macro.target - param.origin)
        if value != param.written:
            writes.append((key, value))
            params = [replace(p, written=value) if p.key == key else p for p in params]
    state = replace(state, fx_slide_params=tuple(params))
    if writes:
        actions.append(SetMacros(tuple(writes)))
    return state, actions


def _end_slide(state, hold):
    # The lift after a slide: the values stay. The parameters it owned go back to the latest
    # remaining slide holding them, at that slide's f; the last slide's lift closes the step.
    actions = []
    if hold.read:
        owned = {m.key for m in hold.read if m.key not in hold.dropped}
        for key in owned:
            if _param(state, key) is None:
                continue
            owner = _slide_owner(state, key)
            if owner is not None and owner.wrote:
                state, more = _blend(state, owner, {key})
                actions += more
        state = _rebase(state)
    if state.fx_slide_undo_open and not any(h.slid for h in state.fx_holds):
        state = replace(state, fx_slide_undo_open=False)
        actions.append(EndUndoStep())
    percent = round(hold.f * 100)
    name = _name(hold.slot, False)
    return state, actions + buttons.say("slots", "slid", name=name, percent=percent, note=hold.note)


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
    # Pink for one rack's snapshot, cyan for the Set's.
    colour = PINK if slot in state.fx_scoped else CYAN
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
    morph = state.morph
    if morph is not None and morph.scene and morph.slot == scene:
        return Light(LIME, Blink.FAST)
    if scene_snapshot(state, scene) is not None:
        return Light(LIME, Blink.TEMPO if scene == state.fx_landed_scene else Blink.STEADY)
    return Light(OFF)


def _slot_press(state, slot, scene, snapshot):
    stored = _stored(state, slot, scene) is not None
    # Copy over Delete, as in Session Mode.
    if state.copy or (not state.delete and not stored):
        return state, [StoreFxSnapshot(slot, scene=scene)]
    if state.delete:
        if not stored:
            return state, []
        state, save = _set(state, slot, scene, None, snapshot.scene_count)
        return state, [save, *buttons.say(_owner(scene), "cleared", name=_name(slot, scene))]
    return state, [RecallFxSnapshot(slot, state.fx_length, scene=scene)]


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
    if not event.recall and event.scoped:
        return _store_scoped(state, event, name)
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
    if state.fx_slide_undo_open:
        # Slides are held: the morph takes the parameters it shares and joins their step. A
        # morph it replaces closes its own.
        state = _leave_slides(state, {m.key for m in macros})
        actions = [EndUndoStep()] if state.fx_undo_open else []
        return replace(state, morph=morph, fx_undo_open=False), actions + message
    # A recall closes a fader gesture's undo step, and replaces a running morph and its step;
    # the finger carries on in a new one.
    state, actions = _close_steps(state)
    state = replace(state, morph=morph, fx_undo_open=True)
    return state, actions + [BeginUndoStep(), *message]


def _store_scoped(state, event, name):
    # The selected rack's macros only; its key counts every rack in the Set, as a recall's do.
    stored = tuple(
        item
        for item, view in zip(capture(event.racks), event.racks)
        if event.selected is not None and view.path == event.selected
    )
    if not stored:
        return state, buttons.refuse("slots", "no_rack", name=name)
    slots = _put(state.fx_slots, event.slot, stored)
    state, save = _save_slots(state, slots, state.fx_scoped | {event.slot})
    return state, [save, *buttons.say("slots", "stored_scoped", name=name, rack=stored[0].rack)]


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
