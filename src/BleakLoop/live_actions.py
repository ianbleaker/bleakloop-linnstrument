"""Adapter: carry out core actions on Live objects. No decisions."""

import Live

from .core.model import (
    ArmExclusive,
    EnterMode,
    FireScene,
    FireSlot,
    Redo,
    SelectTrack,
    SetLaunchQuantization,
    SetTempo,
    ShowMessage,
    StopAllClips,
    StopTrackClips,
    ToggleMetronome,
    ToggleMute,
    TogglePlay,
    ToggleSolo,
    Undo,
)


def apply(action, song, surface):
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
        slot = song.visible_tracks[action.track].clip_slots[action.scene]
        if action.legato:
            slot.fire(force_legato=True)
        else:
            slot.fire()
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
    elif isinstance(action, ShowMessage):
        surface.show_message(action.text)
    else:
        raise TypeError(f"unknown action: {action!r}")
