from types import SimpleNamespace

import pytest

from BleakLoop import live_state
from BleakLoop.core.layout import Window
from BleakLoop.core.modes import BoundRead, FaderBinding, Morph, MorphMacro
from tests.support import fake_song, fake_track

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


def test_any_armed_reads_armable_tracks_only():
    armed = fake_track("b")
    armed.arm = True
    # Live raises on reading arm from a track that can't be armed.
    unarmable = fake_track("c")
    unarmable.can_be_armed = False
    del unarmable.arm
    assert not read(fake_song([fake_track("a"), unarmable])).any_armed
    assert read(fake_song([fake_track("a"), unarmable, armed])).any_armed


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


DEVICE_FX = SimpleNamespace()


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


def test_no_selected_device_gives_dark_faders():
    assert live_state.read_faders(fader_song(None), DEVICE_FX) == (None,) * 8


# Locators: bound snapshot slots' parameters


def located_track(name, devices=(), sends=("A-Reverb",)):
    track = SimpleNamespace(name=name, devices=list(devices))
    track.mixer_device = SimpleNamespace(
        volume=fake_parameter("Track Volume", 0.85),
        panning=fake_parameter("Track Panning", 0.0),
        sends=[fake_parameter(send, 0.5) for send in sends],
    )
    return track


def located_song(tracks, returns=()):
    song = fake_song(tracks, returns)
    song.master_track = located_track("Main", sends=())
    return song


def test_the_split_view_reads_8_tracks():
    song = fake_song([fake_track(str(i)) for i in range(20)])
    snapshot = live_state.read(song, APPLICATION, Window(), width=8)
    assert [track.name for track in snapshot.tracks] == [str(i) for i in range(8)]


# Sequencer Mode reads


class FakeNote:
    def __init__(self, note_id, pitch, start_time, duration=0.25, velocity=100.0):
        self.note_id, self.pitch, self.start_time = note_id, pitch, start_time
        self.duration, self.velocity = duration, velocity


def fake_clip(notes=(), loop_start=0.0, loop_end=4.0, end_marker=4.0, playing=False):
    clip = SimpleNamespace(
        loop_start=loop_start,
        loop_end=loop_end,
        end_marker=end_marker,
        is_playing=playing,
        playing_position=1.5 if playing else 0.0,
        reads=[],
    )
    clip.get_notes_extended = lambda *args: clip.reads.append(args) or list(notes)
    return clip


def seq_track(name, midi=True, foldable=False, armable=True, arm=False, clips=None, playing=-1):
    track = fake_track(name)
    track.has_midi_input = midi
    track.is_foldable = foldable
    track.can_be_armed = armable
    track.arm = arm
    track.playing_slot_index = playing
    track.devices = []
    clips = clips or {}
    track.clip_slots = [
        SimpleNamespace(
            has_clip=scene in clips,
            clip=clips.get(scene),
            is_playing=False, is_triggered=False, is_recording=False,
            is_group_slot=False, controls_other_clips=False,
            canonical_parent=track,
        )
        for scene in range(4)
    ]
    for clip in clips.values():
        if clip is not None:
            clip.canonical_parent = next(s for s in track.clip_slots if s.clip is clip)
    return track


def seq_song(tracks, selected, scene=0, detail=None):
    scenes = [SimpleNamespace(is_triggered=False, number=n) for n in range(4)]
    song = fake_song(tracks, selected=selected, scenes=scenes)
    song.view.selected_scene = scenes[scene]
    song.view.detail_clip = detail
    song.scale_mode = True
    song.root_note = 2
    song.scale_intervals = [0, 2, 3, 5, 7, 8, 10]
    return song


def test_set_index_arms_and_entry_only_for_the_sequencer():
    keys = seq_track("Keys", arm=True)
    group = seq_track("Group", foldable=True, armable=False)
    # A folded member is in song.tracks but not visible.
    member = seq_track("Member")
    song = seq_song([keys, group, member], selected=keys)
    song.visible_tracks = [keys, group]
    plain = live_state.read(song, APPLICATION, Window())
    assert plain.arms == () and plain.seq_entry is None
    assert plain.tracks[1].set_index is None
    snapshot = live_state.read(song, APPLICATION, Window(), seq_entry=True)
    assert snapshot.arms == (True, None, False)
    assert [track.set_index for track in snapshot.tracks] == [0, 1]
    assert snapshot.seq_entry.selected == 0


def test_read_sequencer_reads_the_highlighted_clip():
    clip = fake_clip(
        [FakeNote(5, 48, 0.25), FakeNote(6, 50, 1.0, 0.5, 90.0)],
        loop_start=1.0,
        loop_end=8.0,
        end_marker=6.0,
        playing=True,
    )
    audio = seq_track("Audio", midi=False)
    keys = seq_track("Keys", clips={2: clip})
    song = seq_song([audio, keys], selected=keys, scene=2)
    view = live_state.read_sequencer(song)
    assert (view.track, view.name, view.scene, view.is_midi) == (1, "Keys", 2, True)
    assert (view.has_clip, view.is_playing, view.position) == (True, True, 1.5)
    assert (view.loop_start, view.loop_end) == (1.0, 8.0)
    assert [(n.note_id, n.pitch, n.start, n.duration, n.velocity) for n in view.notes] == [
        (5, 48, 0.25, 0.25, 100.0),
        (6, 50, 1.0, 0.5, 90.0),
    ]
    assert clip.reads == [(0, 128, 0.0, 8.0)]
    assert (view.scale.on, view.scale.root, view.scale.intervals) == (
        True,
        2,
        (0, 2, 3, 5, 7, 8, 10),
    )


def test_read_sequencer_on_an_empty_slot():
    keys = seq_track("Keys")
    view = live_state.read_sequencer(seq_song([keys], selected=keys, scene=1))
    assert view.track == 0 and view.is_midi and not view.has_clip


def test_read_sequencer_on_an_audio_track_reads_no_notes():
    audio = seq_track("Audio", midi=False, clips={0: fake_clip()})
    view = live_state.read_sequencer(seq_song([audio], selected=audio))
    assert view.track == 0 and not view.is_midi and not view.has_clip


def test_read_sequencer_on_master():
    keys = seq_track("Keys")
    view = live_state.read_sequencer(seq_song([keys], selected=fake_track("Master")))
    assert view.track is None


def test_seq_entry_finds_the_detail_clip_and_the_playing_slot():
    clip = fake_clip()
    keys = seq_track("Keys", playing=3)
    other = seq_track("Other", clips={1: clip})
    song = seq_song([keys, other], selected=keys, scene=2, detail=clip)
    entry = live_state.read_seq_entry(song)
    assert (entry.selected, entry.selected_midi, entry.scene, entry.has_clip) == (0, True, 2, False)
    assert entry.detail == (1, 1)
    assert entry.playing_scene == 3


def test_seq_entry_ignores_an_arrangement_clip():
    clip = fake_clip()
    keys = seq_track("Keys")
    clip.canonical_parent = keys  # an Arrangement clip's parent is its track
    entry = live_state.read_seq_entry(seq_song([keys], selected=keys, detail=clip))
    assert entry.detail is None and entry.playing_scene is None


def test_seq_entry_ignores_a_detail_clip_on_an_audio_track():
    clip = fake_clip()
    keys = seq_track("Keys")
    audio = seq_track("Audio", midi=False, clips={0: clip})
    entry = live_state.read_seq_entry(seq_song([keys, audio], selected=keys, detail=clip))
    assert entry.detail is None


def test_read_position():
    clip = fake_clip(playing=True)
    song = seq_song([], selected=None)
    assert live_state.read_position(song) == (False, 0.0)
    song.view.highlighted_clip_slot = SimpleNamespace(has_clip=True, clip=clip)
    assert live_state.read_position(song) == (True, 1.5)


def fake_rack(scroll=9, selected=36, filled=(36, 38)):
    pads = [SimpleNamespace(note=n, chains=[object()] if n in filled else []) for n in range(128)]
    view = SimpleNamespace(
        drum_pads_scroll_position=scroll,
        selected_drum_pad=pads[selected] if selected is not None else None,
    )
    return SimpleNamespace(
        can_have_drum_pads=True, can_have_chains=True, view=view, drum_pads=pads, chains=[]
    )


def fake_instrument(chains=()):
    return SimpleNamespace(
        can_have_drum_pads=False, can_have_chains=bool(chains), chains=list(chains)
    )


def fake_chain(*devices):
    return SimpleNamespace(devices=list(devices))


def test_read_sequencer_reads_the_first_drum_rack():
    drums = seq_track("Drums")
    drums.devices = [fake_instrument(), fake_rack(), fake_rack(scroll=3)]
    view = live_state.read_sequencer(seq_song([drums], selected=drums))
    assert view.drum.scroll == 9
    assert view.drum.selected == 36
    assert view.drum.filled == frozenset({36, 38})


def test_a_drum_rack_with_no_selected_pad():
    drums = seq_track("Drums")
    drums.devices = [fake_rack(selected=None)]
    view = live_state.read_sequencer(seq_song([drums], selected=drums))
    assert view.drum.selected is None


def test_a_melodic_track_has_no_drum_view():
    keys = seq_track("Keys")
    keys.devices = [fake_instrument(), fake_instrument([fake_chain(fake_instrument())])]
    assert live_state.read_sequencer(seq_song([keys], selected=keys)).drum is None


def test_a_drum_rack_inside_an_instrument_rack():
    drums = seq_track("Drums")
    inner = fake_rack(scroll=4)
    instrument_rack = fake_instrument([fake_chain(fake_instrument()), fake_chain(inner)])
    drums.devices = [instrument_rack, fake_rack(scroll=9)]
    assert live_state.drum_rack(drums) is inner
    assert live_state.read_sequencer(seq_song([drums], selected=drums)).drum.scroll == 4


def test_a_drum_rack_s_own_pads_arent_searched():
    outer = fake_rack(scroll=2)
    outer.chains = [fake_chain(fake_rack(scroll=5))]
    track = SimpleNamespace(devices=[outer])
    assert live_state.drum_rack(track) is outer


def test_read_fx_scenes_store():
    stored = {"BleakLoop.fx.scenes": "text"}
    song = SimpleNamespace(get_data=lambda key, default: stored.get(key, default))
    assert live_state.read_fx_scenes_store(song) == "text"
    assert live_state.read_fx_scenes_store(SimpleNamespace(get_data=lambda k, d: d)) == ""


def _launch_song(*triggered):
    return SimpleNamespace(scenes=[SimpleNamespace(is_triggered=t) for t in triggered])


@pytest.mark.parametrize(
    "triggered, slot, expected",
    [
        ((False, True), 1, True),  # waiting
        ((False, False), 1, False),  # started
        ((True, False), 1, None),  # another scene took the wait over
        ((False,), 1, None),  # the scene has gone
        ((False, False), None, None),  # its scene was deleted
    ],
)
def test_read_launch_triggered(triggered, slot, expected):
    morph = Morph(slot, 0.0, 8.0, 0.0, scene=True, launch=True)
    assert live_state.read_launch_triggered(_launch_song(*triggered), morph) is expected


def test_read_launch_triggered_ignores_other_morphs():
    morph = Morph(0, 0.0, 8.0, 0.0, scene=True)
    assert live_state.read_launch_triggered(_launch_song(True), morph) is None


# Morph targets: a rack macro or a parameter locator


def target_song():
    rack = fake_device("FX", [fake_parameter(f"Macro {i}", float(i)) for i in range(1, 9)], rack=True)
    filter_ = fake_device("Auto Filter", [fake_parameter("Frequency", 40.0)])
    return located_song([located_track("Bass", [rack, filter_])])


def test_target_parameters_resolve_macros_and_locators():
    song = target_song()
    keys = (
        (("track", 0, 0), "FX", 2),
        FaderBinding("Bass", 0, "Auto Filter", 0, 1, "Frequency"),
        FaderBinding("Bass", 0, None, 0, 0, "Track Volume"),
        FaderBinding("Bass", 0, "Auto Filter", 0, 1, "Resonance"),
        (("track", 0, 1), "FX", 0),
    )
    found = live_state.target_parameters(song, keys)
    assert [p and (p.name, p.value) for p in found] == [
        ("Macro 3", 3.0), ("Frequency", 40.0), ("Track Volume", 0.85), None, None,
    ]


def test_read_macro_values_reads_locators_too():
    keys = ((("track", 0, 0), "FX", 0), FaderBinding("Bass", 0, "Auto Filter", 0, 1, "Frequency"))
    morph = Morph(0, 0.0, 4.0, 0.0, tuple(MorphMacro(key, 0.0, 1.0, False, 0.0, 1.0) for key in keys))
    assert live_state.read_macro_values(target_song(), morph) == (1.0, 40.0)


def test_a_renamed_macro_is_still_found_by_its_index():
    song = target_song()
    rack = song.tracks[0].devices[0]
    rack.parameters[2].name = "Cutoff"
    (found,) = live_state.read_bound(song, (FaderBinding("Bass", 0, "FX", 0, 2, "Macro 2"),))
    assert found.name == "Cutoff" and found.key == (("track", 0, 0), "FX", 1)


def test_read_bound_gives_locator_keys_for_other_parameters_and_none_when_missing():
    song = target_song()
    frequency = FaderBinding("Bass", 0, "Auto Filter", 0, 1, "Frequency")
    found = live_state.read_bound(song, (frequency, FaderBinding("Bass", 0, "Auto Filter", 0, 1, "Q")))
    assert found == (BoundRead(frequency, "Frequency", 40.0, 0.0, 127.0, False, owner="Auto Filter"), None)


def test_read_bound_carries_lives_text_for_the_value():
    song = target_song()
    frequency = song.tracks[0].devices[1].parameters[1]
    frequency.str_for_value = lambda value: f"{value:.0f} Hz"
    (found,) = live_state.read_bound(song, (FaderBinding("Bass", 0, "Auto Filter", 0, 1, "Frequency"),))
    assert found.text == "40 Hz"


def test_read_bound_gives_the_punch_in_values_clamped_with_their_text():
    song = target_song()
    frequency = song.tracks[0].devices[1].parameters[1]
    frequency.str_for_value = lambda value: f"{value:.0f} Hz"
    locator = FaderBinding("Bass", 0, "Auto Filter", 0, 1, "Frequency")
    (inside,) = live_state.read_bound(song, (locator,), (90.0,))
    assert (inside.target, inside.target_text, inside.text) == (90.0, "90 Hz", "40 Hz")
    (above,) = live_state.read_bound(song, (locator,), (500.0,))
    assert (above.target, above.target_text) == (127.0, "127 Hz")
    (none,) = live_state.read_bound(song, (locator,))
    assert (none.target, none.target_text) == (None, "")


def test_read_bound_gives_no_target_text_when_live_has_none():
    song = target_song()
    frequency = song.tracks[0].devices[1].parameters[1]

    def fails(value):
        raise RuntimeError

    frequency.str_for_value = fails
    locator = FaderBinding("Bass", 0, "Auto Filter", 0, 1, "Frequency")
    (found,) = live_state.read_bound(song, (locator, locator), (90.0,))[:1]
    assert (found.target, found.target_text) == (90.0, "")
