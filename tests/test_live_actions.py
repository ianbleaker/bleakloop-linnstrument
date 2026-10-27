import sys
from types import ModuleType, SimpleNamespace

import pytest

# Live exists only inside Live: the handlers tested here don't touch it.
sys.modules.setdefault("Live", ModuleType("Live"))

from BleakLoop import live_actions  # noqa: E402
from BleakLoop.core.model import (  # noqa: E402
    CopyGroupClips,
    SetArm,
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
    return SimpleNamespace(
        tracks=list(tracks),
        visible_tracks=list(tracks if visible is None else visible),
        return_tracks=list(returns),
        exclusive_solo=exclusive_solo,
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
    apply(CopyGroupClips(1, 0, 2), fake_song(tracks, visible=[outside, group, inner, direct, empty]))
    assert folded.clip_slots[0].copied_to is folded.clip_slots[2]
    assert direct.clip_slots[0].copied_to is None
    assert all(slot.copied_to is None for slot in empty.clip_slots + outside.clip_slots)
