"""Adapter: carry out core actions on Live objects. No decisions."""

import logging
import time
from contextlib import contextmanager

import Live

from . import live_state
from .core import values
from .core.modes import FaderBinding
from .core.model import (
    AddScene,
    ArmExclusive,
    BeginUndoStep,
    BindFader,
    CaptureAndInsertScene,
    CaptureMidi,
    ClearBackToArrangement,
    CopyClip,
    CopyGroupClips,
    CopyScene,
    DeleteClip,
    DeleteGroupClips,
    DeleteScene,
    DuplicateLoop,
    EditNotes,
    EndUndoStep,
    EnterMode,
    FaderBound,
    FireScene,
    FireSlot,
    HighlightSlot,
    ModifyNotes,
    QuantizeClip,
    RacksRead,
    RecallFxSnapshot,
    Redo,
    RemovePitch,
    SaveFaderBindings,
    SaveFxScenes,
    SaveFxSnapshots,
    SceneSelected,
    SelectDrumPad,
    SelectSetTrack,
    SelectTrack,
    SetArm,
    SetArms,
    SetArrangementRecord,
    SetDrumScroll,
    SetFaderParameter,
    SetLaunchQuantization,
    SetLoop,
    SetMacros,
    SetMixer,
    SetSessionRecord,
    SetTempo,
    SetVolume,
    ShowClip,
    ShowMessage,
    StepDevice,
    StepTrack,
    StopAllClips,
    StopTrackClips,
    StoreFxSnapshot,
    ToggleDetailView,
    ToggleMetronome,
    ToggleMute,
    TogglePlay,
    ToggleSolo,
    Undo,
    UnmuteAll,
    UnarmAll,
    UnsoloAll,
)

logger = logging.getLogger(__name__)


def _slot(song, track, scene):
    return song.visible_tracks[track].clip_slots[scene]


def _set_track(song, index):
    # Sequencer actions index song.tracks, folded group members included.
    tracks = list(song.tracks)
    return tracks[index] if index < len(tracks) else None


def _set_slot(song, track, scene):
    # The clip slot, or None when its track or scene is gone.
    owner = _set_track(song, track)
    if owner is None:
        return None
    slots = list(owner.clip_slots)
    return slots[scene] if scene < len(slots) else None


def _set_clip(song, action):
    # The action's clip, or None with a log line when it's gone.
    slot = _set_slot(song, action.track, action.scene)
    if slot is None or not slot.has_clip:
        name = type(action).__name__
        logger.info("SEQ: skipped %s, no clip at %d/%d", name, action.track, action.scene)
        return None
    return slot.clip


def _edit_notes(song, action):
    slot = _set_slot(song, action.track, action.scene)
    if slot is None or (not slot.has_clip and action.create_length is None):
        logger.info("SEQ: skipped EditNotes, no clip at %d/%d", action.track, action.scene)
        return
    with _undo_step(song):
        if not slot.has_clip:
            slot.create_clip(action.create_length)
        clip = slot.clip
        if action.remove:
            clip.remove_notes_by_id(list(action.remove))
        if action.add:
            clip.add_new_notes(
                tuple(
                    Live.Clip.MidiNoteSpecification(
                        pitch=pitch, start_time=start, duration=duration, velocity=velocity
                    )
                    for pitch, start, duration, velocity in action.add
                )
            )


def _set_loop(clip, start, end):
    # Live refuses a loop start at or past the loop end: move the end first when it would be.
    if start >= clip.loop_end:
        clip.loop_end = end
        clip.loop_start = start
    else:
        clip.loop_start = start
        clip.loop_end = end


def _modify_notes(clip, changes):
    notes = clip.get_notes_by_id([note_id for note_id, _, _ in changes])
    wanted = {note_id: (start, velocity) for note_id, start, velocity in changes}
    for note in notes:
        note.start_time, note.velocity = wanted[note.note_id]
    clip.apply_note_modifications(notes)


@contextmanager
def _undo_step(song):
    # Several changes from one press undo together; a failure mustn't leave the step open.
    song.begin_undo_step()
    try:
        yield
    finally:
        song.end_undo_step()


def _mixable(song):
    # Every track that has mute and solo: the tracks and return tracks, not master.
    return list(song.tracks) + list(song.return_tracks)


def _binding(song, row):
    # (FaderBinding, message) for Live's selected parameter, or (None, the refusal).
    parameter = song.view.selected_parameter
    if parameter is None:
        return None, "Click a parameter in Live first"
    owner = getattr(parameter, "canonical_parent", None)
    track = getattr(owner, "canonical_parent", None)
    tracks = [entry[2] for entry in live_state.fx_tracks(song)]
    if not any(track == other for other in tracks):
        # Inside a rack chain, or not on a track at all.
        if _on_a_track(track, tracks):
            return None, "Map it to a macro instead"
        return None, "Can't bind this parameter"
    tn = _earlier_named(tracks, track)
    if hasattr(owner, "sends"):
        # The track's mixer: volume, pan and sends only.
        index = _index(live_state.mixer_parameters(track), parameter)
        if index is None:
            return None, "Can't bind this parameter"
        binding = FaderBinding(track.name, tn, None, 0, index, parameter.name)
        return binding, f"Fader {row + 1}: {track.name} {parameter.name}"
    index = _index(list(owner.parameters), parameter)
    if index is None:
        return None, "Can't bind this parameter"
    devices = list(track.devices)
    binding = FaderBinding(
        track.name, tn, owner.name, _earlier_named(devices, owner), index, parameter.name
    )
    return binding, f"Fader {row + 1}: {owner.name} {parameter.name}"


def _on_a_track(item, tracks):
    # Whether item sits somewhere under one of the tracks: a chain, a nested device. Racks
    # nest a few levels at most; the limit only guards against an unexpected parent loop.
    for _ in range(32):
        if item is None:
            return False
        if any(item == track for track in tracks):
            return True
        item = getattr(item, "canonical_parent", None)
    return False


def _earlier_named(items, item):
    # The count of items before item with its name.
    position = _index(items, item)
    return sum(1 for other in items[:position] if other.name == item.name)


def _index(items, item):
    return next((i for i, other in enumerate(items) if other == item), None)


def _step(items, current, step):
    # The item step places from current, or None past either end. With nothing current,
    # the first or the last.
    index = next((i for i, item in enumerate(items) if item == current), None)
    if index is None:
        index = -1 if step > 0 else len(items)
    index += step
    return items[index] if 0 <= index < len(items) else None


def _step_track(song, step):
    tracks = list(song.visible_tracks) + list(song.return_tracks) + [song.master_track]
    track = _step(tracks, song.view.selected_track, step)
    if track is None:
        return "No more tracks"
    song.view.selected_track = track
    return track.name


def _step_device(song, step):
    track = song.view.selected_track
    devices = list(track.devices)
    device = _step(devices, _top_level(track.view.selected_device, track, devices), step)
    if device is None:
        return "No more devices"
    song.view.select_device(device)
    # The blue hand too: Device FX follows it, and a selection doesn't always move it.
    song.appointed_device = device
    return device.name


def _top_level(device, track, devices):
    # A device inside a rack steps from the rack on the track: up through chains and racks.
    while device is not None and not any(device == other for other in devices):
        device = getattr(device, "canonical_parent", None)
        if device == track:
            return None
    return device


def _toggle_detail_view(view):
    # Read Live's view, not a flag of our own, so a mouse click in between counts. Showing
    # Detail/Clip also opens a hidden Detail view.
    if view.is_view_visible("Detail/Clip"):
        view.show_view("Detail/DeviceChain")
    else:
        view.show_view("Detail/Clip")


def apply(action, song, surface):
    # Returns None, or a follow-up event for the core (Capture, FX store and recall).
    if isinstance(action, ToggleMetronome):
        song.metronome = not song.metronome
    elif isinstance(action, TogglePlay):
        if song.is_playing:
            song.stop_playing()
        else:
            song.start_playing()
    elif isinstance(action, EnterMode):
        surface.enter_mode(action.mode)
    elif isinstance(action, FireSlot):
        options = {}
        if action.legato:
            options["force_legato"] = True
        if action.record_length is not None:
            options["record_length"] = action.record_length
        _slot(song, action.track, action.scene).fire(**options)
    elif isinstance(action, FireScene):
        song.scenes[action.scene].fire(force_legato=action.legato)
    elif isinstance(action, ToggleMute):
        track = song.visible_tracks[action.track]
        track.mute = not track.mute
    elif isinstance(action, ToggleSolo):
        target = song.visible_tracks[action.track]
        # Live's Exclusive Solo preference: soloing one unsolos the rest, as Live's button does.
        if not target.solo and song.exclusive_solo:
            for track in _mixable(song):
                if track != target and track.solo:
                    track.solo = False
        target.solo = not target.solo
    elif isinstance(action, SelectTrack):
        song.view.selected_track = song.visible_tracks[action.track]
    elif isinstance(action, ArmExclusive):
        target = song.visible_tracks[action.track]
        for track in song.tracks:
            if track != target and track.can_be_armed and track.arm:
                track.arm = False
        target.arm = action.arm
    elif isinstance(action, SetArm):
        song.visible_tracks[action.track].arm = action.arm
    elif isinstance(action, UnmuteAll):
        for track in _mixable(song):
            if track.mute:
                track.mute = False
    elif isinstance(action, UnsoloAll):
        for track in _mixable(song):
            if track.solo:
                track.solo = False
    elif isinstance(action, UnarmAll):
        for track in song.tracks:
            if track.can_be_armed and track.arm:
                track.arm = False
    elif isinstance(action, StopTrackClips):
        song.visible_tracks[action.track].stop_all_clips()
    elif isinstance(action, StopAllClips):
        song.stop_all_clips()
    elif isinstance(action, Undo):
        song.undo()
    elif isinstance(action, Redo):
        song.redo()
    elif isinstance(action, SetTempo):
        song.tempo = action.bpm
    elif isinstance(action, SetLaunchQuantization):
        song.clip_trigger_quantization = Live.Song.Quantization.values[action.value]
    elif isinstance(action, ShowClip):
        surface.show_clip_when_ready(_slot(song, action.track, action.scene))
    elif isinstance(action, CopyClip):
        source = _slot(song, action.source_track, action.source_scene)
        source.duplicate_clip_to(_slot(song, action.track, action.scene))
    elif isinstance(action, CopyGroupClips):
        # Folded members aren't in visible_tracks: resolve them through song.tracks.
        group = song.visible_tracks[action.track]
        with _undo_step(song):
            for member in live_state.group_members(song, group):
                source = member.clip_slots[action.source_scene]
                target = member.clip_slots[action.scene]
                if source.has_clip and not target.has_clip:
                    source.duplicate_clip_to(target)
    elif isinstance(action, CopyScene):
        with _undo_step(song):
            for track in song.tracks:
                if not track.is_foldable and track.clip_slots[action.source].has_clip:
                    track.clip_slots[action.source].duplicate_clip_to(
                        track.clip_slots[action.target]
                    )
    elif isinstance(action, DeleteClip):
        _slot(song, action.track, action.scene).delete_clip()
    elif isinstance(action, DeleteGroupClips):
        group = song.visible_tracks[action.track]
        with _undo_step(song):
            for member in live_state.group_members(song, group):
                slot = member.clip_slots[action.scene]
                if slot.has_clip:
                    slot.delete_clip()
    elif isinstance(action, DeleteScene):
        song.delete_scene(action.scene)
    elif isinstance(action, CaptureAndInsertScene):
        song.capture_and_insert_scene()
        return SceneSelected(list(song.scenes).index(song.view.selected_scene))
    elif isinstance(action, CaptureMidi):
        song.capture_midi()
    elif isinstance(action, AddScene):
        song.create_scene(-1)
    elif isinstance(action, QuantizeClip):
        clip = live_state.candidate_clip(song, action.target)
        clip.quantize(Live.Song.RecordingQuantization.rec_q_sixtenth, 1.0)
    elif isinstance(action, SetSessionRecord):
        song.session_record = action.on
    elif isinstance(action, SetArrangementRecord):
        song.record_mode = action.on
    elif isinstance(action, ClearBackToArrangement):
        song.back_to_arranger = False
    elif isinstance(action, SetVolume):
        # The track list can change mid-glide: a track that's gone is skipped.
        if action.track < len(song.visible_tracks):
            param = song.visible_tracks[action.track].mixer_device.volume
            param.value = min(max(action.value, param.min), param.max)
    elif isinstance(action, (StoreFxSnapshot, RecallFxSnapshot)):
        start = time.monotonic()
        racks = live_state.read_racks(song)
        logger.info("FX: read %d racks in %.1f ms", len(racks), (time.monotonic() - start) * 1000)
        if isinstance(action, RecallFxSnapshot):
            return RacksRead(action.slot, racks, True, action.bars, action.scene, action.end_beats)
        return RacksRead(action.slot, racks, False, scene=action.scene)
    elif isinstance(action, SetMacros):
        # The Set can change mid-morph: a rack that has moved or gone is skipped.
        targets = live_state.macro_parameters(song, (write[:3] for write in action.writes))
        for (path, rack_name, index, value), parameter in zip(action.writes, targets):
            if parameter is None:
                logger.info("FX: skipped %s macro %d of %r", path, index + 1, rack_name)
                continue
            parameter.value = min(max(value, parameter.min), parameter.max)
    elif isinstance(action, SetFaderParameter):
        # The parameter can change under a touch: a different one is skipped.
        parameter = live_state.fader_parameter(song, surface.core_state, action.row)
        if parameter is None or parameter.name != action.name:
            logger.info("FADERS: skipped row %d, %r not found", action.row + 1, action.name)
        else:
            parameter.value = min(max(action.value, parameter.min), parameter.max)
    elif isinstance(action, BindFader):
        binding, message = _binding(song, action.row)
        return FaderBound(action.row, binding, message)
    elif isinstance(action, SaveFaderBindings):
        song.set_data(values.FADERS_DATA_KEY, action.text)
    elif isinstance(action, StepTrack):
        surface.show_message(_step_track(song, action.step))
    elif isinstance(action, StepDevice):
        surface.show_message(_step_device(song, action.step))
    elif isinstance(action, SaveFxSnapshots):
        song.set_data(values.FX_DATA_KEY, action.text)
    elif isinstance(action, SaveFxScenes):
        song.set_data(values.FX_SCENES_DATA_KEY, action.text)
    elif isinstance(action, HighlightSlot):
        slot = _set_slot(song, action.track, action.scene)
        if slot is None:
            logger.info("SEQ: skipped HighlightSlot, no slot at %d/%d", action.track, action.scene)
        else:
            song.view.highlighted_clip_slot = slot
    elif isinstance(action, SetArms):
        for index, arm in action.arms:
            track = _set_track(song, index)
            if track is not None and track.can_be_armed:
                track.arm = arm
    elif isinstance(action, SelectSetTrack):
        track = _set_track(song, action.track)
        if track is not None:
            song.view.selected_track = track
    elif isinstance(action, EditNotes):
        _edit_notes(song, action)
    elif isinstance(action, RemovePitch):
        clip = _set_clip(song, action)
        if clip is not None:
            with _undo_step(song):
                span = max(clip.loop_end, clip.end_marker)
                clip.remove_notes_extended(action.pitch, 1, 0.0, span)
    elif isinstance(action, ModifyNotes):
        clip = _set_clip(song, action)
        if clip is not None:
            _modify_notes(clip, action.changes)
    elif isinstance(action, SetLoop):
        clip = _set_clip(song, action)
        if clip is not None:
            with _undo_step(song):
                _set_loop(clip, action.start, action.end)
    elif isinstance(action, DuplicateLoop):
        clip = _set_clip(song, action)
        if clip is not None:
            clip.duplicate_loop()
    elif isinstance(action, (SetDrumScroll, SelectDrumPad)):
        track = _set_track(song, action.track)
        rack = live_state.drum_rack(track) if track is not None else None
        if rack is None:
            logger.info("SEQ: skipped %s, no Drum Rack on %d", type(action).__name__, action.track)
        elif isinstance(action, SetDrumScroll):
            rack.view.drum_pads_scroll_position = action.position
        else:
            rack.view.selected_drum_pad = rack.drum_pads[action.note]
    elif isinstance(action, BeginUndoStep):
        song.begin_undo_step()
    elif isinstance(action, EndUndoStep):
        song.end_undo_step()
    elif isinstance(action, ToggleDetailView):
        _toggle_detail_view(Live.Application.get_application().view)
    elif isinstance(action, SetMixer):
        surface.set_mixer(action.on)
    elif isinstance(action, ShowMessage):
        surface.show_message(action.text)
    else:
        raise TypeError(f"unknown action: {action!r}")
    return None
