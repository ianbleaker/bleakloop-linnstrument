"""A temporary golden capture of every view's buttons, held states and hold sequences, guarding
the #116 refactor. Regenerate by hand only where a step's plan says the result changes:

PYTHONPATH=src python3 -m tests.golden.capture

It goes through engine.handle and engine.render alone, reaching each held state by pressing
today's hold pads, so it outlives the code it checks.
"""

import json
from dataclasses import fields, replace
from pathlib import Path

from BleakLoop.core import engine
from BleakLoop.core.layout import Window
from BleakLoop.core.model import (
    DrumView,
    PadPress,
    SelectedTrack,
    SequencerView,
    SeqEntry,
    SlotView,
    Snapshot,
    TrackView,
)
from BleakLoop.core.modes import BoundSlot, FaderBinding, FxRack, Mode, State

FIXTURE = Path(__file__).resolve().parent.parent / "fixtures" / "golden_layout.json"

# Today's shipped hold pads.
SHIFT = (1, 8)
DEVICE_CLIP = (16, 8)
COPY = (16, 7)
DELETE = (16, 6)
SEQ = (16, 5)
STOP = (15, 8)

SURFACE_PADS = [(column, pad) for column in (1, 15, 16) for pad in range(1, 9)]
LEFT_SPLIT_PADS = [(1, pad) for pad in range(1, 9)]


def _tracks():
    tracks = []
    for i in range(13):
        slots = tuple(
            SlotView(has_clip=(i + row) % 3 == 0, is_playing=(i + row) % 5 == 0) for row in range(6)
        )
        tracks.append(
            TrackView(
                index=i,
                name=f"T{i + 1}",
                colour=0x10 * i,
                arm=i == 1,
                mute=i == 2,
                solo=i == 3,
                has_midi_input=i < 4,
                selected=i == 0,
                slots=slots,
                set_index=i,
            )
        )
    return tuple(tracks)


SESSION_SNAP = Snapshot(
    is_playing=True,
    song_beats=0.0,
    tempo=120.0,
    metronome=True,
    session_view=True,
    track_count=20,
    scene_count=10,
    tracks=_tracks(),
    can_undo=True,
    can_redo=True,
    scene_clips=(True, False, True, False, True, False),
    selected_track=SelectedTrack(0, "T1", armed=True, clips=(True,) + (False,) * 9),
    can_capture_midi=True,
    any_muted=True,
    any_soloed=True,
    any_armed=True,
    arms=(True, False, False, False) + (False,) * 16,
    seq_entry=SeqEntry(selected=0, selected_midi=True, scene=0, has_clip=True),
)

MIDI = SequencerView(track=0, is_midi=True, has_clip=True, loop_end=16.0)
DRUMS = replace(MIDI, drum=DrumView(scroll=9, selected=36, filled=frozenset({36, 37, 40})))

STORED = (FxRack("A", "R", 0, (1.0,)),)
BOUND = BoundSlot((FaderBinding("A", 0, "D", 0, 1, "P"),), (0.5,))
SLOTS = (STORED, BOUND) + (None,) * 126

SESSION = State(fx_slots=SLOTS, window=Window(0, 0))
SEQUENCER = State(mode=Mode.SEQUENCER, seq_track=0, fx_slots=SLOTS)
LINNSTRUMENT = State(mode=Mode.LINNSTRUMENT, fx_slots=SLOTS)

# name -> (base state, snapshot, pads, kind)
VIEWS = {
    "session": (SESSION, SESSION_SNAP, SURFACE_PADS, "session"),
    "session_split": (replace(SESSION, split=True), SESSION_SNAP, SURFACE_PADS, "session"),
    "session_split_snapshots": (
        replace(SESSION, split=True, split_snapshots=True),
        SESSION_SNAP,
        SURFACE_PADS,
        "session",
    ),
    "mixer": (replace(SESSION, mixer=True), SESSION_SNAP, SURFACE_PADS, "session"),
    "mixer_split": (replace(SESSION, mixer=True, mixer_split=True), SESSION_SNAP, SURFACE_PADS, "session"),
    "mixer_split_snapshots": (
        replace(SESSION, mixer=True, mixer_split=True, split_snapshots=True),
        SESSION_SNAP,
        SURFACE_PADS,
        "session",
    ),
    "fx": (replace(SESSION, fx=True), SESSION_SNAP, SURFACE_PADS, "session"),
    "fx_bind_undo": (
        replace(SESSION, fx=True, bind_undo=((1, BOUND.params[0], 0.5, "added"),), bind_undo_at=1.0),
        SESSION_SNAP,
        SURFACE_PADS,
        "session",
    ),
    "sequencer": (SEQUENCER, replace(SESSION_SNAP, sequencer=MIDI), SURFACE_PADS, "sequencer"),
    "sequencer_settings": (
        replace(SEQUENCER, seq_settings=True),
        replace(SESSION_SNAP, sequencer=MIDI),
        SURFACE_PADS,
        "sequencer",
    ),
    "sequencer_drums": (SEQUENCER, replace(SESSION_SNAP, sequencer=DRUMS), SURFACE_PADS, "sequencer"),
    "linnstrument": (LINNSTRUMENT, SESSION_SNAP, LEFT_SPLIT_PADS, "linnstrument"),
    "linnstrument_scenes": (replace(LINNSTRUMENT, scene_page=True), SESSION_SNAP, LEFT_SPLIT_PADS, "linnstrument"),
}

COMMON = {
    "none": (),
    "shift": (SHIFT,),
    "device_clip": (DEVICE_CLIP,),
    "copy": (COPY,),
    "delete": (DELETE,),
    "shift+device_clip": (SHIFT, DEVICE_CLIP),
    "shift+copy": (SHIFT, COPY),
    "shift+delete": (SHIFT, DELETE),
}
HELD = {
    "session": {**COMMON, "stop": (STOP,), "seq": (SEQ,), "shift+stop": (SHIFT, STOP)},
    "sequencer": COMMON,
    "linnstrument": {"none": (), "shift": (SHIFT,)},
}


def light(value):
    return f"{value.colour}/{value.blink.name}"


def frame(state, snapshot):
    rendered = engine.render(state, snapshot)
    return {f"{c},{p}": light(rendered[c, p]) for c, p in sorted(rendered)}


def diff(before, after):
    return {
        field.name: repr(getattr(after, field.name))
        for field in fields(State)
        if getattr(before, field.name) != getattr(after, field.name)
    }


def step(state, snapshot, key, pressed):
    after, actions = engine.handle(state, PadPress(*key, pressed), snapshot)
    record = {"event": f"{key[0]},{key[1]} {'press' if pressed else 'release'}", "state": diff(state, after)}
    record["actions"] = [repr(action) for action in actions]
    return after, record


def hold(state, snapshot, keys):
    for key in keys:
        state, _ = engine.handle(state, PadPress(*key, True), snapshot)
    return state


def run_sequence(state, snapshot, events):
    records = []
    for key, pressed in events:
        state, record = step(state, snapshot, key, pressed)
        records.append(record)
    return state, {"steps": records, "frame": frame(state, snapshot)}


def views():
    out = {}
    for name, (base, snapshot, pads, kind) in VIEWS.items():
        for held, keys in HELD[kind].items():
            state = hold(base, snapshot, keys)
            prefix = f"{name}|{held}"
            out[f"{prefix}|frame"] = frame(state, snapshot)
            for key in pads:
                pressed, press = step(state, snapshot, key, True)
                _, release = step(pressed, snapshot, key, False)
                out[f"{prefix}|{key[0]},{key[1]}"] = [press, release]
    return out


def press_release(key):
    return [(key, True), (key, False)]


def sequences():
    out = {}
    session, _, _, _ = VIEWS["session"]
    sequencer, seq_snap, _, _ = VIEWS["sequencer"]
    tap = [(DEVICE_CLIP, True), (DEVICE_CLIP, False)]
    used = [(DEVICE_CLIP, True), *press_release((16, 7)), (DEVICE_CLIP, False)]
    for name in ("session", "mixer", "fx", "sequencer"):
        base, snapshot, _, _ = VIEWS[name]
        for clip_view in (False, True):
            snap = replace(snapshot, clip_view=clip_view)
            _, result = run_sequence(base, snap, tap)
            assert any("ToggleDetailView" in a for a in result["steps"][-1]["actions"]), name
            out[f"seq|{name}|device_clip_tap|clip_view={clip_view}"] = result
        _, result = run_sequence(base, snapshot, used)
        assert not any("ToggleDetailView" in a for a in result["steps"][-1]["actions"]), name
        out[f"seq|{name}|device_clip_used"] = result
    # Device/Clip + a snapshot slot: slot 1 stored Set-wide, slot 2 bound.
    for name in ("fx", "session_split_snapshots", "mixer_split_snapshots"):
        base, snapshot, _, _ = VIEWS[name]
        for slot in ((11, 1), (11, 2), (11, 3), (14, 1)):
            events = [(DEVICE_CLIP, True), (slot, True), (slot, False), (DEVICE_CLIP, False)]
            _, result = run_sequence(base, snapshot, events)
            out[f"seq|{name}|device_clip+{slot[0]},{slot[1]}"] = result
            if slot in ((11, 1), (11, 2)):
                assert result["steps"][1]["state"].get("fx_holds"), (name, slot)
        for slot in ((11, 1), (11, 2)):
            _, result = run_sequence(base, snapshot, press_release(slot))
            out[f"seq|{name}|{slot[0]},{slot[1]}"] = result
    # Seq held + a clip, a scene, a Navigation pad.
    for target in ((2, 1), (2, 2), (15, 1), (16, 1), (16, 8), (1, 1)):
        events = [(SEQ, True), (target, True), (target, False), (SEQ, False)]
        state, result = run_sequence(session, SESSION_SNAP, events)
        if target == (2, 1):
            assert state.mode is Mode.SEQUENCER
        out[f"seq|session|seq+{target[0]},{target[1]}"] = result
    _, result = run_sequence(session, SESSION_SNAP, [(SEQ, True), (SEQ, False)])
    out["seq|session|seq_tap"] = result
    # The scene page opened under Shift stays open once Shift is let go; then a scene, and Back.
    linnstrument, _, _, _ = VIEWS["linnstrument"]
    for name, base, snapshot in (
        ("linnstrument", linnstrument, SESSION_SNAP),
        ("sequencer", sequencer, seq_snap),
    ):
        events = [(SHIFT, True), *press_release((1, 7)), (SHIFT, False)]
        state, result = run_sequence(base, snapshot, events)
        assert state.scene_page, name
        out[f"seq|{name}|scene_page_under_shift"] = result
        _, result = run_sequence(state, snapshot, press_release((1, 2)))
        out[f"seq|{name}|scene_page_scene"] = result
        _, result = run_sequence(state, snapshot, press_release((1, 8)))
        out[f"seq|{name}|scene_page_back"] = result
    # Shift held, then a hold's pad: it gives way to the Shift layer's button.
    for name in ("session", "mixer", "fx", "sequencer"):
        base, snapshot, _, _ = VIEWS[name]
        for key in (DEVICE_CLIP, COPY, DELETE, SEQ, STOP):
            events = [(SHIFT, True), (key, True), (SHIFT, False), (key, False)]
            _, result = run_sequence(base, snapshot, events)
            out[f"seq|{name}|shift_then_{key[0]},{key[1]}_shift_up_first"] = result
    # Linnstrument Mode and back.
    for name in ("session", "mixer", "fx", "sequencer"):
        base, snapshot, _, _ = VIEWS[name]
        state, result = run_sequence(base, snapshot, press_release((1, 7)))
        out[f"seq|{name}|linnstrument_mode"] = result
        if name != "sequencer" or state.mode is Mode.LINNSTRUMENT:
            _, result = run_sequence(state, snapshot, press_release((1, 7)))
            out[f"seq|{name}|linnstrument_mode_back"] = result
    return out


def run():
    return {**views(), **sequences()}


def main():
    FIXTURE.write_text(json.dumps(run(), indent=0, sort_keys=True) + "\n")
    print(f"wrote {FIXTURE}")


if __name__ == "__main__":
    main()
