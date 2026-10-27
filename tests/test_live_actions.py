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
    FaderBound,
    SaveFaderBindings,
    SetArm,
    SetFaderParameter,
    StepDevice,
    StepTrack,
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
