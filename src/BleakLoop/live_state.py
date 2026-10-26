"""Adapter: read Live's state into a plain Snapshot. No decisions."""

from dataclasses import replace

from .core import layout
from .core.model import ClipTarget, ClipView, SelectedTrack, SlotView, Snapshot, TrackView


def read_transport(song, application):
    # Only the transport: enough for the blink clock, without the tracks and slots.
    return Snapshot(
        is_playing=song.is_playing,
        song_beats=song.current_song_time,
        tempo=song.tempo,
        metronome=song.metronome,
        session_view=application.view.is_view_visible("Session"),
    )


def read(song, application, window, scene_clips=False, selected=False):
    tracks = list(song.visible_tracks)
    scenes = list(song.scenes)
    rows = range(window.scene, min(window.scene + layout.WINDOW_SCENES, len(scenes)))
    columns = range(window.track, min(window.track + layout.WINDOW_TRACKS, len(tracks)))
    return replace(
        read_transport(song, application),
        track_count=len(tracks),
        scene_count=len(scenes),
        tracks=tuple(_track(i, tracks[i], rows) for i in columns),
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
        # Every scene of one track: only in Linnstrument Mode, which is the only reader.
        selected_track=_selected_track(song, tracks, scenes) if selected else None,
        selected_scene=scenes.index(song.view.selected_scene) if selected else 0,
        can_capture_midi=song.can_capture_midi,
    )


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


def _track(index, track, rows):
    slots = track.clip_slots
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
        volume=track.mixer_device.volume.value,
        slots=tuple(_slot(slots[scene]) for scene in rows),
    )


def _slot(slot):
    return SlotView(
        has_clip=slot.has_clip,
        is_playing=slot.is_playing,
        is_triggered=slot.is_triggered,
        is_recording=slot.is_recording,
    )
