"""FX Mode: rack macro snapshots, their storage, recall and timed morphs."""

import json
import math
from dataclasses import replace

from . import faders, layout, mixer
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
    ShowMessage,
    StoreFxSnapshot,
)
from .modes import FxRack, Mode, Morph, MorphMacro, PendingLaunch
from .values import FX_TOUCH_TOLERANCE

SLOTS = 16

# Launch quantization values (column_1.QUANTIZATION_NAMES) to their length: bars, then beats.
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


def dump(slots):
    return json.dumps({"v": 1, "slots": [_encode(slot) for slot in slots]}, separators=(",", ":"))


def parse(text):
    # Anything unreadable gives empty slots: a bad store never stops the script loading.
    empty = (None,) * SLOTS
    try:
        data = json.loads(text)
        if data.get("v") != 1 or len(data["slots"]) != SLOTS:
            return empty
        return tuple(_decode(slot) for slot in data["slots"])
    except (ValueError, TypeError, KeyError, AttributeError):
        return empty


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
    slots = _put(state.fx_slots, slot, value)
    return replace(state, fx_slots=slots), SaveFxSnapshots(dump(slots))


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
        return state, actions + [ShowMessage("FX Mode OFF")]
    # FX and Mixer Mode replace each other. Split view faders give way to FX Mode's.
    state, actions = faders.reset(state)
    if state.mixer:
        state, more = mixer.reset(state)
        actions += more
        state = replace(state, mixer=False)
        actions.append(SetMixer(False))
    state = replace(state, fx=True, copy_source=None)
    return state, actions + [ShowMessage("FX Mode ON")]


def press(state, event, snapshot):
    # Every grid pad in FX Mode, and the split views' snapshot panel, releases included.
    key = (event.column, event.pad)
    if key in layout.FX_LENGTHS:
        bars = layout.FX_LENGTHS[key]
        if event.pressed:
            return replace(state, fx_length=bars), []
        if state.fx_length == bars:
            return replace(state, fx_length=None), []
        return state, []
    # Under Shift the grid is dark and does nothing, as Mixer's faders.
    if not event.pressed or state.shift:
        return state, []
    if key in layout.FX_SLOTS:
        return _slot_press(state, layout.FX_SLOTS.index(key), False, snapshot)
    if key in layout.FX_SCENE_SLOTS:
        # Column 13 follows the scene pads.
        scene = state.window.scene + layout.FX_SCENE_SLOTS.index(key)
        if scene < snapshot.scene_count:
            return _slot_press(state, scene, True, snapshot)
    return state, []


def _slot_press(state, slot, scene, snapshot):
    stored = _stored(state, slot, scene) is not None
    # Copy over Delete, as in Session Mode.
    if state.copy or (not state.delete and not stored):
        return state, [StoreFxSnapshot(slot, scene=scene)]
    if state.delete:
        if not stored:
            return state, []
        state, save = _set(state, slot, scene, None, snapshot.scene_count)
        return state, [save, ShowMessage(f"{_name(slot, scene)} cleared")]
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
    morph = state.morph
    target = morph.slot if morph is not None and not morph.scene else None
    for slot, key in enumerate(layout.FX_SLOTS):
        if slot == target:
            frame[key] = Light(CYAN, Blink.FAST)
        elif state.fx_slots[slot] is not None:
            frame[key] = Light(CYAN, Blink.TEMPO if slot == state.fx_landed else Blink.STEADY)
    target = morph.slot if morph is not None and morph.scene else None
    for row, key in enumerate(layout.FX_SCENE_SLOTS):
        scene = state.window.scene + row
        if scene >= snapshot.scene_count:
            continue
        if scene == target:
            frame[key] = Light(LIME, Blink.FAST)
        elif scene_snapshot(state, scene) is not None:
            landed = scene == state.fx_landed_scene
            frame[key] = Light(LIME, Blink.TEMPO if landed else Blink.STEADY)
    for key, bars in layout.FX_LENGTHS.items():
        frame[key] = Light(WHITE, Blink.FAST if bars == state.fx_length else Blink.STEADY)
    return frame


def racks_read(state, event, snapshot):
    # The adapter's rack read after a store or a recall, in any mode.
    name = _name(event.slot, event.scene)
    if not event.recall:
        if not event.racks:
            return state, [ShowMessage("No racks to store")]
        value = capture(event.racks)
        state, save = _set(state, event.slot, event.scene, value, snapshot.scene_count)
        return state, [save, ShowMessage(f"{name} stored ({_count(len(event.racks), 'rack')})")]
    stored = _stored(state, event.slot, event.scene)
    if stored is None:
        return state, []
    macros, missing = _match(stored, event.racks)
    note = f", {_count(missing, 'rack')} not found" if missing else ""
    if not macros:
        return state, [ShowMessage(f"{name}: nothing to recall{note}")]
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
        return state, actions + [ShowMessage(f"{name} recalled{note}")]
    start = snapshot.song_beats
    end = event.end_beats if launch else end_beats(snapshot, event.bars)
    morph = Morph(event.slot, start, end, start, macros, scene=event.scene)
    state = replace(state, morph=morph, fx_undo_open=True)
    timing = "on launch" if launch else f"in {_count(event.bars, 'bar')}"
    message = ShowMessage(f"{name} {timing}{note}")
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
        state = _landed(replace(state, morph=None, fx_undo_open=False), morph.slot, morph.scene)
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


def launch_step(snapshot):
    # Launch quantization's length in beats, None when launches are unquantized.
    q = snapshot.launch_quantization
    if q in LAUNCH_BARS:
        return LAUNCH_BARS[q] * snapshot.signature_numerator * 4 / snapshot.signature_denominator
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
        # Fired halfway through the last boundary's step: clear of the timer's jitter.
        start = math.ceil(start / step - 1e-9) * step
        fire = start - step / 2
    actions = []
    if scene_snapshot(state, scene) is not None:
        actions.append(RecallFxSnapshot(scene, None, scene=True, end_beats=start))
    if fire <= snapshot.song_beats:
        # Live's launch quantization already starts it on time.
        return state, [FireScene(scene, legato=False), *actions]
    pending = PendingLaunch(scene, fire, snapshot.song_beats)
    message = ShowMessage(f"Scene {scene + 1} in {_count(bars, 'bar')}")
    return replace(state, pending_launch=pending), [message, *actions]


def launch_tick(state, transport):
    # On the 10 ms timer: fire the pending launch at its time. A stop or a backward jump
    # cancels it, as either lands a morph at once. Returns whether to redraw.
    pending = state.pending_launch
    now = transport.song_beats
    if not transport.is_playing or now < pending.last_beats:
        message = ShowMessage(f"Scene {pending.scene + 1} launch cancelled")
        return replace(state, pending_launch=None), [message], True
    if now >= pending.fire_beats:
        return replace(state, pending_launch=None), [FireScene(pending.scene, legato=False)], True
    return replace(state, pending_launch=replace(pending, last_beats=now)), [], False


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
