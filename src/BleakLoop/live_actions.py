"""Adapter: carry out core actions on Live objects. No decisions."""

import Live

from . import live_state
from .core.model import (
    AddScene,
    ArmExclusive,
    BeginUndoStep,
    CaptureAndInsertScene,
    CaptureMidi,
    ClearBackToArrangement,
    CopyClip,
    CopyScene,
    DeleteClip,
    DeleteScene,
    EndUndoStep,
    EnterMode,
    FireScene,
    FireSlot,
    QuantizeClip,
    Redo,
    SceneSelected,
    SelectTrack,
    SetArrangementRecord,
    SetLaunchQuantization,
    SetMixer,
    SetSessionRecord,
    SetTempo,
    SetVolume,
    ShowClip,
    ShowMessage,
    StopAllClips,
    StopTrackClips,
    ToggleMetronome,
    ToggleMute,
    TogglePlay,
    ToggleSolo,
    Undo,
)


def _slot(song, track, scene):
    return song.visible_tracks[track].clip_slots[scene]


def apply(action, song, surface):
    # Returns None, or a follow-up event for the core (Capture).
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
        track = song.visible_tracks[action.track]
        track.solo = not track.solo
    elif isinstance(action, SelectTrack):
        song.view.selected_track = song.visible_tracks[action.track]
    elif isinstance(action, ArmExclusive):
        target = song.visible_tracks[action.track]
        for track in song.tracks:
            if track != target and track.can_be_armed and track.arm:
                track.arm = False
        target.arm = action.arm
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
    elif isinstance(action, CopyScene):
        for track in song.tracks:
            if not track.is_foldable and track.clip_slots[action.source].has_clip:
                track.clip_slots[action.source].duplicate_clip_to(
                    track.clip_slots[action.target]
                )
    elif isinstance(action, DeleteClip):
        _slot(song, action.track, action.scene).delete_clip()
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
    elif isinstance(action, BeginUndoStep):
        song.begin_undo_step()
    elif isinstance(action, EndUndoStep):
        song.end_undo_step()
    elif isinstance(action, SetMixer):
        surface.set_mixer(action.on)
    elif isinstance(action, ShowMessage):
        surface.show_message(action.text)
    else:
        raise TypeError(f"unknown action: {action!r}")
    return None
