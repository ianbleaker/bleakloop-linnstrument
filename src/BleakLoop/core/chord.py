"""Chord Mode: hold quality and extension pads, then press a degree or piano key for a chord.

Live's Chord MIDI effect, inserted on the armed track, plays the chord: each chord pad is
translated to its chord's root, and the device's shifts build the rest around it. Track
indexes are song.tracks indexes.
"""

from dataclasses import replace

from . import arm, column_1, controls, faders, fx, harmony, layout, mixer, modes
from .leds import OFF, Light
from .model import (
    ChordView,
    EnterMode,
    InsertChord,
    PadPress,
    RemoveChord,
    SetChordDevice,
    ShowMessage,
)
from .modes import Mode

NEEDS_MIDI = "Chord needs a MIDI track"
REST = ((0,) * harmony.SHIFTS, False)  # every shift off: notes pass through unchanged


def key_of(view):
    scale = view.scale
    return harmony.Key(scale.root, scale.intervals or harmony.MAJOR, scale.name or "Major")


def template(state, view):
    # The device's (shifts, scale_aware) for the next press: the held pads' chord shape.
    mode, quality, tones = harmony.shape(
        key_of(view), state.chord_qualities, state.chord_extensions
    )
    shape = harmony.Chord(0, mode, quality or "maj", tones, 0)
    voicing = harmony.voice(shape, state.chord_inv, state.chord_spread, state.chord_bass)
    return harmony.shifts(shape, voicing)


def _set_device(state, setting):
    # A SetChordDevice when the setting changed since the last one sent.
    track = state.chord_device_track
    if track is None or state.chord_setting == (track, *setting):
        return state, []
    return replace(state, chord_setting=(track, *setting)), [SetChordDevice(track, *setting)]


# Entry and leaving


def enter(state, snapshot):
    view = snapshot.chord
    if view is None or view.track is None or not view.is_midi:
        return state, [ShowMessage(NEEDS_MIDI)]
    state, actions = mixer.reset(state)
    state, more = faders.reset(state)
    actions += more
    state, more = fx.close_morph_step(state)
    actions += more
    state, more = arm.take(state, snapshot, view.track)
    actions += more
    old, pending = state.chord_device_track, state.chord_remove_pending
    state = modes.enter(state, Mode.CHORD)
    if pending and old == view.track:
        # Left with a pad held and back on the same track: the device is still there.
        state = replace(state, chord_remove_pending=False)
    else:
        if pending:
            actions.append(RemoveChord(old))
        actions.append(InsertChord(view.track))
        state = replace(
            state,
            chord_device_track=view.track,
            chord_remove_pending=False,
            chord_setting=None,
        )
    state, more = _set_device(state, template(state, view))
    message = ShowMessage(f"Chord: {key_of(view).text}")
    return state, actions + more + [EnterMode(Mode.CHORD), message]


def leave(state, snapshot, to=layout.SESSION):
    # To Session, Mixer or FX, putting the arms back. The device goes once no chord pad is
    # held, so a sounding chord's notes end as they started.
    state, actions = _set_device(state, REST)
    holds = state.chord_holds
    if holds:
        state = replace(state, chord_remove_pending=True)
    else:
        state, more = _remove(state)
        actions += more
    actions += arm.restore(state, snapshot.arms)
    state = modes.enter(arm.release(state), Mode.SESSION)
    # Kept so the engine sees the held pads' releases outside Chord Mode.
    state = replace(state, chord_holds=holds)
    actions.append(EnterMode(Mode.SESSION))
    if to == layout.SESSION:
        return state, actions
    state, more = (mixer.toggle if to == layout.MIXER else fx.toggle)(state)
    # The new mode's width can be wider than Session's split view.
    window = layout.move_window(
        state.window,
        0,
        0,
        snapshot.track_count,
        snapshot.scene_count,
        controls.window_tracks(state),
    )
    return replace(state, window=window), actions + more


def _remove(state):
    track = state.chord_device_track
    state = replace(
        state, chord_device_track=None, chord_remove_pending=False, chord_setting=None
    )
    return state, [] if track is None else [RemoveChord(track)]


def release_hold(state, event):
    # A held chord pad's release, in any mode: the press it ends may be from Chord Mode.
    key = (event.column, event.pad)
    holds = tuple(h for h in state.chord_holds if h[:2] != key)
    if holds == state.chord_holds:
        return state, False
    return replace(state, chord_holds=holds), True


def sync(state, snapshot):
    # On every display tick in Chord Mode, in Linnstrument Mode entered from it, and while a
    # removal waits for the held pads.
    if state.chord_remove_pending:
        if not state.chord_holds:
            return _remove(state)
        return state, []
    view = snapshot.chord or ChordView()
    actions = []
    if not state.chord_holds:
        # A held pad's chord ends on the device that started it: the move waits for it.
        state, actions, moved = arm.follow(state, snapshot, view, NEEDS_MIDI)
        if moved:
            state, more = _remove(state)
            actions += more + [InsertChord(state.arm_track)]
            state = replace(state, chord_device_track=state.arm_track)
        elif view.track is not None and view.track == state.chord_device_track:
            if not view.device_present:
                # Undo took the insert back.
                actions.append(InsertChord(view.track, again=True))
                state = replace(state, chord_setting=None)
    if state.mode is Mode.LINNSTRUMENT:
        # The player plays the track: its notes pass through unchanged.
        state, more = _set_device(state, REST)
    else:
        state, more = _set_device(state, template(state, view))
    return state, actions + more


# Input


def handle(state, event, snapshot):
    if not isinstance(event, PadPress):
        return state, []
    if event.column == 1:
        return column_1.handle(state, event, snapshot)
    return state, []


def render(state, snapshot):
    frame = {
        (column, pad): Light(OFF)
        for column in range(1, layout.COLUMNS)
        for pad in range(1, layout.ROWS + 1)
    }
    frame.update(column_1.render(state, snapshot))
    return frame
