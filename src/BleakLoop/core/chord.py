"""Chord Mode: hold quality and extension pads, then press a degree or piano key for a chord.

Live's Chord MIDI effect, inserted on the armed track, plays the chord: each chord pad is
translated to its chord's root, and the device's shifts build the rest around it. Track
indexes are song.tracks indexes.
"""

from dataclasses import replace

from . import arm, column_1, controls, faders, fx, harmony, layout, mixer, modes, values
from .leds import BLUE, CYAN, GREEN, OFF, ORANGE, WHITE, YELLOW, Blink, Light
from .model import (
    ChordView,
    EnterMode,
    InsertChord,
    PadPress,
    RemoveChord,
    SetChordDevice,
    SetScale,
    ShowMessage,
    WriteChord,
)
from .modes import Mode

NEEDS_MIDI = "Chord needs a MIDI track"
SESSION_ONLY = "Chord notes are written in Session clips only"
MAJ, MIN = (next(k for k, q in layout.CHORD_QUALITIES.items() if q == name) for name in ("maj", "min"))
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
    state = modes.enter(state, Mode.CHORD)
    if state.chord_remove_pending and state.chord_device_track == view.track:
        # Left with a pad held and back on the same track: the device is still there.
        state = replace(state, chord_remove_pending=False)
    else:
        state, more = _remove(state)
        actions += more
        state, more = _insert(state, view.track)
        actions += more
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
    if track is None:
        return state, []
    state, actions = fx.close_morph_step(state)
    return state, actions + [RemoveChord(track)]


def _insert(state, track, again=False):
    # A running morph's undo step closes first, so undoing the morph leaves the device alone.
    state, actions = fx.close_morph_step(state)
    state = replace(state, chord_device_track=track, chord_setting=None)
    return state, actions + [InsertChord(track, again)]


def release_hold(state, event):
    # A held chord pad's release, in any mode: the press it ends may be from Chord Mode.
    # Returns (state, actions), with actions None when the pad wasn't a held chord pad. A
    # recorded press writes the chord's other notes next to the root Live recorded.
    key = (event.column, event.pad)
    ended = [h for h in state.chord_holds if h[:2] == key]
    if not ended:
        return state, None
    state = replace(state, chord_holds=tuple(h for h in state.chord_holds if h[:2] != key))
    actions = []
    for _, _, pitches, take in ended:
        if take is not None:
            # A running morph's undo step closes first, as before any other clip edit.
            state, more = fx.close_morph_step(state)
            actions += more + [WriteChord(*take, pitches)]
    return state, actions


def sync(state, snapshot):
    # On every display tick in Chord Mode, in Linnstrument Mode entered from it, and while a
    # removal waits for the held pads.
    if state.chord_remove_pending:
        if not state.chord_holds:
            return _remove(state)
        return state, []
    view = snapshot.chord or ChordView()
    if state.chord_told_arrangement and not view.arrangement:
        # The Arrangement take ended: the next one is told again.
        state = replace(state, chord_told_arrangement=False)
    actions = []
    if not state.chord_holds:
        # A held pad's chord ends on the device that started it: the move waits for it.
        state, actions, moved = arm.follow(state, snapshot, view, NEEDS_MIDI)
        if moved:
            state, more = _remove(state)
            actions += more
            state, more = _insert(state, state.arm_track)
            actions += more
        elif view.track is not None and view.track == state.chord_device_track:
            if not view.device_present:
                # Undo took the insert back.
                state, more = _insert(state, view.track, again=True)
                actions += more
    if state.mode is Mode.LINNSTRUMENT:
        # The player plays the track: its notes pass through unchanged.
        state, more = _set_device(state, REST)
    else:
        state, more = _set_device(state, template(state, view))
    return state, actions + more


# Pads


def chord_key(column, pad):
    # ("degree", semitone above the key root) or ("piano", (pair, semitone)), else None.
    if pad == 1 and column in layout.CHORD_DEGREE_COLUMNS:
        return "degree", column - layout.CHORD_DEGREE_COLUMNS[0]
    if column in layout.CHORD_PIANO_COLUMNS and pad in layout.CHORD_PIANO_PADS:
        keys = harmony.WHITES if pad % 2 == 0 else harmony.BLACKS
        semitone = keys[column - layout.CHORD_PIANO_COLUMNS[0]]
        if semitone is not None:
            return "piano", ((layout.ROWS - pad) // 2, semitone)
    return None


def root_note(state, view, column, pad):
    # The note a chord pad's chord is built on, sounding or not; None off the chord pads.
    found = chord_key(column, pad)
    if found is None:
        return None
    kind, place = found
    if kind == "degree":
        return 60 + 12 * state.chord_octave + key_of(view).root + place
    pair, semitone = place
    return 48 + 12 * state.chord_octave + 12 * pair + semitone


def pad_note(state, view, column, pad):
    # The note a chord pad is translated to: None while Shift is held (its layer sets the key),
    # off a MIDI track, and for an out-of-key pad while no quality is held, which is silent.
    if state.mode is not Mode.CHORD or state.shift or view.track is None or not view.is_midi:
        return None
    note = root_note(state, view, column, pad)
    if note is None or not 0 <= note <= 127:
        return None
    if not state.chord_qualities and key_of(view).degree_of(note % 12) is None:
        return None
    return note


# Input


def handle(state, event, snapshot):
    if not isinstance(event, PadPress):
        return state, []
    view = snapshot.chord or ChordView()
    key = (event.column, event.pad)
    if not event.pressed:
        state, actions = release_hold(state, event)
        if actions is not None:
            return state, actions
    if key == layout.SHIFT:
        return column_1.handle(state, event, snapshot)
    if event.column == layout.NAV_COLUMN:
        return _nav(state, event, snapshot)
    if key in layout.CHORD_QUALITIES or key in layout.CHORD_EXTENSIONS:
        return _modifier(state, event, view)
    if not event.pressed:
        return state, []
    if event.column == 1:
        return column_1.handle(state, event, snapshot)
    if state.shift:
        return _shift(state, key, view)
    if key in (layout.CHORD_INV, layout.CHORD_SPREAD, layout.CHORD_BASS):
        return _voicing(state, key, view)
    if key in (layout.CHORD_OCT_UP, layout.CHORD_OCT_DOWN):
        return _octave(state, 1 if key == layout.CHORD_OCT_UP else -1)
    if chord_key(*key) is not None:
        return _chord_press(state, event, view)
    return state, []


def _modifier(state, event, view):
    key = (event.column, event.pad)
    if key in layout.CHORD_QUALITIES:
        if state.shift and event.pressed:
            return _shift(state, key, view)
        quality = layout.CHORD_QUALITIES[key]
        qualities = tuple(q for q in state.chord_qualities if q != quality)
        state = replace(state, chord_qualities=qualities + ((quality,) if event.pressed else ()))
    else:
        extension = layout.CHORD_EXTENSIONS[key]
        extensions = state.chord_extensions - {extension}
        if event.pressed:
            extensions |= {extension}
        state = replace(state, chord_extensions=extensions)
    return _set_device(state, template(state, view))


def _voicing(state, key, view):
    if key == layout.CHORD_INV:
        _, _, tones = harmony.shape(key_of(view), state.chord_qualities, state.chord_extensions)
        # The 3rd inversion only for 4+ note chords.
        state = replace(state, chord_inv=(state.chord_inv + 1) % (4 if len(tones) > 3 else 3))
        message = f"Inversion: {harmony.INVERSIONS[state.chord_inv]}"
    elif key == layout.CHORD_SPREAD:
        state = replace(state, chord_spread=(state.chord_spread + 1) % len(harmony.SPREADS))
        message = f"Spread: {harmony.SPREADS[state.chord_spread]}"
    else:
        state = replace(state, chord_bass=not state.chord_bass)
        message = f"Bass {'ON' if state.chord_bass else 'OFF'}"
    state, actions = _set_device(state, template(state, view))
    return state, actions + [ShowMessage(message)]


def _octave(state, step):
    if state.chord_holds:
        # A held pad keeps its translation: its chord must end where it started.
        return state, []
    octave = state.chord_octave + step
    if octave not in values.CHORD_OCTAVES:
        return state, []
    return replace(state, chord_octave=octave), [ShowMessage(f"Octave {octave}")]


def _shift(state, key, view):
    # Shift + a piano key sets the key's root; Shift + Maj or Min the scale, Scale Mode on.
    current = key_of(view)
    if key in layout.CHORD_QUALITIES:
        quality = layout.CHORD_QUALITIES[key]
        if quality not in ("maj", "min"):
            return state, []
        name = "Major" if quality == "maj" else "Minor"
        text = harmony.Key(current.root, current.intervals, name).text
        return state, [SetScale(name=name, mode_on=True), ShowMessage(f"Key: {text}")]
    found = chord_key(*key)
    if found is None or found[0] != "piano":
        return state, []
    root = found[1][1] % 12
    text = harmony.Key(root, current.intervals, current.name).text
    return state, [SetScale(root=root), ShowMessage(f"Key: {text}")]


def _chord_press(state, event, view):
    key = key_of(view)
    root = root_note(state, view, event.column, event.pad)
    if view.track is None or not view.is_midi or not 0 <= root <= 127:
        return state, []
    played = harmony.chord(key, root, state.chord_qualities, state.chord_extensions)
    if played is None:
        return state, [ShowMessage(harmony.hint(key, (root - key.root) % 12))]
    voicing = harmony.voice(played, state.chord_inv, state.chord_spread, state.chord_bass)
    take = None
    if view.recording and view.scene is not None:
        take = (view.track, view.scene, root, view.position)
    hold = (event.column, event.pad, harmony.pitches(key, played, voicing), take)
    state = replace(state, chord_holds=state.chord_holds + (hold,))
    actions = [ShowMessage(harmony.describe(key, played, voicing))]
    if view.arrangement and not state.chord_told_arrangement:
        # Once per take: Live records only the root there.
        state = replace(state, chord_told_arrangement=True)
        actions.append(ShowMessage(SESSION_ONLY))
    return state, actions


def _nav(state, event, snapshot):
    # Column 16, as Sequencer Mode's, with Copy, Delete and Seq dark and inert.
    key = (event.column, event.pad)
    shift_layer = state.shift
    if key == layout.DEVICE_CLIP and not (shift_layer and event.pressed):
        return controls.device_clip(state, event)
    if state.device_clip and event.pressed:
        return controls.device_clip_layer(state, key)
    if not event.pressed:
        return state, []
    if shift_layer:
        if key in layout.WINDOW_MOVES:
            return controls.move_window(state, layout.WINDOW_MOVES[key], snapshot)
        if key in layout.TEMPO_STEPS:
            return state, controls.tempo_step(snapshot, layout.TEMPO_STEPS[key])
        if key == layout.FADER_SOURCE:
            return controls.toggle_fader_source(state)
        return state, []
    if key in (layout.CHORD, layout.SESSION, layout.MIXER, layout.FX):
        return leave(state, snapshot, layout.SESSION if key == layout.CHORD else key)
    return state, []


def render(state, snapshot):
    view = snapshot.chord or ChordView()
    key = key_of(view)
    frame = {
        (column, pad): Light(OFF)
        for column in range(1, layout.COLUMNS)
        for pad in range(1, layout.ROWS + 1)
    }
    frame.update(column_1.render(state, snapshot))
    sounding = set()  # MIDI notes of every held chord
    roots = set()
    for column, pad, pitches, _ in state.chord_holds:
        sounding |= set(pitches)
        roots.add(root_note(state, view, column, pad))
    _render_modifiers(frame, state, view)
    _render_degrees(frame, key, roots)
    _render_piano(frame, state, view, key, sounding, roots)
    for pad_key, step in ((layout.CHORD_OCT_UP, 1), (layout.CHORD_OCT_DOWN, -1)):
        movable = state.chord_octave + step in values.CHORD_OCTAVES
        frame[pad_key] = Light(WHITE if movable else OFF)
    _render_nav(frame, state)
    return frame


def _render_modifiers(frame, state, view):
    if state.shift:
        # Shift + Maj or Min sets the scale: the current one cyan.
        name = view.scale.name
        frame[MAJ] = Light(CYAN if name == "Major" else WHITE)
        frame[MIN] = Light(CYAN if name == "Minor" else WHITE)
    else:
        for pad_key, quality in layout.CHORD_QUALITIES.items():
            held = Blink.FAST if quality in state.chord_qualities else Blink.STEADY
            frame[pad_key] = Light(harmony.QUALITIES[quality][3], held)
        for pad_key, extension in layout.CHORD_EXTENSIONS.items():
            held = Blink.FAST if extension in state.chord_extensions else Blink.STEADY
            frame[pad_key] = Light(WHITE, held)
    frame[layout.CHORD_INV] = Light(CYAN)
    frame[layout.CHORD_SPREAD] = Light(CYAN)
    frame[layout.CHORD_BASS] = Light(CYAN if state.chord_bass else OFF)


def _render_degrees(frame, key, roots):
    # Each degree in its quality's colour, green while its chord sounds.
    playing = {(root - key.root) % 12 for root in roots}
    for column in layout.CHORD_DEGREE_COLUMNS:
        semitone = column - layout.CHORD_DEGREE_COLUMNS[0]
        d = key.degree_of(key.root + semitone)
        if semitone in playing:
            colour = GREEN
        elif not key.is_heptatonic:
            colour = ORANGE if d is not None else OFF
        elif d is not None:
            colour = harmony.QUALITIES[key.diatonic_quality(d)][3]
        else:
            colour = harmony.QUALITIES[key.borrowed_quality(semitone)][3]
        frame[(column, 1)] = Light(colour)


def _render_piano(frame, state, view, key, sounding, roots):
    for column in layout.CHORD_PIANO_COLUMNS:
        for pad in layout.CHORD_PIANO_PADS:
            note = root_note(state, view, column, pad)
            if note is None:
                continue
            pc = note % 12
            if state.shift:
                colour = CYAN if pc == key.root else WHITE
            elif note in roots:
                colour = GREEN
            elif note in sounding:
                colour = YELLOW
            elif pc == key.root:
                colour = CYAN
            else:
                colour = WHITE if key.degree_of(pc) is not None else OFF
            frame[(column, pad)] = Light(colour)


def _render_nav(frame, state):
    # As Sequencer Mode's, with Copy, Delete and Seq dark.
    if state.shift:
        for pad_key in layout.WINDOW_MOVES:
            frame[pad_key] = Light(YELLOW)
        for pad_key in layout.TEMPO_STEPS:
            frame[pad_key] = Light(GREEN)
        frame[layout.FADER_SOURCE] = Light(ORANGE)
    else:
        for pad_key in (layout.SESSION, layout.MIXER, layout.FX):
            frame[pad_key] = Light(CYAN)
        frame[layout.CHORD] = Light(BLUE)
        frame[layout.DEVICE_CLIP] = Light(ORANGE)
    if state.device_clip:
        controls.render_device_clip_layer(frame)
