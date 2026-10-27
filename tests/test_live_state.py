from types import SimpleNamespace

from BleakLoop import live_state
from BleakLoop.core.layout import Window
from BleakLoop.core.modes import FaderBinding


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
        is_grouped=False,
        group_track=None,
        mixer_device=SimpleNamespace(volume=SimpleNamespace(value=0.85)),
        clip_slots=[SimpleNamespace(
            has_clip=False, is_playing=False, is_triggered=False, is_recording=False,
            is_group_slot=False, controls_other_clips=False,
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


def test_group_slot_with_member_clips():
    group = fake_track("g")
    group.is_foldable = True
    slot = SimpleNamespace(**vars(group.clip_slots[0]))
    slot.is_group_slot = slot.controls_other_clips = True
    group.clip_slots = [slot] + group.clip_slots[1:]
    scenes = [SimpleNamespace(is_triggered=False)] * 2
    slots = read(fake_song([group], scenes=scenes)).tracks[0].slots
    assert slots[0].controls_other_clips and not slots[0].has_clip
    assert not slots[1].controls_other_clips


def grouped(track, group):
    track.is_grouped, track.group_track = True, group
    return track


def fake_group(name):
    group = fake_track(name)
    group.is_foldable = True
    return group


def test_group_members_direct():
    group = fake_group("g")
    a, b = grouped(fake_track("a"), group), grouped(fake_track("b"), group)
    song = fake_song([group, a, b])
    assert live_state.group_members(song, group) == [a, b]


def test_group_members_nested():
    group = fake_group("g")
    inner = grouped(fake_group("inner"), group)
    a, b = grouped(fake_track("a"), inner), grouped(fake_track("b"), group)
    song = fake_song([group, inner, a, b])
    assert live_state.group_members(song, group) == [a, b]


def test_group_members_excludes_other_tracks():
    group, other = fake_group("g"), fake_group("other")
    a = grouped(fake_track("a"), group)
    outside, loose = grouped(fake_track("outside"), other), fake_track("loose")
    song = fake_song([group, a, other, outside, loose])
    assert live_state.group_members(song, group) == [a]


def with_clip(track, scene):
    slot = SimpleNamespace(**vars(track.clip_slots[scene]))
    slot.has_clip = True
    track.clip_slots = track.clip_slots[:scene] + [slot] + track.clip_slots[scene + 1 :]
    return track


def read_members(song, scene_clips):
    snapshot = live_state.read(song, APPLICATION, Window(), scene_clips=scene_clips)
    return [track.slots[0].member_clips for track in snapshot.tracks]


def group_song():
    group = fake_group("g")
    a = with_clip(grouped(fake_track("a"), group), 0)
    b = grouped(fake_track("b"), group)
    return fake_song([group, a, b], scenes=[SimpleNamespace(is_triggered=False)] * 2)


def test_group_member_clips_while_copy_held():
    assert read_members(group_song(), True) == [(True, False), (), ()]


def test_group_member_clips_not_read_otherwise():
    assert read_members(group_song(), False) == [(), (), ()]


# Faders


def fake_parameter(name, value=0.0, quantized=False):
    return SimpleNamespace(name=name, value=value, min=0.0, max=127.0, is_quantized=quantized)


def fake_device(name, parameters, rack=False, macros=8, parent=None):
    return SimpleNamespace(
        name=name,
        parameters=[fake_parameter("Device On")] + parameters,
        can_have_chains=rack,
        visible_macro_count=macros,
        canonical_parent=parent,
    )


def fader_song(device, tracks=()):
    song = fake_song(tracks)
    song.appointed_device = device
    song.master_track = SimpleNamespace(devices=[])
    return song


DEVICE_FX = SimpleNamespace(fader_source="device")


def test_faders_of_a_rack_are_its_macros_with_their_identity():
    track = SimpleNamespace(devices=[])
    rack = fake_device(
        "FX", [fake_parameter(f"Macro {i}", i) for i in range(1, 17)], rack=True, macros=10,
        parent=track,
    )
    track.devices = [fake_device("Synth", []), rack]
    views = live_state.read_faders(fader_song(rack, [fake_track("a"), track]), DEVICE_FX)
    assert [view.name for view in views] == [f"Macro {i}" for i in range(1, 9)]
    assert views[2].value == 3
    assert views[2].macro == (("track", 1, 1), "FX", 2)


def test_a_nested_rack_has_no_macro_identity():
    rack = fake_device("FX", [fake_parameter("M1")], rack=True, macros=1, parent=object())
    views = live_state.read_faders(fader_song(rack), DEVICE_FX)
    assert views[0].name == "M1" and views[0].macro is None


def test_faders_of_a_device_skip_device_on_and_dark_past_its_parameters():
    device = fake_device("EQ", [fake_parameter(f"P{i}", quantized=i == 2) for i in range(1, 4)])
    views = live_state.read_faders(fader_song(device), DEVICE_FX)
    assert [view and view.name for view in views] == ["P1", "P2", "P3"] + [None] * 5
    assert views[1].is_quantized and views[0].macro is None


def test_no_selected_device_or_mapped_fx_gives_dark_faders():
    assert live_state.read_faders(fader_song(None), DEVICE_FX) == (None,) * 8
    device = fake_device("EQ", [fake_parameter("P1")])
    mapped = SimpleNamespace(fader_source="mapped", fader_bindings=(None,) * 8)
    assert live_state.read_faders(fader_song(device), mapped) == (None,) * 8


# Mapped FX


def mapped_track(name, devices=(), sends=("A-Reverb",)):
    track = SimpleNamespace(name=name, devices=list(devices))
    track.mixer_device = SimpleNamespace(
        volume=fake_parameter("Track Volume", 0.85),
        panning=fake_parameter("Track Panning", 0.0),
        sends=[fake_parameter(send, 0.5) for send in sends],
    )
    return track


def mapped_song(tracks, returns=()):
    song = fake_song(tracks, returns)
    song.master_track = mapped_track("Main", sends=())
    return song


def mapped(*bindings):
    return SimpleNamespace(
        fader_source="mapped", fader_bindings=bindings + (None,) * (8 - len(bindings))
    )


def test_mapped_faders_resolve_device_and_mixer_parameters():
    filter_ = fake_device("Auto Filter", [fake_parameter("Frequency", 40.0)])
    bass = mapped_track("Bass", [filter_])
    reverb = mapped_track("A Reverb", sends=())
    song = mapped_song([bass], [reverb])
    views = live_state.read_faders(
        song,
        mapped(
            FaderBinding("Bass", 0, "Auto Filter", 0, 1, "Frequency"),
            FaderBinding("A Reverb", 0, None, 0, 0, "Track Volume"),
            FaderBinding("Bass", 0, None, 0, 1, "Track Panning"),
            FaderBinding("Bass", 0, None, 0, 2, "A-Reverb"),
            FaderBinding("Main", 0, None, 0, 0, "Track Volume"),
        ),
    )
    assert [view and view.name for view in views[:6]] == [
        "Frequency", "Track Volume", "Track Panning", "A-Reverb", "Track Volume", None,
    ]
    assert views[0].value == 40.0 and views[0].macro is None


def test_mapped_faders_tell_same_named_tracks_and_devices_apart():
    first = mapped_track("Synth", [fake_device("EQ", [fake_parameter("Gain", 1.0)])])
    second = mapped_track(
        "Synth",
        [
            fake_device("EQ", [fake_parameter("Gain", 2.0)]),
            fake_device("EQ", [fake_parameter("Gain", 3.0)]),
        ],
    )
    song = mapped_song([first, second])
    views = live_state.read_faders(
        song,
        mapped(
            FaderBinding("Synth", 0, "EQ", 0, 1, "Gain"),
            FaderBinding("Synth", 1, "EQ", 1, 1, "Gain"),
            FaderBinding("Synth", 2, "EQ", 0, 1, "Gain"),
        ),
    )
    assert [view and view.value for view in views[:3]] == [1.0, 3.0, None]


def test_a_renamed_or_missing_parameter_resolves_to_nothing():
    song = mapped_song([mapped_track("Bass", [fake_device("EQ", [fake_parameter("Gain")])])])
    views = live_state.read_faders(
        song,
        mapped(
            FaderBinding("Bass", 0, "EQ", 0, 1, "Frequency"),
            FaderBinding("Bass", 0, "EQ", 0, 9, "Gain"),
            FaderBinding("Bass", 0, "Comp", 0, 1, "Gain"),
            FaderBinding("Drums", 0, "EQ", 0, 1, "Gain"),
        ),
    )
    assert views == (None,) * 8


def test_a_mapped_rack_macro_carries_its_identity():
    track = mapped_track("Bass")
    rack = fake_device(
        "FX", [fake_parameter(f"Macro {i}") for i in range(1, 9)], rack=True, macros=8,
        parent=track,
    )
    track.devices = [rack]
    views = live_state.read_faders(
        mapped_song([track]), mapped(FaderBinding("Bass", 0, "FX", 0, 3, "Macro 3"))
    )
    assert views[0].macro == (("track", 0, 0), "FX", 2)


def test_the_split_view_reads_8_tracks():
    song = fake_song([fake_track(str(i)) for i in range(20)])
    snapshot = live_state.read(song, APPLICATION, Window(), width=8)
    assert [track.name for track in snapshot.tracks] == [str(i) for i in range(8)]
