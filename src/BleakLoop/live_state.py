"""Adapter: read Live's state into a plain Snapshot. No decisions."""

from dataclasses import replace

from .core import layout, values
from .core.model import (
    ClipTarget,
    ClipView,
    DrumView,
    FaderView,
    MacroView,
    NoteView,
    RackView,
    ScaleView,
    SelectedTrack,
    SeqEntry,
    SequencerView,
    SlotView,
    Snapshot,
    TrackView,
)


def read_transport(song, application):
    # Only the transport: enough for the blink clock, without the tracks and slots.
    return Snapshot(
        is_playing=song.is_playing,
        song_beats=song.current_song_time,
        tempo=song.tempo,
        metronome=song.metronome,
        session_view=application.view.is_view_visible("Session"),
    )


def read(
    song,
    application,
    window,
    scene_clips=False,
    selected=False,
    faders=None,
    width=layout.WINDOW_TRACKS,
    sequencer=None,
    seq_entry=False,
):
    # faders: the core state whose faders show, or None while they're hidden.
    # sequencer: Sequencer Mode's SequencerView, read by read_sequencer, or None outside it.
    tracks = list(song.visible_tracks)
    scenes = list(song.scenes)
    rows = range(window.scene, min(window.scene + layout.WINDOW_SCENES, len(scenes)))
    columns = range(window.track, min(window.track + width, len(tracks)))
    selected_track = song.view.selected_track
    mixable = list(song.tracks) + list(song.return_tracks)
    set_tracks = list(song.tracks) if sequencer is not None or seq_entry else None
    return replace(
        read_transport(song, application),
        track_count=len(tracks),
        scene_count=len(scenes),
        # Group members' clips are costly too: only while Copy is held.
        tracks=tuple(
            _track(song, i, tracks[i], rows, selected_track, scene_clips, set_tracks)
            for i in columns
        ),
        can_undo=song.can_undo,
        can_redo=song.can_redo,
        launch_quantization=int(song.clip_trigger_quantization),
        signature_numerator=song.signature_numerator,
        signature_denominator=song.signature_denominator,
        session_record=song.session_record,
        arrangement_overdub=song.arrangement_overdub,
        arrangement_record=song.record_mode,
        back_to_arranger=song.back_to_arranger,
        highlighted_clip=_clip(candidate_clip(song, ClipTarget.HIGHLIGHTED)),
        detail_clip=_clip(candidate_clip(song, ClipTarget.DETAIL)),
        playing_clip=_clip(candidate_clip(song, ClipTarget.PLAYING)),
        # Costly with many tracks: only while Copy is held, when the window can't move.
        scene_clips=_scene_clips(song, rows) if scene_clips else (),
        scene_triggered=tuple(scenes[scene].is_triggered for scene in rows),
        # Every scene of one track: only in Linnstrument Mode, which is the only reader.
        selected_track=_selected_track(song, tracks, scenes) if selected else None,
        selected_scene=scenes.index(song.view.selected_scene) if selected else 0,
        can_capture_midi=song.can_capture_midi,
        any_muted=any(track.mute for track in mixable),
        any_soloed=any(track.solo for track in mixable),
        # Live raises on reading arm from a track that can't be armed.
        any_armed=any(track.can_be_armed and track.arm for track in song.tracks),
        faders=read_faders(song, faders) if faders is not None else (),
        arms=_arms(set_tracks) if set_tracks is not None else (),
        sequencer=sequencer,
        seq_entry=read_seq_entry(song) if seq_entry else None,
    )


def read_arms(song):
    return _arms(list(song.tracks))


def _arms(tracks):
    # Live raises on reading arm state from a track that can't be armed.
    return tuple(track.arm if track.can_be_armed else None for track in tracks)


def _index(items, item):
    # By equality: Live hands out a new wrapper per read.
    return next((i for i, other in enumerate(items) if other == item), None)


def _is_midi(track):
    return track.has_midi_input and not track.is_foldable


def read_sequencer(song):
    # Sequencer Mode's target: Live's highlighted slot, every note of its clip, and the scale.
    tracks = list(song.tracks)
    scene = _index(list(song.scenes), song.view.selected_scene) or 0
    track = song.view.selected_track
    index = _index(tracks, track)
    view = SequencerView(
        scene=scene,
        scale=ScaleView(song.scale_mode, song.root_note, tuple(song.scale_intervals)),
    )
    if index is None:
        return view
    view = replace(view, track=index, name=track.name, is_midi=_is_midi(track))
    if not view.is_midi:
        return view
    view = replace(view, drum=_drum(track))
    slot = track.clip_slots[scene]
    if not slot.has_clip:
        return view
    clip = slot.clip
    notes = clip.get_notes_extended(0, 128, 0.0, max(clip.loop_end, clip.end_marker))
    return replace(
        view,
        has_clip=True,
        is_playing=clip.is_playing,
        loop_start=clip.loop_start,
        loop_end=clip.loop_end,
        position=clip.playing_position,
        notes=tuple(
            NoteView(note.note_id, note.pitch, note.start_time, note.duration, note.velocity)
            for note in notes
        ),
    )


RACK_DEPTH = 8  # racks nest a few levels at most; this only guards against a parent loop


def drum_rack(track, depth=RACK_DEPTH):
    # The track's first Drum Rack, depth first: its devices in order, and inside a rack its
    # chains in order, such as a Drum Rack inside an Instrument Rack. A Drum Rack's own pads
    # aren't searched. None without one. live_actions resolves the drum actions with this too.
    for device in track.devices:
        if device.can_have_drum_pads:
            return device
        if device.can_have_chains and depth > 0:
            for chain in device.chains:
                found = drum_rack(chain, depth - 1)
                if found is not None:
                    return found
    return None


def _drum(track):
    rack = drum_rack(track)
    if rack is None:
        return None
    selected = rack.view.selected_drum_pad
    return DrumView(
        scroll=rack.view.drum_pads_scroll_position,
        selected=selected.note if selected is not None else None,
        filled=frozenset(pad.note for pad in rack.drum_pads if len(pad.chains) > 0),
    )


def read_seq_entry(song):
    # Where a Seq tap enters: the highlighted slot, the Detail-view clip and the playing slot.
    tracks = list(song.tracks)
    scene = _index(list(song.scenes), song.view.selected_scene) or 0
    track = song.view.selected_track
    index = _index(tracks, track)
    if index is None:
        return SeqEntry(scene=scene, detail=_detail_slot(song, tracks))
    playing = track.playing_slot_index
    return SeqEntry(
        selected=index,
        selected_midi=_is_midi(track),
        scene=scene,
        has_clip=track.clip_slots[scene].has_clip,
        detail=_detail_slot(song, tracks),
        playing_scene=playing if playing >= 0 else None,
    )


def _detail_slot(song, tracks):
    # (track, scene) of the Detail-view clip when it's a Session clip on a MIDI track. An
    # Arrangement clip's parent is its track, not a slot.
    clip = song.view.detail_clip
    if clip is None:
        return None
    slot = clip.canonical_parent
    owner = getattr(slot, "canonical_parent", None)
    index = _index(tracks, owner)
    if index is None or not _is_midi(owner):
        return None
    scene = _index(list(owner.clip_slots), slot)
    return None if scene is None else (index, scene)


def read_position(song):
    # The 10 ms timer's read: whether the highlighted slot's clip plays, and where.
    slot = song.view.highlighted_clip_slot
    if slot is None or not slot.has_clip:
        return False, 0.0
    clip = slot.clip
    return clip.is_playing, clip.playing_position


FADER_ROWS = 8


def read_faders(song, state):
    # FaderView or None per fader row. A top-level rack's macro carries its identity in
    # read_racks's terms, so a fader can take its macro out of a morph.
    return tuple(
        None
        if target is None
        else FaderView(
            target[0].name,
            target[0].value,
            target[0].min,
            target[0].max,
            target[0].is_quantized,
            target[1],
        )
        for target in fader_targets(song, state, range(FADER_ROWS))
    )


def fader_parameter(song, state, row):
    # live_actions resolves SetFaderParameter with this, so the faders and their writes
    # can't disagree.
    target = fader_targets(song, state, (row,))[0]
    return None if target is None else target[0]


def fader_targets(song, state, rows):
    # (parameter, macro identity or None), or None, per row asked for.
    if state.fader_source == "mapped":
        return [_bound(song, state.fader_bindings[row]) for row in rows]
    # Device FX: the device with Live's blue hand.
    device = song.appointed_device
    if device is None:
        return [None for _ in rows]
    path = None
    if device.can_have_chains:
        parameters = macros(device)[:FADER_ROWS]
        path = _rack_path(song, device)
    else:
        # Parameter 0 is Device On.
        parameters = list(device.parameters)[1 : 1 + FADER_ROWS]
    return [
        None
        if row >= len(parameters)
        else (parameters[row], None if path is None else (path, device.name, row))
        for row in rows
    ]


def _bound(song, binding):
    # A Mapped FX binding's parameter, found again by names; None if it's gone or renamed.
    if binding is None:
        return None
    found = nth_named(fx_tracks(song), binding.track, binding.tn, lambda item: item[2].name)
    if found is None:
        return None
    kind, index, track = found
    macro = None
    if binding.device is None:
        parameters = mixer_parameters(track)
    else:
        devices = list(track.devices)
        device = nth_named(devices, binding.device, binding.dn, lambda item: item.name)
        if device is None:
            return None
        parameters = list(device.parameters)
        if device.can_have_chains and 1 <= binding.param <= device.visible_macro_count:
            position = next(i for i, other in enumerate(devices) if other == device)
            macro = ((kind, index, position), device.name, binding.param - 1)
    if binding.param >= len(parameters):
        return None
    parameter = parameters[binding.param]
    if parameter.name != binding.name:
        return None
    return parameter, macro


def mixer_parameters(track):
    # A track's bindable mixer parameters, in binding index order.
    mixer = track.mixer_device
    return [mixer.volume, mixer.panning, *mixer.sends]


def nth_named(items, name, n, name_of):
    # The item that is the n-th (from 0) with this name, or None.
    count = 0
    for item in items:
        if name_of(item) == name:
            if count == n:
                return item
            count += 1
    return None


def read_fader_store(song):
    return song.get_data(values.FADERS_DATA_KEY, "")


def _rack_path(song, device):
    # (kind, track index, device index) of a rack directly on a track, return or master.
    parent = device.canonical_parent
    for kind, index, track in fx_tracks(song):
        if track == parent:
            for position, other in enumerate(track.devices):
                if other == device:
                    return kind, index, position
    return None


def candidate_clip(song, target):
    # The quantize candidates. live_actions resolves QuantizeClip with this too, so the
    # snapshot and the action can't disagree.
    if target is ClipTarget.HIGHLIGHTED:
        slot = song.view.highlighted_clip_slot
        return slot.clip if slot is not None and slot.has_clip else None
    if target is ClipTarget.DETAIL:
        return song.view.detail_clip
    # Master and return tracks aren't in song.tracks.
    track = song.view.selected_track
    if track not in list(song.tracks) or track.playing_slot_index < 0:
        return None
    slot = track.clip_slots[track.playing_slot_index]
    return slot.clip if slot.has_clip else None


def group_members(song, group):
    # The leaf tracks under a group, nested groups included, in song.tracks order. live_actions
    # resolves CopyGroupClips with this too, so the snapshot and the action can't disagree.
    return [track for track in song.tracks if not track.is_foldable and _in_group(track, group)]


def _in_group(track, group):
    while track.is_grouped:
        track = track.group_track
        if track == group:
            return True
    return False


def _clip(clip):
    return None if clip is None else ClipView(is_midi=clip.is_midi_clip)


def _scene_clips(song, rows):
    # Every track in the Set, including folded group members. Group tracks
    # themselves are skipped: their slots can't hold clips.
    tracks = [track for track in song.tracks if not track.is_foldable]
    return tuple(any(track.clip_slots[scene].has_clip for track in tracks) for scene in rows)


def _selected_track(song, tracks, scenes):
    # Master, returns and folded group members aren't in the track list.
    track = song.view.selected_track
    if track not in tracks:
        return None
    can_be_armed = track.can_be_armed
    slots = track.clip_slots
    return SelectedTrack(
        index=tracks.index(track),
        name=track.name,
        armed=can_be_armed and (track.arm or track.implicit_arm),
        is_foldable=track.is_foldable,
        clips=tuple(slots[scene].has_clip for scene in range(len(scenes))),
    )


def _track(song, index, track, rows, selected_track, read_members=False, set_tracks=None):
    slots = track.clip_slots
    members = group_members(song, track) if read_members and track.is_foldable else []
    # Live raises on reading arm state from a track that can't be armed.
    can_be_armed = track.can_be_armed
    return TrackView(
        index=index,
        name=track.name,
        colour=track.color,
        arm=can_be_armed and track.arm,
        implicit_arm=can_be_armed and track.implicit_arm,
        can_be_armed=can_be_armed,
        mute=track.mute,
        solo=track.solo,
        has_midi_input=track.has_midi_input,
        is_foldable=track.is_foldable,
        selected=track == selected_track,
        volume=track.mixer_device.volume.value,
        slots=tuple(_slot(slots[scene], members, scene) for scene in rows),
        set_index=_index(set_tracks, track) if set_tracks is not None else None,
    )


def _slot(slot, members, scene):
    return SlotView(
        has_clip=slot.has_clip,
        is_playing=slot.is_playing,
        is_triggered=slot.is_triggered,
        is_recording=slot.is_recording,
        controls_other_clips=slot.is_group_slot and slot.controls_other_clips,
        member_clips=tuple(member.clip_slots[scene].has_clip for member in members),
    )


def read_racks(song):
    # Every top-level rack in Set order: tracks, returns, then master, devices left to right.
    racks = []
    for kind, index, track in fx_tracks(song):
        for position, device in enumerate(track.devices):
            if device.can_have_chains:
                views = tuple(_macro(parameter) for parameter in macros(device))
                racks.append(RackView((kind, index, position), track.name, device.name, views))
    return tuple(racks)


def read_macro_values(song, morph):
    # The live value per morphing macro, or None when its rack has moved or gone.
    targets = macro_parameters(song, ((m.path, m.rack_name, m.index) for m in morph.macros))
    return tuple(None if parameter is None else parameter.value for parameter in targets)


def macro_parameters(song, macros_wanted):
    # The parameter per (path, rack name, index), or None; each rack resolved once per call,
    # since a morph tick touches every macro of every rack.
    racks = {}
    result = []
    for path, rack_name, index in macros_wanted:
        if (path, rack_name) not in racks:
            device = rack_at(song, path, rack_name)
            racks[path, rack_name] = macros(device) if device is not None else []
        parameters = racks[path, rack_name]
        result.append(parameters[index] if index < len(parameters) else None)
    return result


def read_fx_store(song):
    return song.get_data(values.FX_DATA_KEY, "")


def read_fx_scenes_store(song):
    return song.get_data(values.FX_SCENES_DATA_KEY, "")


def rack_at(song, path, rack_name):
    # The device at path, if it's still a rack with that name.
    kind, index, position = path
    if kind == "track":
        tracks = list(song.tracks)
    elif kind == "return":
        tracks = list(song.return_tracks)
    else:
        tracks = [song.master_track]
    if index >= len(tracks):
        return None
    devices = list(tracks[index].devices)
    if position >= len(devices):
        return None
    device = devices[position]
    if not device.can_have_chains or device.name != rack_name:
        return None
    return device


def fx_tracks(song):
    # (kind, index, track) for every track, return and master, in Set order.
    for index, track in enumerate(song.tracks):
        yield "track", index, track
    for index, track in enumerate(song.return_tracks):
        yield "return", index, track
    yield "master", 0, song.master_track


def macros(device):
    # Parameter 0 is Device On; the visible macros follow it.
    return list(device.parameters)[1 : 1 + device.visible_macro_count]


def _macro(parameter):
    return MacroView(
        value=parameter.value,
        min=parameter.min,
        max=parameter.max,
        is_quantized=parameter.is_quantized,
    )
