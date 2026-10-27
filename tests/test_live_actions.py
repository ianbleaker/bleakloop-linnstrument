import sys
from types import ModuleType, SimpleNamespace

import pytest

# Live exists only inside Live: the handlers tested here don't touch it.
sys.modules.setdefault("Live", ModuleType("Live"))

from BleakLoop import live_actions  # noqa: E402
from BleakLoop.core.modes import FaderBinding  # noqa: E402
from BleakLoop.core.model import (  # noqa: E402
    BindFader,
    CopyGroupClips,
    CopyScene,
    DeleteGroupClips,
    DuplicateLoop,
    EditNotes,
    FaderBound,
    HighlightSlot,
    RacksRead,
    RecallFxSnapshot,
    ModifyNotes,
    RemovePitch,
    SelectDrumPad,
    SaveFaderBindings,
    SaveFxScenes,
    SelectSetTrack,
    SetArm,
    SetArms,
    SetDrumScroll,
    SetFaderParameter,
    SetLoop,
    StepDevice,
    StepTrack,
    StoreFxSnapshot,
    ToggleSolo,
    UnmuteAll,
    UnsoloAll,
)


class FakeSlot:
    def __init__(self, has_clip=False):
        self.has_clip = has_clip
        self.copied_to = None

    def duplicate_clip_to(self, target):
        self.copied_to = target

    def delete_clip(self):
        self.has_clip = False


def fake_track(arm=False, mute=False, solo=False, clips=(), is_foldable=False, group=None):
    # clips: the scenes that have a clip; group: the group track this one sits in.
    return SimpleNamespace(
        can_be_armed=True,
        arm=arm,
        mute=mute,
        solo=solo,
        clip_slots=[FakeSlot(scene in clips) for scene in range(4)],
        is_foldable=is_foldable,
        is_grouped=group is not None,
        group_track=group,
    )


def fake_song(tracks, returns=(), exclusive_solo=False, visible=None):
    # undo: the undo-step calls, in order.
    undo = []
    return SimpleNamespace(
        tracks=list(tracks),
        visible_tracks=list(tracks if visible is None else visible),
        return_tracks=list(returns),
        exclusive_solo=exclusive_solo,
        undo=undo,
        begin_undo_step=lambda: undo.append("begin"),
        end_undo_step=lambda: undo.append("end"),
    )


def apply(action, song):
    return live_actions.apply(action, song, surface=None)


@pytest.mark.parametrize("arm", [True, False])
def test_set_arm_leaves_other_tracks(arm):
    a, b = fake_track(arm=True), fake_track(arm=not arm)
    apply(SetArm(1, arm), fake_song([a, b]))
    assert a.arm
    assert b.arm is arm


def test_unmute_all_covers_tracks_and_returns():
    tracks = [fake_track(mute=True), fake_track()]
    returns = [fake_track(mute=True)]
    apply(UnmuteAll(), fake_song(tracks, returns))
    assert not any(track.mute for track in tracks + returns)


def test_unsolo_all_covers_tracks_and_returns():
    tracks = [fake_track(solo=True), fake_track(solo=True)]
    returns = [fake_track(solo=True)]
    apply(UnsoloAll(), fake_song(tracks, returns))
    assert not any(track.solo for track in tracks + returns)


def test_solo_adds_without_exclusive_solo():
    a, b, ret = fake_track(solo=True), fake_track(), fake_track(solo=True)
    apply(ToggleSolo(1), fake_song([a, b], [ret], exclusive_solo=False))
    assert (a.solo, b.solo, ret.solo) == (True, True, True)


def test_exclusive_solo_unsolos_the_rest():
    a, b, ret = fake_track(solo=True), fake_track(), fake_track(solo=True)
    apply(ToggleSolo(1), fake_song([a, b], [ret], exclusive_solo=True))
    assert (a.solo, b.solo, ret.solo) == (False, True, False)


@pytest.mark.parametrize("exclusive_solo", [True, False])
def test_unsolo_leaves_the_rest(exclusive_solo):
    a, b = fake_track(solo=True), fake_track(solo=True)
    apply(ToggleSolo(1), fake_song([a, b], exclusive_solo=exclusive_solo))
    assert (a.solo, b.solo) == (True, False)


def test_copy_group_clips_copies_each_member_to_its_own_slot():
    group = fake_track(is_foldable=True)
    inner = fake_track(is_foldable=True, group=group)
    folded = fake_track(clips=(0,), group=inner)  # in a folded nested group
    direct = fake_track(clips=(0, 2), group=group)  # already filled in the target row
    empty = fake_track(clips=(2,), group=group)  # no source clip
    outside = fake_track(clips=(0,))
    tracks = [outside, group, inner, folded, direct, empty]
    song = fake_song(tracks, visible=[outside, group, inner, direct, empty])
    apply(CopyGroupClips(1, 0, 2), song)
    assert folded.clip_slots[0].copied_to is folded.clip_slots[2]
    assert direct.clip_slots[0].copied_to is None
    assert all(slot.copied_to is None for slot in empty.clip_slots + outside.clip_slots)
    assert song.undo == ["begin", "end"]


def test_copy_scene_is_one_undo_step():
    group = fake_track(is_foldable=True)
    full = fake_track(clips=(0,), group=group)
    empty = fake_track()
    song = fake_song([group, full, empty])
    apply(CopyScene(0, 1), song)
    assert full.clip_slots[0].copied_to is full.clip_slots[1]
    assert empty.clip_slots[0].copied_to is None
    assert song.undo == ["begin", "end"]


def test_delete_group_clips_deletes_each_member_clip_in_the_row():
    group = fake_track(is_foldable=True)
    inner = fake_track(is_foldable=True, group=group)
    folded = fake_track(clips=(0, 1), group=inner)  # in a folded nested group
    direct = fake_track(clips=(0,), group=group)
    outside = fake_track(clips=(0,))
    tracks = [outside, group, inner, folded, direct]
    song = fake_song(tracks, visible=[outside, group, inner, direct])
    apply(DeleteGroupClips(1, 0), song)
    assert not folded.clip_slots[0].has_clip and folded.clip_slots[1].has_clip
    assert not direct.clip_slots[0].has_clip
    assert outside.clip_slots[0].has_clip
    assert song.undo == ["begin", "end"]


def test_delete_group_clips_closes_its_undo_step_on_failure():
    group = fake_track(is_foldable=True)
    member = fake_track(clips=(0,), group=group)
    member.clip_slots[0].delete_clip = lambda: 1 / 0
    song = fake_song([group, member], visible=[group])
    with pytest.raises(ZeroDivisionError):
        apply(DeleteGroupClips(0, 0), song)
    assert song.undo == ["begin", "end"]


# Faders and Dev


class FakeParameter:
    def __init__(self, name, value=0.0):
        self.name, self.value, self.min, self.max = name, value, 0.0, 1.0


def fader_song(parameters):
    device = SimpleNamespace(
        can_have_chains=False, parameters=[FakeParameter("Device On")] + parameters
    )
    return SimpleNamespace(appointed_device=device)


FADER_SURFACE = SimpleNamespace(core_state=SimpleNamespace(fader_source="device"))


def test_set_fader_parameter_writes_clamped():
    parameter = FakeParameter("Cutoff")
    song = fader_song([parameter])
    live_actions.apply(SetFaderParameter(0, "Cutoff", 1.5), song, FADER_SURFACE)
    assert parameter.value == 1.0


def test_set_fader_parameter_skips_a_different_parameter():
    parameter = FakeParameter("Resonance", 0.25)
    song = fader_song([parameter])
    live_actions.apply(SetFaderParameter(0, "Cutoff", 0.9), song, FADER_SURFACE)
    assert parameter.value == 0.25


def test_set_fader_parameter_skips_a_missing_row():
    song = fader_song([FakeParameter("Cutoff")])
    live_actions.apply(SetFaderParameter(5, "Cutoff", 0.9), song, FADER_SURFACE)


class Messages:
    def __init__(self):
        self.shown = []

    def show_message(self, text):
        self.shown.append(text)


def dev_song(selected, device=None):
    a, b = SimpleNamespace(name="A"), SimpleNamespace(name="B")
    ret, master = SimpleNamespace(name="Reverb"), SimpleNamespace(name="Master")
    tracks = {"A": a, "B": b, "Reverb": ret, "Master": master}
    return SimpleNamespace(
        visible_tracks=[a, b],
        return_tracks=[ret],
        master_track=master,
        view=SimpleNamespace(selected_track=tracks[selected]),
    )


@pytest.mark.parametrize(
    "selected, step, expected",
    [("A", 1, "B"), ("B", 1, "Reverb"), ("Reverb", 1, "Master"), ("B", -1, "A")],
)
def test_step_track_through_tracks_returns_and_master(selected, step, expected):
    song, surface = dev_song(selected), Messages()
    live_actions.apply(StepTrack(step), song, surface)
    assert song.view.selected_track.name == expected
    assert surface.shown == [expected]


@pytest.mark.parametrize("selected, step", [("A", -1), ("Master", 1)])
def test_step_track_stops_at_the_ends(selected, step):
    song, surface = dev_song(selected), Messages()
    live_actions.apply(StepTrack(step), song, surface)
    assert song.view.selected_track.name == selected
    assert surface.shown == ["No more tracks"]


def device_song(selected_index=None, nested=False):
    track = SimpleNamespace()
    devices = [SimpleNamespace(name=n, canonical_parent=track) for n in ("Synth", "Rack", "EQ")]
    selected = None if selected_index is None else devices[selected_index]
    if nested:
        chain = SimpleNamespace(canonical_parent=devices[1])
        selected = SimpleNamespace(name="Inner", canonical_parent=chain)
    track.devices = devices
    track.view = SimpleNamespace(selected_device=selected)
    chosen = []
    song = SimpleNamespace(view=SimpleNamespace(selected_track=track, select_device=chosen.append))
    return song, chosen


def test_step_device_next_and_previous():
    song, chosen = device_song(0)
    surface = Messages()
    live_actions.apply(StepDevice(1), song, surface)
    assert [d.name for d in chosen] == ["Rack"] and surface.shown == ["Rack"]
    assert song.appointed_device.name == "Rack"


def test_step_device_from_inside_a_rack_steps_from_the_rack():
    song, chosen = device_song(nested=True)
    live_actions.apply(StepDevice(1), song, Messages())
    assert [d.name for d in chosen] == ["EQ"]


def test_step_device_stops_at_the_end():
    song, chosen = device_song(2)
    surface = Messages()
    live_actions.apply(StepDevice(1), song, surface)
    assert chosen == [] and surface.shown == ["No more devices"]



# Binding


class Param:
    def __init__(self, name, parent=None):
        self.name, self.canonical_parent = name, parent


def bind_song(selected_parameter):
    return SimpleNamespace(
        view=SimpleNamespace(selected_parameter=selected_parameter),
        tracks=BIND_TRACKS,
        return_tracks=[BIND_RETURN],
        master_track=BIND_MASTER,
    )


def bind_track(name, devices=(), sends=1):
    track = SimpleNamespace(name=name, devices=[])
    mixer = SimpleNamespace(canonical_parent=track)
    mixer.volume = Param("Track Volume", mixer)
    mixer.panning = Param("Track Panning", mixer)
    mixer.sends = [Param(f"Send {i}", mixer) for i in range(sends)]
    mixer.crossfader = Param("Crossfader", mixer)
    track.mixer_device = mixer
    for device_name in devices:
        device = SimpleNamespace(name=device_name, canonical_parent=track)
        device.parameters = [Param("Device On", device), Param("Frequency", device)]
        track.devices.append(device)
    return track


BIND_TRACKS = [bind_track("Bass", ["EQ", "EQ"]), bind_track("Bass", ["Comp"])]
BIND_RETURN = bind_track("A Reverb")
BIND_MASTER = bind_track("Main", sends=0)


def bind(parameter, row=2):
    return apply(BindFader(row), bind_song(parameter))


def test_bind_a_top_level_device_parameter():
    parameter = BIND_TRACKS[0].devices[1].parameters[1]
    assert bind(parameter) == FaderBound(
        2, FaderBinding("Bass", 0, "EQ", 1, 1, "Frequency"), "Fader 3: EQ Frequency"
    )


def test_bind_on_the_second_same_named_track():
    parameter = BIND_TRACKS[1].devices[0].parameters[1]
    assert bind(parameter).binding == FaderBinding("Bass", 1, "Comp", 0, 1, "Frequency")


@pytest.mark.parametrize(
    "track, attribute, index",
    [(BIND_RETURN, "volume", 0), (BIND_TRACKS[0], "panning", 1), (BIND_MASTER, "volume", 0)],
)
def test_bind_mixer_volume_and_pan(track, attribute, index):
    parameter = getattr(track.mixer_device, attribute)
    event = bind(parameter)
    assert event.binding.device is None and event.binding.param == index
    assert event.message == f"Fader 3: {track.name} {parameter.name}"


def test_bind_a_send():
    event = bind(BIND_RETURN.mixer_device.sends[0])
    assert event.binding == FaderBinding("A Reverb", 0, None, 0, 2, "Send 0")


def test_bind_refuses_other_mixer_parameters():
    event = bind(BIND_MASTER.mixer_device.crossfader)
    assert event == FaderBound(2, None, "Can't bind this parameter")


def test_bind_refuses_a_nested_device():
    chain = SimpleNamespace(canonical_parent=BIND_TRACKS[0].devices[0])
    nested = SimpleNamespace(name="Inner", canonical_parent=chain)
    event = bind(Param("Frequency", nested))
    assert event == FaderBound(2, None, "Map it to a macro instead")


def test_bind_with_nothing_selected():
    assert bind(None) == FaderBound(2, None, "Click a parameter in Live first")


def test_save_fader_bindings():
    stored = {}
    song = SimpleNamespace(set_data=lambda key, text: stored.update({key: text}))
    apply(SaveFaderBindings("{}"), song)
    assert stored == {"BleakLoop.faders": "{}"}


# FX snapshots


def test_save_fx_scenes():
    stored = {}
    song = SimpleNamespace(set_data=lambda key, text: stored.update({key: text}))
    apply(SaveFxScenes("{}"), song)
    assert stored == {"BleakLoop.fx.scenes": "{}"}


@pytest.fixture
def no_racks(monkeypatch):
    monkeypatch.setattr(live_actions.live_state, "read_racks", lambda song: ())


@pytest.mark.parametrize(
    "action, event",
    [
        (StoreFxSnapshot(3), RacksRead(3, (), False)),
        (StoreFxSnapshot(3, scene=True), RacksRead(3, (), False, scene=True)),
        (RecallFxSnapshot(3, 2), RacksRead(3, (), True, 2)),
        (
            RecallFxSnapshot(3, None, scene=True, end_beats=8.0),
            RacksRead(3, (), True, None, scene=True, end_beats=8.0),
        ),
    ],
)
def test_fx_snapshot_reads_pass_scene_and_end_through(no_racks, action, event):
    assert apply(action, SimpleNamespace()) == event


# Sequencer Mode actions


class FakeClip:
    def __init__(self, loop_start=0.0, loop_end=4.0, end_marker=4.0, notes=()):
        self.loop_start, self.loop_end, self.end_marker = loop_start, loop_end, end_marker
        self.notes = list(notes)
        self.calls = []

    def __setattr__(self, name, value):
        if name in ("loop_start", "loop_end") and hasattr(self, "calls"):
            self.calls.append((name, value))
        super().__setattr__(name, value)

    def remove_notes_by_id(self, ids):
        self.calls.append(("remove", ids))

    def add_new_notes(self, specs):
        self.calls.append(("add", specs))

    def remove_notes_extended(self, *args):
        self.calls.append(("remove_pitch", args))

    def duplicate_loop(self):
        self.calls.append(("duplicate",))

    def get_notes_by_id(self, ids):
        return [note for note in self.notes if note.note_id in ids]

    def apply_note_modifications(self, notes):
        self.calls.append(("modify", [(n.note_id, n.start_time, n.velocity) for n in notes]))


class SeqSlot(FakeSlot):
    def __init__(self, clip=None):
        super().__init__(clip is not None)
        self.clip = clip

    def create_clip(self, length):
        self.clip = FakeClip(loop_end=length, end_marker=length)
        self.has_clip = True


def seq_song(clip=None, armable=(True, True, False)):
    tracks = [fake_track() for _ in armable]
    for track, can in zip(tracks, armable):
        track.can_be_armed = can
    tracks[1].clip_slots = [SeqSlot(), SeqSlot(clip)]
    song = fake_song(tracks, visible=tracks[:1])
    song.view = SimpleNamespace(highlighted_clip_slot=None, selected_track=None)
    return song


@pytest.fixture
def note_specs(monkeypatch):
    clip_module = SimpleNamespace(MidiNoteSpecification=lambda **k: k)
    monkeypatch.setattr(sys.modules["Live"], "Clip", clip_module, raising=False)


def test_highlight_slot_uses_song_tracks():
    song = seq_song()
    apply(HighlightSlot(1, 1), song)
    assert song.view.highlighted_clip_slot is song.tracks[1].clip_slots[1]


def test_highlight_slot_skips_a_missing_track():
    song = seq_song()
    apply(HighlightSlot(5, 0), song)
    assert song.view.highlighted_clip_slot is None


def test_set_arms_skips_tracks_that_cant_be_armed():
    song = seq_song()
    apply(SetArms(((0, True), (2, True), (9, True))), song)
    assert song.tracks[0].arm and not song.tracks[2].arm


def test_select_set_track():
    song = seq_song()
    apply(SelectSetTrack(1), song)
    assert song.view.selected_track is song.tracks[1]


def test_edit_notes_is_one_undo_step(note_specs):
    clip = FakeClip()
    song = seq_song(clip)
    apply(EditNotes(1, 1, remove=(3, 4), add=((48, 0.5, 0.25, 90),)), song)
    assert song.undo == ["begin", "end"]
    assert clip.calls == [
        ("remove", [3, 4]),
        ("add", ({"pitch": 48, "start_time": 0.5, "duration": 0.25, "velocity": 90},)),
    ]


def test_edit_notes_creates_the_clip(note_specs):
    song = seq_song()
    apply(EditNotes(1, 0, add=((48, 0.0, 0.25, 90),), create_length=6.0), song)
    slot = song.tracks[1].clip_slots[0]
    assert slot.has_clip and slot.clip.loop_end == 6.0
    assert slot.clip.calls[-1][0] == "add"
    assert song.undo == ["begin", "end"]


def test_edit_notes_skips_an_empty_slot_without_a_length():
    song = seq_song()
    apply(EditNotes(1, 0, add=((48, 0.0, 0.25, 90),)), song)
    assert song.undo == []


def test_remove_pitch_covers_the_clip():
    clip = FakeClip(loop_end=8.0, end_marker=12.0)
    song = seq_song(clip)
    apply(RemovePitch(1, 1, 50), song)
    assert clip.calls == [("remove_pitch", (50, 1, 0.0, 12.0))]
    assert song.undo == ["begin", "end"]


def test_set_loop_moves_the_start_first_when_shrinking():
    clip = FakeClip(loop_start=0.0, loop_end=16.0)
    apply(SetLoop(1, 1, 4.0, 8.0), seq_song(clip))
    assert clip.calls == [("loop_start", 4.0), ("loop_end", 8.0)]


def test_set_loop_moves_the_end_first_past_it():
    clip = FakeClip(loop_start=0.0, loop_end=4.0)
    apply(SetLoop(1, 1, 16.0, 32.0), seq_song(clip))
    assert clip.calls == [("loop_end", 32.0), ("loop_start", 16.0)]


def test_duplicate_loop():
    clip = FakeClip()
    apply(DuplicateLoop(1, 1), seq_song(clip))
    assert clip.calls == [("duplicate",)]


def test_modify_notes():
    notes = [SimpleNamespace(note_id=i, start_time=0.0, velocity=100) for i in (1, 2)]
    clip = FakeClip(notes=notes)
    apply(ModifyNotes(1, 1, ((2, 0.125, 64),)), seq_song(clip))
    assert clip.calls == [("modify", [(2, 0.125, 64)])]


@pytest.mark.parametrize(
    "action",
    [RemovePitch(1, 0, 48), SetLoop(1, 0, 0.0, 4.0), DuplicateLoop(1, 0), ModifyNotes(1, 0, ())],
)
def test_clip_actions_skip_an_empty_slot(action):
    song = seq_song()
    apply(action, song)
    assert song.undo == []


def drum_song():
    song = seq_song()
    pads = [SimpleNamespace(note=n) for n in range(128)]
    rack = SimpleNamespace(
        can_have_drum_pads=True,
        drum_pads=pads,
        view=SimpleNamespace(drum_pads_scroll_position=9, selected_drum_pad=pads[36]),
    )
    instrument_rack = SimpleNamespace(
        can_have_drum_pads=False,
        can_have_chains=True,
        chains=[SimpleNamespace(devices=[rack])],
    )
    song.tracks[1].devices = [instrument_rack]
    song.tracks[0].devices = []
    return song, rack


def test_set_drum_scroll():
    song, rack = drum_song()
    apply(SetDrumScroll(1, 12), song)
    assert rack.view.drum_pads_scroll_position == 12


def test_select_drum_pad():
    song, rack = drum_song()
    apply(SelectDrumPad(1, 40), song)
    assert rack.view.selected_drum_pad is rack.drum_pads[40]


@pytest.mark.parametrize("action", [SetDrumScroll(0, 3), SelectDrumPad(0, 40), SetDrumScroll(9, 3)])
def test_drum_actions_skip_without_a_rack(action):
    song, rack = drum_song()
    apply(action, song)
    assert rack.view.drum_pads_scroll_position == 9
    assert rack.view.selected_drum_pad is rack.drum_pads[36]
