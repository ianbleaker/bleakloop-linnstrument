"""Adapter: read Live's state into a plain Snapshot. No decisions."""

from dataclasses import replace

from .core import layout
from .core.model import SlotView, Snapshot, TrackView


def read_transport(song, application):
    # Only the transport: enough for the blink clock, without the tracks and slots.
    return Snapshot(
        is_playing=song.is_playing,
        song_beats=song.current_song_time,
        tempo=song.tempo,
        metronome=song.metronome,
        session_view=application.view.is_view_visible("Session"),
    )


def read(song, application, window):
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
    )


def _track(index, track, rows):
    # Some tracks (e.g. groups) have clip slots without being playable: read them as they are.
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
        slots=tuple(_slot(slots[scene]) for scene in rows),
    )


def _slot(slot):
    return SlotView(
        has_clip=slot.has_clip,
        is_playing=slot.is_playing,
        is_triggered=slot.is_triggered,
        is_recording=slot.is_recording,
    )
