"""Sequencer Mode: 64 steps on the highlighted clip, with note pads to pick and audition notes.

Steps are counted from clip time 0. Step s of the page in view is at column 3 + s % 8, pad
1 + s // 8, top row first. Track indexes are song.tracks indexes.
"""

import math
from dataclasses import replace

from . import buttons, catalogue, controls, faders, functions, fx, global_column, layout, mixer, modes, values
from .leds import (
    BLUE,
    CYAN,
    GREEN,
    MAGENTA,
    OFF,
    ORANGE,
    PINK,
    RED,
    WHITE,
    YELLOW,
    Blink,
    Light,
)
from .model import (
    BeginUndoStep,
    DuplicateLoop,
    EditNotes,
    EndUndoStep,
    EnterMode,
    HighlightSlot,
    ModifyNotes,
    PadPress,
    RemovePitch,
    SelectDrumPad,
    SequencerView,
    SetArms,
    SetDrumScroll,
    SetLoop,
)
from .modes import Mode, StepHold

STEP_COLUMNS = len(layout.SEQ_STEP_COLUMNS)
STEPS = STEP_COLUMNS * layout.ROWS  # per page
NOTE_COLUMNS = len(layout.SEQ_NOTE_COLUMNS)
# Float error in note times and the play position: a time this close to a boundary is past it.
EPSILON = 1e-6
RATE_NAMES = {1.0: "1/4", 0.5: "1/8", 0.25: "1/16", 0.125: "1/32"}
NOTE_NAMES = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")
NATURALS = {0, 2, 4, 5, 7, 9, 11}
MAX_BASE = 96  # the melodic note pads' highest base: the top right is then 127
MAX_SCROLL = 28  # a Drum Rack's last scroll position: 32 rows of 4, 4 in view


# Step maths


def step_length(state):
    # In beats.
    return state.seq_rate * (2 / 3 if state.seq_triplet else 1)


def step_key(s):
    # The (column, pad) of step s of the page in view, 0-63.
    return layout.SEQ_STEP_COLUMNS[0] + s % STEP_COLUMNS, 1 + s // STEP_COLUMNS


def step_of(key):
    # The step of the page in view at (column, pad).
    column, pad = key
    return (pad - 1) * STEP_COLUMNS + column - layout.SEQ_STEP_COLUMNS[0]


def step_of_time(start, length):
    # The global step a note starting at start belongs to: a note past a step's midpoint
    # belongs to the next step.
    return math.floor(start / length + 0.5 + EPSILON)


def page_span(state):
    # A page's length in beats.
    return STEPS * step_length(state)


def view_page(state, view):
    # With Follow on while the clip plays, the page holding the play position.
    if state.seq_follow and view.is_playing:
        return playhead(state, view) // STEPS
    return state.seq_page


def notes_in_step(view, g, length):
    return tuple(note for note in view.notes if step_of_time(note.start, length) == g)


def pad_note(state, view, column, pad):
    # The note of a note pad: chromatic, a row up is +4, the base at the bottom left. On a
    # Drum Rack the base is Live's rack scroll, so pads 5-8 are its visible 16. None while
    # the settings show, off a MIDI track, and above 127.
    if state.seq_settings or not view.is_midi or column not in layout.SEQ_NOTE_COLUMNS:
        return None
    base = NOTE_COLUMNS * view.drum.scroll if view.drum is not None else state.seq_base
    note = base + (layout.ROWS - pad) * NOTE_COLUMNS + column - layout.SEQ_NOTE_COLUMNS[0]
    return note if 0 <= note <= 127 else None


def playhead(state, view):
    # The global step of the play position, or None while the clip isn't playing.
    if not view.is_playing:
        return None
    return math.floor(view.position / step_length(state) + EPSILON)


def selected_pitch(state, view):
    # On a Drum Rack, Live's selected drum pad; seq_pitch only while none is selected.
    if view.drum is not None and view.drum.selected is not None:
        return view.drum.selected
    return state.seq_pitch


def _inert(state, view, g, snapshot):
    # A step at or past the loop end, or past a new clip's length, takes no edits.
    if view.track is None or not view.is_midi:
        return True
    end = view.loop_end if view.has_clip else _create_length(state, snapshot)
    return g * step_length(state) >= end - EPSILON


def _create_length(state, snapshot):
    # A new clip is Fixed Length long, 1 bar while it's off.
    return controls.record_length(state.fixed_length or 1, snapshot)


# Entry and leaving


def enter_on_slot(state, track, scene, snapshot):
    # Seq + a clip slot: track is the slot's TrackView.
    if not track.has_midi_input or track.is_foldable or track.set_index is None:
        return state, buttons.refuse("seq", "needs_midi")
    state, actions = _enter(state, snapshot, track.set_index)
    return state, [HighlightSlot(track.set_index, scene)] + actions


def enter_by_tap(state, snapshot):
    # An empty highlighted slot gives way to the Detail-view clip, then the playing clip.
    entry = snapshot.seq_entry
    if entry is None or entry.selected is None or not entry.selected_midi:
        return state, buttons.refuse("seq", "needs_midi")
    track, highlight = entry.selected, []
    if not entry.has_clip:
        if entry.detail is not None:
            track = entry.detail[0]
            highlight = [HighlightSlot(*entry.detail)]
        elif entry.playing_scene is not None:
            highlight = [HighlightSlot(entry.selected, entry.playing_scene)]
    state, actions = _enter(state, snapshot, track)
    return state, highlight + actions


def _enter(state, snapshot, track):
    # Arm the target alone, remembering every track's arm and what BleakLoop set.
    state, actions = mixer.reset(state)
    state, more = faders.reset(state)
    actions += more
    arms = snapshot.arms
    wanted = tuple(None if arm is None else i == track for i, arm in enumerate(arms))
    changes = tuple(
        (i, want)
        for i, (arm, want) in enumerate(zip(arms, wanted))
        if arm is not None and arm != want
    )
    state = replace(
        state, seq_saved_arms=arms, seq_set_arms=wanted, seq_track=track, seq_refused=None
    )
    state = modes.enter(state, Mode.SEQUENCER)
    if changes:
        actions.append(SetArms(changes))
    return state, actions + [EnterMode(Mode.SEQUENCER), *buttons.say("seq", "entered")]


def leave(state, snapshot):
    # Back to Session, putting the arms back.
    state, actions = _close_slide(state)
    actions += restore_arms(state, snapshot.arms)
    state = replace(
        state, seq_saved_arms=None, seq_set_arms=None, seq_track=None, seq_refused=None
    )
    state = modes.enter(state, Mode.SESSION)
    return state, actions + [EnterMode(Mode.SESSION)]


def restore_arms(state, arms):
    # On leaving, and on unload while the arms are saved (Linnstrument Mode keeps them). A
    # track's arm goes back only if it's still what BleakLoop set; with the track count
    # changed, the indexes don't line up and nothing is restored.
    saved, wanted = state.seq_saved_arms, state.seq_set_arms
    if saved is None or wanted is None or not len(saved) == len(arms) == len(wanted):
        return []
    changes = tuple(
        (i, before)
        for i, (before, set_, now) in enumerate(zip(saved, wanted, arms))
        if now is not None and before is not None and now == set_ and now != before
    )
    return [SetArms(changes)] if changes else []


def sync(state, snapshot):
    # On every display tick: the arm follows Live's selected track to any MIDI track.
    view = snapshot.sequencer
    if view is None:
        return state, []
    if view.track is not None and view.track == state.seq_track:
        return replace(state, seq_refused=None), []
    if view.track is None or not view.is_midi:
        refused = -1 if view.track is None else view.track
        if state.seq_refused == refused:
            return state, []
        return replace(state, seq_refused=refused), buttons.refuse("seq", "needs_midi")
    state, actions = _close_slide(state)
    old, new, arms = state.seq_track, view.track, snapshot.arms
    changes = []
    if old is not None and old < len(arms) and arms[old]:
        changes.append((old, False))
    if new < len(arms) and arms[new] is False:
        changes.append((new, True))
    wanted = state.seq_set_arms
    if wanted is not None:
        wanted = list(wanted)
        for i, arm in ((old, False), (new, True)):
            if i is not None and i < len(wanted) and wanted[i] is not None:
                wanted[i] = arm
        wanted = tuple(wanted)
    state = replace(
        state,
        seq_track=new,
        seq_set_arms=wanted,
        seq_refused=None,
        seq_holds=(),
        seq_copy_source=None,
        seq_follow=True,
        seq_page=0,
    )
    if changes:
        actions.append(SetArms(tuple(changes)))
    return state, actions


def _close_slide(state):
    if not state.seq_undo_open:
        return state, []
    return replace(state, seq_undo_open=False), [EndUndoStep()]


def _close_morph_step(state):
    # Before any write to the Set: a morph's undo step closes first; the morph carries on.
    if not state.fx_undo_open:
        return state, []
    return replace(state, fx_undo_open=False), [EndUndoStep()]


def _write(state, writes):
    # Edits and loop changes: dropped while a slide's undo step is open.
    if state.seq_undo_open or not writes:
        return state, []
    state, actions = _close_morph_step(state)
    return state, actions + list(writes)


# Input


def handle(state, event, snapshot):
    if not isinstance(event, PadPress):
        return state, []
    view = snapshot.sequencer or SequencerView()
    key = (event.column, event.pad)
    if not event.pressed and any((h.column, h.pad) == key for h in state.seq_holds):
        # A held step ends on its cell's release, wherever the finger slid to.
        return _release_step(state, event, view, snapshot)
    normal = controls.at(controls.sections(state), key)
    held = normal[1] if normal is not None else None
    if held == "shift":
        return global_column.handle(state, event, snapshot)
    # Under Shift, a hold's press gives way to the Shift layer's button on its pad.
    shift_layer = state.shift and not state.copy and not state.delete
    shifted = shift_layer and event.pressed and layout.SEQUENCER_NAV_SHIFT.at(key) is not None
    if held == "device_clip" and not shifted:
        return controls.device_clip(state, event, snapshot)
    if state.device_clip and event.pressed and key in controls.navigation_pads(state):
        # Device/Clip's layer replaces the Navigation column's normal and Shift layers.
        return controls.device_clip_layer(state, key)
    if held == "copy" and not shifted:
        if not event.pressed:
            return replace(state, copy=False, seq_copy_source=None), []
        return replace(state, copy=True), buttons.say("copy", "held_steps")
    if held == "delete" and not shifted:
        if not event.pressed:
            return replace(state, delete=False), []
        return replace(state, delete=True), buttons.say("delete", "held_steps")
    if event.column in layout.SEQ_STEP_COLUMNS:
        return _step(state, event, view, snapshot)
    if event.column in layout.SEQ_NOTE_COLUMNS and not state.seq_settings:
        return _note_pad(state, event, view, snapshot)
    setting = layout.SEQUENCER_SETTINGS.at(key) if state.seq_settings else None
    if setting is not None:
        # The settings take every press and release, whatever is held.
        if not event.pressed:
            return _page_release(state, setting), []
        return functions.press(setting, state, snapshot)
    if not event.pressed:
        return state, []
    if key in controls.navigation_pads(state):
        # Navigation's buttons work under Copy and Delete too.
        button = (layout.SEQUENCER_NAV_SHIFT if shift_layer else layout.SEQUENCER_NAV).at(key)
        return functions.press(button, state, snapshot) if button else (state, [])
    # Copy over Delete over Shift.
    if state.copy or state.delete:
        return state, []
    if state.scene_page and event.column == layout.GLOBAL_COLUMN:
        return global_column.handle(state, event, snapshot)
    button = controls.at(controls.sections(state, shift=state.shift), key)
    if button is None:
        return state, []
    return functions.press(button, state, snapshot)


def _page_release(state, button):
    if button[1] == "pages" and button[3] - 1 == state.seq_page_held:
        return replace(state, seq_page_held=None)
    return state


def _view_of(snapshot):
    return snapshot.sequencer or SequencerView()


def _leave_for(toggle):
    def press(state, snapshot, value):
        state, actions = leave(state, snapshot)
        state, more = toggle(state)
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

    return press


def _cyan(state, snapshot, value):
    return Light(CYAN)


@functions.register("session", [catalogue.SEQUENCER], light=_cyan)
def _session(state, snapshot, value):
    state, actions = leave(state, snapshot)
    return state, actions + buttons.say("session")


@functions.register("seq", [catalogue.SEQUENCER], light=lambda state, snapshot, value: Light(BLUE))
def _seq(state, snapshot, value):
    state, actions = leave(state, snapshot)
    return state, actions + buttons.say("seq", "left")


functions.register("mixer", [catalogue.SEQUENCER], light=_cyan)(_leave_for(mixer.toggle))
functions.register("fx", [catalogue.SEQUENCER], light=_cyan)(_leave_for(fx.toggle))
functions.register_hold(
    "copy",
    [catalogue.SEQUENCER],
    light=lambda state, snapshot, value: Light(RED, Blink.FAST) if state.copy else Light(MAGENTA),
)
functions.register_hold(
    "delete",
    [catalogue.SEQUENCER],
    light=lambda state, snapshot, value: Light(RED, Blink.FAST if state.delete else Blink.STEADY),
)


@functions.register(
    "view", light=lambda state, snapshot, value: Light(BLUE if state.seq_settings else CYAN)
)
def _view(state, snapshot, value):
    state = replace(state, seq_settings=not state.seq_settings)
    return state, buttons.say("view", "settings" if state.seq_settings else "notes")


def _shift_notes(step):
    def press(state, snapshot, value):
        view = _view_of(snapshot)
        if view.drum is not None and view.is_midi:
            return _scroll(state, view, step)
        return _octave(state, step)

    return press


functions.register("up", light=lambda state, snapshot, value: Light(WHITE))(_shift_notes(1))
functions.register("down", light=lambda state, snapshot, value: Light(WHITE))(_shift_notes(-1))


@functions.register(
    "follow", light=lambda state, snapshot, value: Light(BLUE if state.seq_follow else CYAN)
)
def _follow(state, snapshot, value):
    if state.seq_follow:
        view = _view_of(snapshot)
        state = replace(state, seq_follow=False, seq_page=view_page(state, view))
        return state, buttons.say("follow", "off")
    return replace(state, seq_follow=True), buttons.say("follow", "on")


@functions.register("double", light=lambda state, snapshot, value: Light(RED))
def _double(state, snapshot, value):
    view = _view_of(snapshot)
    if not view.has_clip or not view.is_midi:
        return state, buttons.refuse("double", "no_clip")
    return _write(state, [DuplicateLoop(view.track, view.scene), *buttons.say("double")])


@functions.register("halve", light=lambda state, snapshot, value: Light(PINK))
def _halve(state, snapshot, value):
    view = _view_of(snapshot)
    if not view.has_clip or not view.is_midi:
        return state, buttons.refuse("halve", "no_clip")
    half = (view.loop_end - view.loop_start) / 2
    if half < step_length(state) - EPSILON:
        return state, buttons.refuse("halve", "too_short")
    loop = SetLoop(view.track, view.scene, view.loop_start, view.loop_start + half)
    return _write(state, [loop, *buttons.say("halve")])


@functions.register(
    "rates", light=lambda state, snapshot, rate: Light(BLUE if rate == state.seq_rate else CYAN)
)
def _rate(state, snapshot, rate):
    state = replace(state, seq_rate=rate)
    return state, _rate_message("rates", state)


@functions.register(
    "triplet", light=lambda state, snapshot, value: Light(ORANGE if state.seq_triplet else PINK)
)
def _triplet(state, snapshot, value):
    state = replace(state, seq_triplet=not state.seq_triplet)
    return state, _rate_message("triplet", state)


def _page_light(state, snapshot, value):
    view = _view_of(snapshot)
    page = value - 1
    playing = playhead(state, view)
    if page == view_page(state, view):
        colour = BLUE
    elif view.has_clip and page * page_span(state) < view.loop_end - EPSILON:
        colour = CYAN
    else:
        return Light(OFF)
    playing_page = playing // STEPS if playing is not None else None
    return Light(colour, Blink.TEMPO if page == playing_page else Blink.STEADY)


@functions.register("pages", light=_page_light)
def _page_press(state, snapshot, value):
    return _page(state, value - 1, _view_of(snapshot))


# Slides: hold a step and slide along its row (stage 2)


def x_rows(state):
    # The device rows that want X and slide mode: the rows holding a step.
    return tuple(sorted({layout.device_row(h.pad) for h in state.seq_holds}))


def x_axis(state, event):
    # An X report on a held step's cell: no snapshot, and a redraw flag.
    hold = next(
        (h for h in state.seq_holds if (h.column, h.pad) == (event.column, event.pad)), None
    )
    if hold is None:
        return state, [], False
    if hold.x0 is None:
        return _put_hold(state, hold, replace(hold, x0=event.value)), [], False
    columns = (event.value - hold.x0) / values.X_COLUMN_WIDTH
    actions, started = [], not hold.sliding
    if started:
        # A hold that a span or note pad used, or that holds no notes, stays still.
        if hold.used or not hold.notes or abs(columns) < values.SLIDE_START:
            return state, [], False
        if not state.seq_undo_open:
            state, actions = _close_morph_step(state)
            actions.append(BeginUndoStep())
            state = replace(state, seq_undo_open=True)
        sliding = replace(hold, used=True, sliding=True)
        state, hold = _put_hold(state, hold, sliding), sliding
    if hold.shift:
        moved = round(columns)
    else:
        moved = round(columns * values.VELOCITY_PER_COLUMN)
    if moved == hold.moved:
        # The meter appears when a slide starts.
        return state, actions, started
    before, after = _slid(hold, hold.moved), _slid(hold, moved)
    state = _put_hold(state, hold, replace(hold, moved=moved))
    if after != before:
        actions.append(ModifyNotes(*hold.target, after))
    return state, actions, True


def _slid(hold, moved):
    # (note_id, start, velocity) per captured note, moved by the slide.
    if hold.shift:
        offset = moved * hold.length * values.NUDGE_PER_COLUMN
        return tuple(
            (note.note_id, max(0.0, note.start + offset), note.velocity) for note in hold.notes
        )
    return tuple(
        (note.note_id, note.start, min(127, max(1, note.velocity + moved))) for note in hold.notes
    )


def slide(state, event):
    # A finger crossed into the next cell: its hold follows. Whether a hold owns the slide.
    hold = next(
        (h for h in state.seq_holds if (h.column, h.pad) == (event.from_column, event.pad)),
        None,
    )
    if hold is None:
        return state, False
    return _put_hold(state, hold, replace(hold, column=event.to_column)), True


def _put_hold(state, old, new):
    return replace(state, seq_holds=tuple(new if h is old else h for h in state.seq_holds))


# Steps and note pads


def _step(state, event, view, snapshot):
    if not event.pressed:
        return _release_step(state, event, view, snapshot)
    g = view_page(state, view) * STEPS + step_of((event.column, event.pad))
    length = step_length(state)
    if _inert(state, view, g, snapshot):
        return state, []
    if state.copy:
        return _copy_step(state, g, view, snapshot)
    if state.delete:
        notes = notes_in_step(view, g, length)
        if not notes:
            return state, []
        return _write(state, [EditNotes(view.track, view.scene, remove=_ids(notes))])
    hold = StepHold(
        g,
        event.column,
        event.pad,
        event.velocity,
        shift=state.shift,
        notes=notes_in_step(view, g, length),
        target=(view.track, view.scene),
        length=length,
    )
    first = next((h for h in state.seq_holds if not h.used and h.step < g), None)
    if first is None:
        return replace(state, seq_holds=state.seq_holds + (hold,)), []
    # A span: one note from the first step to this one, replacing the pitch's notes there.
    pitch = selected_pitch(state, view)
    remove = tuple(
        note.note_id
        for note in view.notes
        if note.pitch == pitch and first.step <= step_of_time(note.start, length) <= g
    )
    add = ((pitch, first.step * length, (g - first.step + 1) * length, first.velocity),)
    holds = tuple(replace(h, used=True) if h == first else h for h in state.seq_holds)
    state = replace(state, seq_holds=holds + (replace(hold, used=True),))
    return _write(state, [_edit(state, view, snapshot, remove, add)])


def _release_step(state, event, view, snapshot):
    # By the cell: the page in view can change during a hold.
    hold = next(
        (h for h in state.seq_holds if (h.column, h.pad) == (event.column, event.pad)), None
    )
    if hold is None:
        return state, []
    state = replace(state, seq_holds=tuple(h for h in state.seq_holds if h is not hold))
    if hold.sliding:
        # The last slide to end closes the undo step they share.
        if any(h.sliding for h in state.seq_holds):
            return state, []
        return replace(state, seq_undo_open=False), [EndUndoStep()]
    if hold.used:
        return state, []
    # A tap toggles a one-step note of the selected pitch.
    length = step_length(state)
    pitch = selected_pitch(state, view)
    toggle = _toggle(state, view, snapshot, ((hold.step, hold.velocity),), pitch, length)
    return _write(state, [toggle])


def _toggle(state, view, snapshot, steps, pitch, length):
    # One edit over several (step, velocity): each step loses the pitch's notes, or gains one.
    remove, add = (), ()
    for g, velocity in steps:
        found = [note for note in notes_in_step(view, g, length) if note.pitch == pitch]
        if found:
            remove += _ids(found)
        else:
            add += ((pitch, g * length, length, velocity),)
    return _edit(state, view, snapshot, remove, add)


def _edit(state, view, snapshot, remove=(), add=()):
    create = None if view.has_clip else _create_length(state, snapshot)
    return EditNotes(view.track, view.scene, remove=remove, add=add, create_length=create)


def _ids(notes):
    return tuple(note.note_id for note in notes)


def _copy_step(state, g, view, snapshot):
    # The first press picks the source; each later one pastes over its step's notes.
    length = step_length(state)
    notes = notes_in_step(view, g, length)
    source = state.seq_copy_source
    if source is None:
        if not notes:
            return state, buttons.refuse("copy", "empty_step")
        copied = tuple(
            (note.pitch, note.start - g * length, note.duration, note.velocity) for note in notes
        )
        return replace(state, seq_copy_source=(g, copied)), buttons.say("copy", "picked_step")
    if g == source[0]:
        return state, []
    add = tuple(
        (pitch, g * length + offset, duration, velocity)
        for pitch, offset, duration, velocity in source[1]
    )
    return _write(state, [_edit(state, view, snapshot, _ids(notes), add)])


def _note_pad(state, event, view, snapshot):
    if not event.pressed:
        return state, []
    note = pad_note(state, view, event.column, event.pad)
    if note is None:
        return state, []
    if state.copy:
        return state, []
    if state.delete:
        if not view.has_clip:
            return state, []
        return _write(state, [RemovePitch(view.track, view.scene, note)])
    if state.seq_holds:
        # Toggle the pitch on every held step; the selected note stays.
        steps = tuple((h.step, event.velocity) for h in state.seq_holds)
        holds = tuple(replace(h, used=True) for h in state.seq_holds)
        edit = _toggle(state, view, snapshot, steps, note, step_length(state))
        return _write(replace(state, seq_holds=holds), [edit])
    if view.drum is not None:
        # Live's selection is the selected note: read back on the next snapshot.
        return state, [SelectDrumPad(view.track, note)]
    return replace(state, seq_pitch=note), []


# Settings view


def _rate_message(function, state):
    rate = RATE_NAMES[state.seq_rate]
    return buttons.say(function, "triplet" if state.seq_triplet else None, rate=rate)


def _direction(step):
    return "up" if step > 0 else "down"


def _octave(state, step):
    base = min(MAX_BASE, max(0, state.seq_base + 12 * step))
    if base == state.seq_base:
        return state, []
    return replace(state, seq_base=base), buttons.say(_direction(step), "notes", note=note_name(base))


def _scroll(state, view, step):
    # One rack row, as Live's rack view scrolls.
    scroll = min(MAX_SCROLL, max(0, view.drum.scroll + step))
    if scroll == view.drum.scroll:
        return state, []
    message = buttons.say(_direction(step), "pads", note=note_name(NOTE_COLUMNS * scroll))
    return state, [SetDrumScroll(view.track, scroll), *message]


def note_name(note):
    # Live's naming: C3 = 60.
    return f"{NOTE_NAMES[note % 12]}{note // 12 - 2}"


def _page(state, page, view):
    if not view.has_clip or not view.is_midi:
        return state, []
    span = page_span(state)
    held = state.seq_page_held
    if held is not None and held != page:
        # Hold one page and press another: the loop spans both.
        start, end = min(held, page) * span, (max(held, page) + 1) * span
        loop = buttons.say("pages", "loop", first=min(held, page) + 1, last=max(held, page) + 1)
        return _write(state, [SetLoop(view.track, view.scene, start, end), *loop])
    state = replace(state, seq_page_held=page)
    shown = buttons.say("pages", page=page + 1)
    if page * span >= view.loop_end - EPSILON:
        # Past the end: the loop extends to it.
        state = replace(state, seq_follow=False, seq_page=page)
        loop = SetLoop(view.track, view.scene, view.loop_start, (page + 1) * span)
        return _write(state, [loop, *shown])
    playing = playhead(state, view)
    if playing is not None and playing // STEPS == page:
        return replace(state, seq_follow=True), shown
    return replace(state, seq_follow=False, seq_page=page), shown


# Render


def render(state, snapshot):
    view = snapshot.sequencer or SequencerView()
    frame = {
        (column, pad): Light(OFF)
        for column in range(1, layout.COLUMNS)
        for pad in range(1, layout.ROWS + 1)
    }
    frame.update(global_column.render(state, snapshot))
    if view.track is not None and view.is_midi:
        _render_steps(frame, state, view, snapshot)
        _render_meters(frame, state, view)
        if not state.seq_settings:
            _render_note_pads(frame, state, view)
    _render_buttons(frame, state, snapshot)
    return frame


def _render_steps(frame, state, view, snapshot):
    length = step_length(state)
    first = view_page(state, view) * STEPS
    pitch = selected_pitch(state, view)
    held = {}  # global step -> whether the selected pitch starts there
    for note in view.notes:
        g = step_of_time(note.start, length)
        if first <= g < first + STEPS:
            held[g] = held.get(g, False) or note.pitch == pitch
    playing = playhead(state, view)
    source = state.seq_copy_source[0] if state.seq_copy_source is not None else None
    for s in range(STEPS):
        g = first + s
        if _inert(state, view, g, snapshot):
            continue
        if g == source:
            light = Light(RED, Blink.FAST)
        elif g == playing:
            light = Light(WHITE)
        elif g in held:
            light = Light(ORANGE if held[g] else BLUE)
        else:
            continue
        frame[step_key(s)] = light


def _render_meters(frame, state, view):
    # A velocity slide's row is a bar meter: the selected note's velocity, else the highest.
    pitch = selected_pitch(state, view)
    for hold in state.seq_holds:
        if not hold.sliding or hold.shift:
            continue
        slid = dict((note_id, velocity) for note_id, _, velocity in _slid(hold, hold.moved))
        selected = [slid[note.note_id] for note in hold.notes if note.pitch == pitch]
        velocity = max(selected or slid.values())
        lit = math.ceil(velocity / values.VELOCITY_PER_COLUMN)
        colour = ORANGE if selected else BLUE
        for i, column in enumerate(layout.SEQ_STEP_COLUMNS):
            frame[(column, hold.pad)] = Light(colour if i < lit else OFF)


def _render_note_pads(frame, state, view):
    sounding = set()
    if view.is_playing:
        sounding = {
            note.pitch
            for note in view.notes
            if note.start - EPSILON <= view.position < note.start + note.duration
        }
    selected = selected_pitch(state, view)
    for column in layout.SEQ_NOTE_COLUMNS:
        for pad in range(1, layout.ROWS + 1):
            note = pad_note(state, view, column, pad)
            if note is None:
                continue
            if note in sounding:
                light = Light(YELLOW)
            elif note == selected:
                light = Light(GREEN, Blink.FAST)
            else:
                light = Light(_note_colour(view, note, pad))
            frame[(column, pad)] = light


def _note_colour(view, note, pad):
    if view.drum is not None:
        if note not in view.drum.filled:
            return OFF
        # Pads 5-8 are Live's visible 16.
        return WHITE if pad > layout.ROWS // 2 else CYAN
    scale = view.scale
    if scale.on:
        degree = (note - scale.root) % 12
        if degree == 0:
            return CYAN
        return WHITE if degree in scale.intervals else MAGENTA
    return WHITE if note % 12 in NATURALS else MAGENTA


def _render_buttons(frame, state, snapshot):
    # Column 15 and the settings on both layers; the Navigation column's live layer.
    shift_layer = state.shift and not state.copy and not state.delete
    own = controls.sections(state)[2:]
    navigation = layout.SEQUENCER_NAV_SHIFT if shift_layer else layout.SEQUENCER_NAV
    for section in (*own, navigation):
        for button in section.buttons():
            frame[button[2]] = functions.light(button, state, snapshot)
    if state.device_clip:
        controls.render_device_clip_layer(frame, state, snapshot)
