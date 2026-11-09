"""FX Mode: rack macro snapshots, their storage, recall and timed morphs."""

import json
import math
from dataclasses import replace

from . import buttons, faders, functions, layout, mixer
from .leds import CYAN, LIME, OFF, WHITE, Blink, Light
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
from .modes import FxRack, Mode, Morph, MorphMacro, PendingLaunch
from .values import BEAT_EPSILON, FX_TOUCH_TOLERANCE, LOOP_WRAP_TOLERANCE

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


def dump(slots, scoped):
    # The scoped slots go in their own key, only when there are any: older builds ignore it,
    # and a store without scoped slots keeps the v1 text it always had.
    data = {"v": 1, "slots": [_encode(slot) for slot in slots]}
    if scoped:
        data["scoped"] = sorted(scoped)
    return json.dumps(data, separators=(",", ":"))


def parse(text):
    # (slots, scoped). Anything unreadable gives empty slots: a bad store never stops the
    # script loading. A bad "scoped" entry is dropped, leaving its slot Set-wide.
    empty = (None,) * layout.FX_SLOTS, frozenset()
    try:
        data = json.loads(text)
        if data.get("v") != 1 or len(data["slots"]) != layout.FX_SLOTS:
            return empty
        slots = tuple(_decode(slot) for slot in data["slots"])
    except (ValueError, TypeError, KeyError, AttributeError):
        return empty
    scoped = data.get("scoped")
    if not isinstance(scoped, list):
        return slots, frozenset()
    return slots, frozenset(
        i
        for i in scoped
        if isinstance(i, int) and not isinstance(i, bool) and 0 <= i < layout.FX_SLOTS and slots[i] is not None
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
    return f"Scene {slot + 1} snapshot" if scene else f"Snapshot {slot + 1}"


def _landed(state, slot, scene):
    # Only the last snapshot to land blinks, global or scene.
    if scene:
        return replace(state, fx_landed=None, fx_landed_scene=slot)
    return replace(state, fx_landed=slot, fx_landed_scene=None)


def panel_visible(state):
    # Session or Mixer Mode's split view shows the snapshots in columns 11-14.
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
    # Under Shift the grid is dark and does nothing, as Mixer's faders.
    if not event.pressed or state.shift:
        return state, []
    return functions.press(button, state, snapshot)


@functions.register("slots", light=lambda state, snapshot, slot: _slot_light(state, slot - 1))
def _slot(state, snapshot, slot):
    return _slot_press(state, slot - 1, False, snapshot)


@functions.register(
    "scene_slots", light=lambda state, snapshot, row: _scene_slot_light(state, snapshot, row - 1)
)
def _scene_slot(state, snapshot, row):
    # Column 13 follows the scene pads.
    scene = state.window.scene + row - 1
    if scene < snapshot.scene_count:
        return _slot_press(state, scene, True, snapshot)
    return state, []


functions.register_hold(
    "bars",
    light=lambda state, snapshot, bars: Light(WHITE, Blink.FAST if bars == state.fx_length else Blink.STEADY),
)


def _slot_light(state, slot):
    morph = state.morph
    if morph is not None and not morph.scene and morph.slot == slot:
        return Light(CYAN, Blink.FAST)
    if state.fx_slots[slot] is not None:
        return Light(CYAN, Blink.TEMPO if slot == state.fx_landed else Blink.STEADY)
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
    # The grid columns right of the faders in FX Mode, and the split views' snapshot panel;
    # dark under Shift, as Mixer's faders.
    frame = {
        (column, pad): Light(OFF)
        for column in layout.GRID_COLUMNS
        if column not in layout.FX_FADER_COLUMNS
        for pad in range(1, layout.ROWS + 1)
    }
    if state.shift and not state.copy and not state.delete:
        return frame
    functions.paint(frame, layout.FX.buttons(), state, snapshot)
    return frame


def racks_read(state, event, snapshot):
    # The adapter's rack read after a store or a recall, in any mode.
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
    # A recall closes a fader gesture's undo step; the finger carries on in a new one.
    actions = []
    if state.fader_undo_open:
        state = replace(state, fader_undo_open=False)
        actions.append(EndUndoStep())
    # A new recall replaces a running morph and its undo step.
    if state.fx_undo_open:
        actions.append(EndUndoStep())
    launch = event.end_beats is not None
    if launch:
        # The press decided the landing: the follow-up's transport may already have started.
        instant = snapshot.song_beats >= event.end_beats
    else:
        instant = event.bars is None or not snapshot.is_playing
    if instant:
        writes = tuple((m.path, m.rack_name, m.index, m.target) for m in macros)
        actions += [BeginUndoStep(), SetMacros(writes), EndUndoStep()]
        state = replace(state, morph=None, fx_undo_open=False)
        state = _landed(state, event.slot, event.scene)
        return state, actions + buttons.say(owner, "recalled", name=name, note=note)
    start = snapshot.song_beats
    end = event.end_beats if launch else end_beats(snapshot, event.bars)
    morph = Morph(event.slot, start, end, start, macros, scene=event.scene, launch=launch)
    state = replace(state, morph=morph, fx_undo_open=True)
    timing = "on launch" if launch else f"in {_count(event.bars, 'bar')}"
    message = buttons.say(owner, "morphing", name=name, timing=timing, note=note)
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
        writes = tuple((m.path, m.rack_name, m.index, m.target) for m in macros)
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
                writes.append((macro.path, macro.rack_name, macro.index, value))
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
