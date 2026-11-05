"""Fakes and snapshots shared by more than one test file."""

from types import SimpleNamespace

from BleakLoop.core import layout
from BleakLoop.core.layout import Window
from BleakLoop.core.model import SlotView, Snapshot, TrackView


def session_snapshot(track_count=20, scene_count=10, window=Window(), **k):
    visible = range(window.track, min(window.track + 13, track_count))
    rows = range(window.scene, min(window.scene + layout.WINDOW_SCENES, scene_count))
    tracks = tuple(
        TrackView(index=i, name=f"T{i + 1}", slots=tuple(SlotView() for _ in rows))
        for i in visible
    )
    return Snapshot(
        is_playing=False,
        song_beats=0.0,
        tempo=120.0,
        metronome=False,
        session_view=True,
        track_count=track_count,
        scene_count=scene_count,
        tracks=tracks,
        **k,
    )


SNAP = session_snapshot()


class FakeSlot:
    def __init__(self, has_clip=False):
        self.has_clip = has_clip
        self.is_playing = False
        self.is_triggered = False
        self.is_recording = False
        self.is_group_slot = False
        self.controls_other_clips = False
        self.copied_to = None

    def duplicate_clip_to(self, target):
        self.copied_to = target

    def delete_clip(self):
        self.has_clip = False


def fake_track(name="T", arm=False, mute=False, solo=False, clips=(), is_foldable=False, group=None):
    # clips: the scenes that have a clip; group: the group track this one sits in.
    return SimpleNamespace(
        name=name,
        color=0,
        can_be_armed=True,
        arm=arm,
        implicit_arm=False,
        mute=mute,
        solo=solo,
        has_midi_input=False,
        is_foldable=is_foldable,
        is_grouped=group is not None,
        group_track=group,
        mixer_device=SimpleNamespace(volume=SimpleNamespace(value=0.85)),
        clip_slots=[FakeSlot(scene in clips) for scene in range(8)],
        playing_slot_index=-1,
    )


def fake_song(tracks, returns=(), selected=None, scenes=(), exclusive_solo=False, visible=None):
    # undo: the undo-step calls, in order.
    undo = []
    return SimpleNamespace(
        is_playing=False,
        current_song_time=0.0,
        tempo=120.0,
        metronome=False,
        loop=False,
        loop_start=0.0,
        loop_length=16.0,
        visible_tracks=list(tracks if visible is None else visible),
        tracks=list(tracks),
        return_tracks=list(returns),
        scenes=list(scenes),
        exclusive_solo=exclusive_solo,
        can_undo=False,
        can_redo=False,
        clip_trigger_quantization=4,
        signature_numerator=4,
        signature_denominator=4,
        session_record=False,
        arrangement_overdub=False,
        record_mode=False,
        back_to_arranger=False,
        can_capture_midi=False,
        undo=undo,
        begin_undo_step=lambda: undo.append("begin"),
        end_undo_step=lambda: undo.append("end"),
        view=SimpleNamespace(
            selected_track=selected,
            highlighted_clip_slot=None,
            detail_clip=None,
        ),
    )
