"""Session Mode: clip slots, the mute and select rows, columns 15 and 16, and the Shift layer."""

from dataclasses import replace

from . import buttons, controls, dispatch, faders, functions, fx, layout, mixer, modes, sequencer
from .leds import (
    BLUE,
    CYAN,
    LIME,
    MAGENTA,
    OFF,
    ORANGE,
    PINK,
    RED,
    WHITE,
    YELLOW,
    Blink,
    Light,
    track_colour,
)
from .model import (
    ArmExclusive,
    CopyClip,
    CopyGroupClips,
    CopyScene,
    DeleteClip,
    DeleteGroupClips,
    DeleteScene,
    EnterMode,
    FireScene,
    FireSlot,
    PadPress,
    SceneSelected,
    SelectTrack,
    SetArm,
    ShowClip,
    StopTrackClips,
    ToggleMute,
    ToggleSolo,
)
from .modes import ClipSource, GroupSource, Mode, SceneSource

def handle(state, event, snapshot):
    if isinstance(event, SceneSelected):
        # Keep the scene Capture selected in view.
        window = layout.scroll_to_scene(
            state.window,
            event.scene,
            snapshot.track_count,
            snapshot.scene_count,
            controls.window_tracks(state),
        )
        return replace(state, window=window), []
    if not isinstance(event, PadPress):
        return state, []
    if not event.pressed and fx.binding(state, event):
        # Shift + a slot's lift binds, even once Shift is let go: the press decided.
        return fx.bind_release(state)
    if not event.pressed and fx.holding(state, event):
        # A held slot's lift, wherever its finger slid to: a tap recalls, a slide keeps.
        return fx.release(state, event, snapshot)
    if not event.pressed and faders.holds(state, event):
        # A fader touch ends on its cell's release, wherever the finger slid to.
        return faders.press(state, event, snapshot)
    # The buttons and holds, before the clip grid, faders and snapshots.
    result = dispatch.handle_button(state, event, snapshot)
    if result is not None:
        return result
    if fx.panel_visible(state) and event.column in layout.SPLIT_FADER_COLUMNS:
        # The split view's snapshots, releases included, as FX Mode's: Stop leaves them alone.
        return fx.press(state, event, snapshot)
    if faders.visible(state) and not state.fx and event.column in layout.SPLIT_FADER_COLUMNS:
        # The split view's faders, releases included; Stop, Copy and Shift leave them alone.
        return faders.press(state, event, snapshot)
    if state.stop and not state.fx and event.column in layout.GRID_COLUMNS and event.pressed:
        # Held Stop takes a track's pads, faders and rows included, before anything else.
        return _stop_track(state, _track(event.column, snapshot))
    if state.mixer and event.column in layout.GRID_COLUMNS:
        if event.pad in mixer.FADER_PADS:
            # Releases matter too.
            return mixer.press(state, event, snapshot)
        if not event.pressed:
            return mixer.row_release(state, event, snapshot), []
        if mixer.sliding(state, event.column):
            # A slide that runs off the fader moves nothing, not even the rows.
            return state, []
    if state.fx and event.column in layout.FX_FADER_COLUMNS:
        return faders.press(state, event, snapshot)
    if state.fx and event.column in layout.GRID_COLUMNS:
        return fx.press(state, event, snapshot)
    if not event.pressed:
        return state, []
    if state.mixer and (state.copy or state.delete):
        # Held for the snapshots: the tracks and scenes ignore them.
        return state, []
    # Copy over Delete over Shift.
    if state.copy:
        return _copy(state, event, snapshot)
    if state.delete:
        return _delete(state, event, snapshot)
    if event.column in layout.GRID_COLUMNS:
        if event.pad == layout.MUTE_ROW:
            return state, _mute_row(state, _track(event.column, snapshot))
        if event.pad == layout.SELECT_ROW:
            return state, _select_row(state, _track(event.column, snapshot))
        return _slot(state, event, snapshot)
    if _is_scene(event):
        scene = state.window.scene + event.pad - 1
        if scene < snapshot.scene_count:
            # The newest launch replaces a pending one. A legato launch leaves the macros alone,
            # and ignores a held Bars pad.
            state = replace(state, pending_launch=None)
            if state.shift:
                return state, [FireScene(scene, legato=True)]
            if state.fx_length is not None:
                return fx.timed_launch(state, scene, snapshot)
            return state, [FireScene(scene, legato=False), *fx.scene_launch(state, scene, snapshot)]
    return state, []


def _current(state):
    return "mixer" if state.mixer else "fx" if state.fx else "session"


def _mode_light(name):
    # Modes are cyan, the current one blue, or pink in its split view. In Sequencer Mode, each
    # leaves it: all cyan.
    def light(state, snapshot, value):
        if state.mode is Mode.SEQUENCER or _current(state) != name:
            return Light(CYAN)
        return Light(PINK if faders.split_view(state) else BLUE)

    return light


@functions.register("session", light=_mode_light("session"))
def _session_press(state, snapshot, value):
    # The current mode's pad goes back to Session.
    if state.mode is Mode.SEQUENCER:
        return sequencer.leave_to_session(state, snapshot)
    if state.mixer:
        return _widen(state, mixer.toggle, snapshot)
    if state.fx:
        return fx.toggle(state)
    return _toggle_split(state, snapshot)


@functions.register("mixer", light=_mode_light("mixer"))
def _mixer_press(state, snapshot, value):
    if state.mode is Mode.SEQUENCER:
        return sequencer.leave_to_mixer(state, snapshot)
    if state.mixer:
        return _toggle_split(state, snapshot)
    return _widen(state, mixer.toggle, snapshot)


@functions.register("fx", light=_mode_light("fx"))
def _fx_press(state, snapshot, value):
    if state.mode is Mode.SEQUENCER:
        return sequencer.leave_to_fx(state, snapshot)
    return _widen(state, fx.toggle, snapshot)


@functions.register("reserved")
def _reserved(state, snapshot, value):
    return state, []


def _seq_light(state, snapshot, value):
    if state.mode is Mode.SEQUENCER:
        return Light(BLUE)
    return Light(CYAN, Blink.FAST) if state.seq_held else Light(CYAN)


def _seq_hold(state, event, snapshot):
    # A hold in Session Mode; in Sequencer Mode a tap leaves it.
    if state.mode is Mode.SEQUENCER:
        return sequencer.leave_by_seq(state, snapshot) if event.pressed else (state, [])
    return _seq(state, event, snapshot)


def _copy_hold(state, event, snapshot):
    if state.mode is Mode.SEQUENCER:
        return sequencer.copy_hold(state, event)
    if not event.pressed:
        return replace(state, copy=False, copy_source=None, fx_copy_source=None), []
    # In Mixer Mode, Copy and Delete only work on the split view's snapshots.
    if state.mixer and not fx.panel_visible(state):
        return state, []
    if state.fx or state.mixer:
        return replace(state, copy=True), buttons.say("copy", "held_slots")
    return replace(state, copy=True), buttons.say("copy", "held")


def _delete_hold(state, event, snapshot):
    if state.mode is Mode.SEQUENCER:
        return sequencer.delete_hold(state, event)
    if not event.pressed:
        return replace(state, delete=False), []
    if state.mixer and not fx.panel_visible(state):
        return state, []
    return replace(state, delete=True), buttons.say("delete", "held")


functions.register_hold(
    "seq",
    light=_seq_light,
    handle=_seq_hold,
    down=lambda state: state.seq_held,
    capture=lambda state, event, snapshot: _seq_press(state, event, snapshot),
)
# Copy and Delete hide the Shift layer.
functions.register_hold(
    "copy",
    light=lambda state, snapshot, value: Light(RED, Blink.FAST) if state.copy else Light(MAGENTA),
    handle=_copy_hold,
    down=lambda state: state.copy,
    hides=("shift",),
)
functions.register_hold(
    "delete",
    light=lambda state, snapshot, value: Light(RED, Blink.FAST if state.delete else Blink.STEADY),
    handle=_delete_hold,
    down=lambda state: state.delete,
    hides=("shift",),
)
functions.register_hold(
    "stop",
    light=lambda state, snapshot, value: Light(RED, Blink.FAST if state.stop else Blink.STEADY),
    handle=lambda state, event, snapshot: _stop(state, event),
    down=lambda state: state.stop,
)


def _track(column, snapshot):
    i = column - layout.GRID_COLUMNS[0]
    return snapshot.tracks[i] if i < len(snapshot.tracks) else None


def _slot_at(state, event, snapshot):
    # The track and scene of a clip-slot press, or None outside the session.
    track = _track(event.column, snapshot)
    scene = state.window.scene + event.pad - 1
    if track is None or scene >= snapshot.scene_count:
        return None
    return track, scene


def _is_slot(event):
    return event.column in layout.GRID_COLUMNS and event.pad <= layout.WINDOW_SCENES


def _is_scene(event):
    return event.column == layout.SCENE_COLUMN and event.pad <= layout.WINDOW_SCENES


def _slot(state, event, snapshot):
    target = _slot_at(state, event, snapshot)
    if target is None:
        return state, []
    track, scene = target
    slot = track.slots[event.pad - 1]
    armed = track.arm or track.implicit_arm
    starts = armed and not slot.has_clip
    # A press that starts or continues a recording.
    records = (
        starts or slot.is_recording or (slot.is_playing and armed and snapshot.session_record)
    )
    # Live only starts a new recording in an empty slot on an armed track.
    length = controls.record_length(state.fixed_length, snapshot) if starts else None
    actions = [FireSlot(track.index, scene, legato=state.shift, record_length=length)]
    if records:
        actions.append(ShowClip(track.index, scene))
        if track.has_midi_input:
            state, more = faders.reset(state)
            state = modes.enter(state, Mode.LINNSTRUMENT)
            actions += more + [EnterMode(Mode.LINNSTRUMENT)]
    return state, actions


def _copy(state, event, snapshot):
    if _is_slot(event):
        return _copy_slot(state, event, snapshot)
    if _is_scene(event):
        return _copy_scene(state, event, snapshot)
    return state, []


def _copy_slot(state, event, snapshot):
    target = _slot_at(state, event, snapshot)
    if target is None:
        return state, []
    track, scene = target
    slot = track.slots[event.pad - 1]
    source = state.copy_source
    if source is None:
        if slot.has_clip:
            source = ClipSource(track.index, scene, track.has_midi_input)
            return replace(state, copy_source=source), buttons.say("copy", "picked_clip")
        if track.is_foldable and any(slot.member_clips):
            source = GroupSource(track.index, scene)
            return replace(state, copy_source=source), buttons.say("copy", "picked_clip")
        return state, buttons.refuse("copy", "empty_slot")
    if isinstance(source, SceneSource):
        return state, buttons.refuse("copy", "scene_source")
    dropped = replace(state, copy_source=None)
    if isinstance(source, GroupSource):
        return dropped, _copy_group(state, source, track, scene, slot)
    if slot.has_clip:
        return dropped, buttons.refuse("copy", "target_full")
    if track.is_foldable:
        return dropped, buttons.refuse("copy", "group_target")
    if track.has_midi_input != source.midi:
        return dropped, buttons.refuse("copy", "kinds")
    copy = CopyClip(source.track, source.scene, track.index, scene)
    return dropped, [copy, *buttons.say("copy", "clip_copied")]


def _copy_group(state, source, track, scene, slot):
    # Each member copies to its own slot: every member with a clip in the source row needs an
    # empty slot in the target row, or nothing copies.
    if track.index != source.track:
        return buttons.refuse("copy", "other_group")
    row = source.scene - state.window.scene
    if not 0 <= row < len(track.slots):
        return []
    sources = track.slots[row].member_clips
    if any(a and b for a, b in zip(sources, slot.member_clips)):
        return buttons.refuse("copy", "target_full")
    return [CopyGroupClips(source.track, source.scene, scene), *buttons.say("copy", "clips_copied")]


def _copy_scene(state, event, snapshot):
    scene = state.window.scene + event.pad - 1
    if scene >= snapshot.scene_count:
        return state, []
    row = event.pad - 1
    has = snapshot.scene_clips[row] if row < len(snapshot.scene_clips) else False
    source = state.copy_source
    if source is None:
        if has:
            state = replace(state, copy_source=SceneSource(scene))
            return state, buttons.say("copy", "picked_scene")
        return state, buttons.refuse("copy", "empty_scene")
    if isinstance(source, (ClipSource, GroupSource)):
        return state, buttons.refuse("copy", "clip_source")
    dropped = replace(state, copy_source=None)
    if has:
        return dropped, buttons.refuse("copy", "scene_full")
    dropped, save = fx.copy_scene(dropped, source.scene, scene, snapshot.scene_count)
    return dropped, [CopyScene(source.scene, scene), *save, *buttons.say("copy", "scene_copied")]


def _delete(state, event, snapshot):
    if _is_slot(event):
        target = _slot_at(state, event, snapshot)
        if target is None:
            return state, []
        track, scene = target
        slot = track.slots[event.pad - 1]
        if slot.has_clip:
            return state, [DeleteClip(track.index, scene)]
        if track.is_foldable and slot.controls_other_clips:
            return state, [DeleteGroupClips(track.index, scene)]
        return state, []
    if _is_scene(event):
        scene = state.window.scene + event.pad - 1
        if scene >= snapshot.scene_count:
            return state, []
        if snapshot.scene_count == 1:
            return state, buttons.refuse("delete", "last_scene")
        window = layout.move_window(
            state.window,
            0,
            0,
            snapshot.track_count,
            snapshot.scene_count - 1,
            controls.window_tracks(state),
        )
        return replace(state, window=window), [DeleteScene(scene)]
    return state, []


def _seq(state, event, snapshot):
    # A hold pad, like Stop: hold it and press a clip slot to sequence that slot, or tap it.
    if event.pressed:
        if state.copy or state.delete:
            return state, []
        return replace(state, seq_held=True, seq_used=False), buttons.say("seq")
    if not state.seq_held:
        return state, []
    used = state.seq_used
    state = replace(state, seq_held=False, seq_used=False)
    if used:
        return state, []
    return sequencer.enter_by_tap(state, snapshot)


def _seq_press(state, event, snapshot):
    # Any press while Seq is held uses the hold; only a slot on the plain Session layer enters.
    state = replace(state, seq_used=True)
    plain = not (state.mixer or state.fx or state.shift or state.copy or state.delete)
    if plain and _is_slot(event) and event.column in _track_columns(state):
        target = _slot_at(state, event, snapshot)
        if target is not None:
            return sequencer.enter_on_slot(state, *target, snapshot)
    return state, []


def _stop(state, event):
    # A hold pad: hold it and press a track's pad to stop that track. Shift's layer hides it.
    if not event.pressed:
        return replace(state, stop=False), []
    if state.copy or state.delete or state.shift:
        return state, []
    return replace(state, stop=True), buttons.say("stop", "held")


def _stop_track(state, track):
    if track is None:
        return state, []
    return state, [StopTrackClips(track.index), *buttons.say("stop", track=track.name)]


def _mute_row(state, track):
    if track is None:
        return []
    if state.shift:
        return [ToggleSolo(track.index)]
    return [ToggleMute(track.index)]


def _select_row(state, track):
    # A plain press arms exclusively whatever Live's Exclusive Arm preference says.
    if track is None:
        return []
    if state.shift:
        # Arm or disarm this track alone; the selection stays.
        return [SetArm(track.index, not track.arm)] if track.can_be_armed else []
    if not track.can_be_armed:
        return [SelectTrack(track.index)]
    # Pressing the selected, armed track arms it again: Shift + the pad disarms.
    return [SelectTrack(track.index), ArmExclusive(track.index, True)]


def _widen(state, toggle, snapshot):
    # Leaving a split view for 13 tracks keeps the last tracks filling the window.
    width = controls.window_tracks(state)
    state, actions = toggle(state)
    if controls.window_tracks(state) > width:
        window = layout.move_window(
            state.window, 0, 0, snapshot.track_count, snapshot.scene_count
        )
        state = replace(state, window=window)
    return state, actions


def _split_owner(state):
    # Session and Mixer Mode each toggle their own split view from their own pad.
    return "mixer" if state.mixer else "session"


def _toggle_split(state, snapshot):
    # Session or Mixer Mode's own split view.
    on = not faders.split_view(state)
    if state.mixer:
        # Columns 10-14 change hands: no volume fader touch latches.
        state, actions = mixer.reset(state)
        state = replace(state, mixer_split=on)
    else:
        actions = []
        state = replace(state, split=on)
    if on:
        return state, actions + buttons.say(_split_owner(state), "split_on")
    # The wider window keeps the last tracks filling it; the faders and snapshots stop showing.
    state, more = faders.reset(state)
    state = replace(state, fx_length=None)
    actions += more
    window = layout.move_window(state.window, 0, 0, snapshot.track_count, snapshot.scene_count)
    return replace(state, window=window), actions + buttons.say(_split_owner(state), "split_off")


def render(state, snapshot):
    # Copy and Delete hide the Shift layer.
    shift_layer = state.shift and not state.copy and not state.delete
    frame = {
        (column, pad): Light(OFF)
        for column in range(1, layout.COLUMNS)
        for pad in range(1, layout.ROWS + 1)
    }
    for column in _track_columns(state):
        track = _track(column, snapshot)
        if state.fx:
            break
        if state.mixer:
            if not shift_layer:
                _render_fader(frame, column, track)  # dark under Shift
            _render_rows(frame, column, track, shift_layer)
            continue
        for pad in range(1, layout.WINDOW_SCENES + 1):
            frame[(column, pad)] = _slot_light(track, pad - 1)
        _render_rows(frame, column, track, shift_layer)
    if state.fx or fx.panel_visible(state):
        frame.update(fx.render(state, snapshot))
    if faders.visible(state):
        frame.update(faders.render(state, snapshot))
    for pad in range(1, layout.WINDOW_SCENES + 1):
        frame[(layout.SCENE_COLUMN, pad)] = controls.scene_light(
            snapshot, state.window.scene, pad - 1, controls.waiting_scene(state)
        )
    dispatch.paint(frame, state, snapshot)
    _render_copy_source(frame, state)
    # A slot slide's meter goes over everything on its row, scenes and Navigation included.
    frame.update(fx.render_meters(state))
    return frame


def _track_columns(state):
    return range(layout.GRID_COLUMNS[0], layout.GRID_COLUMNS[0] + controls.window_tracks(state))


def _render_copy_source(frame, state):
    # The copy source: on top of everything else, and only while in the window.
    source = state.copy_source
    window = state.window
    if isinstance(source, (ClipSource, GroupSource)):
        column = source.track - window.track + layout.GRID_COLUMNS[0]
        pad = source.scene - window.scene + 1
        if column in _track_columns(state) and 1 <= pad <= layout.WINDOW_SCENES:
            frame[(column, pad)] = Light(RED, Blink.FAST)
    elif isinstance(source, SceneSource):
        pad = source.scene - window.scene + 1
        if 1 <= pad <= layout.WINDOW_SCENES:
            frame[(layout.SCENE_COLUMN, pad)] = Light(RED, Blink.FAST)


def _render_fader(frame, column, track):
    # A bar in the track's colour from the last fader pad up to the pad nearest Live's volume.
    if track is None:
        return
    for pad in range(mixer.lit_pad(track.volume), mixer.FADER_PADS[-1] + 1):
        frame[(column, pad)] = Light(track_colour(track.colour))


def _slot_light(track, row):
    # Highest priority first; the same on both layers. A group slot's playing, triggered
    # and recording state is its members'.
    if track is None or row >= len(track.slots):
        return Light(OFF)
    slot = track.slots[row]
    if slot.is_recording:
        return Light(RED)
    if slot.is_triggered:
        return Light(YELLOW)
    if slot.is_playing:
        return Light(track_colour(track.colour), Blink.TEMPO)
    if slot.has_clip or slot.controls_other_clips:
        return Light(track_colour(track.colour))
    if track.arm or track.implicit_arm:
        return Light(WHITE)
    return Light(OFF)


def _render_rows(frame, column, track, shift_layer):
    frame[(column, layout.MUTE_ROW)] = _mute_light(track, shift_layer)
    frame[(column, layout.SELECT_ROW)] = _select_light(track)


def _mute_light(track, shift_layer):
    if track is None:
        return Light(OFF)
    if shift_layer:
        return Light(BLUE if track.solo else CYAN)
    return Light(ORANGE if track.mute else PINK)


def _select_light(track):
    # The same on both layers.
    if track is None:
        return Light(OFF)
    if track.can_be_armed and (track.arm or track.implicit_arm):
        return Light(RED)
    if track.selected:
        return Light(WHITE)
    return Light(LIME if track.can_be_armed else OFF)
