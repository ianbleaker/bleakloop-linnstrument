from types import SimpleNamespace

from BleakLoop import live_state
from BleakLoop.core.layout import Window


def fake_track(name, mute=False, solo=False):
    return SimpleNamespace(
        name=name,
        color=0,
        can_be_armed=True,
        arm=False,
        implicit_arm=False,
        mute=mute,
        solo=solo,
        has_midi_input=False,
        is_foldable=False,
        mixer_device=SimpleNamespace(volume=SimpleNamespace(value=0.85)),
        clip_slots=[SimpleNamespace(
            has_clip=False, is_playing=False, is_triggered=False, is_recording=False
        )] * 8,
        playing_slot_index=-1,
    )


def fake_song(tracks, returns=(), selected=None, scenes=()):
    return SimpleNamespace(
        is_playing=False,
        current_song_time=0.0,
        tempo=120.0,
        metronome=False,
        visible_tracks=list(tracks),
        tracks=list(tracks),
        return_tracks=list(returns),
        scenes=list(scenes),
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
        view=SimpleNamespace(
            selected_track=selected,
            highlighted_clip_slot=None,
            detail_clip=None,
        ),
    )


APPLICATION = SimpleNamespace(view=SimpleNamespace(is_view_visible=lambda name: True))


def read(song):
    return live_state.read(song, APPLICATION, Window())


def test_scene_triggered_per_window_row():
    scenes = [SimpleNamespace(is_triggered=i == 1) for i in range(8)]
    snapshot = read(fake_song([fake_track("a")], scenes=scenes))
    assert snapshot.scene_triggered == (False, True, False, False, False, False)


def test_selected_track():
    a, b = fake_track("a"), fake_track("b")
    snapshot = read(fake_song([a, b], selected=b))
    assert [track.selected for track in snapshot.tracks] == [False, True]


def test_return_track_selected_selects_no_track():
    a, ret = fake_track("a"), fake_track("A Return")
    snapshot = read(fake_song([a], [ret], selected=ret))
    assert not snapshot.tracks[0].selected


def test_nothing_muted_or_soloed():
    snapshot = read(fake_song([fake_track("a")], [fake_track("A Return")]))
    assert not snapshot.any_muted
    assert not snapshot.any_soloed


def test_muted_track():
    snapshot = read(fake_song([fake_track("a"), fake_track("b", mute=True)]))
    assert snapshot.any_muted
    assert not snapshot.any_soloed


def test_soloed_return_track():
    snapshot = read(fake_song([fake_track("a")], [fake_track("A Return", solo=True)]))
    assert snapshot.any_soloed
    assert not snapshot.any_muted


def test_muted_return_track():
    snapshot = read(fake_song([fake_track("a")], [fake_track("A Return", mute=True)]))
    assert snapshot.any_muted


def test_track_outside_the_window_counts():
    tracks = [fake_track(str(i)) for i in range(14)] + [fake_track("last", solo=True)]
    snapshot = read(fake_song(tracks))
    assert len(snapshot.tracks) == 13
    assert snapshot.any_soloed
