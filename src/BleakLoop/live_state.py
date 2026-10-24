"""Adapter: read Live's state into a plain Snapshot. No decisions."""

from .core.model import Snapshot


def read(song, application):
    return Snapshot(
        is_playing=song.is_playing,
        song_beats=song.current_song_time,
        tempo=song.tempo,
        metronome=song.metronome,
        session_view=application.view.is_view_visible("Session"),
    )
