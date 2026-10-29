from dataclasses import dataclass, replace

from BleakLoop.core import arm
from BleakLoop.core.model import SetArms, ShowMessage
from BleakLoop.core.modes import State


@dataclass(frozen=True)
class Snap:
    arms: tuple


@dataclass(frozen=True)
class View:
    track: int | None
    is_midi: bool = True


ARMS = (False, True, False, None, False)
# Taken on track 2 with track 1 armed before: BleakLoop disarmed 1 and armed 2.
TAKEN = State(saved_arms=ARMS, set_arms=(False, False, True, None, False), arm_track=2)
NOW = (False, False, True, None, False)


def test_take_arms_the_track_alone():
    state, actions = arm.take(State(), Snap(ARMS), 2)
    assert state == TAKEN
    assert actions == [SetArms(((1, False), (2, True)))]


def test_take_on_the_only_armed_track_changes_nothing():
    state, actions = arm.take(State(), Snap((False, True)), 1)
    assert state.arm_track == 1 and state.saved_arms == (False, True)
    assert actions == []


def test_restore_puts_back_what_bleakloop_set():
    assert arm.restore(TAKEN, NOW) == [SetArms(((1, True), (2, False)))]


def test_restore_leaves_a_track_the_user_changed():
    # Track 2 disarmed by hand: it no longer equals what BleakLoop set.
    assert arm.restore(TAKEN, (False, False, False, None, False)) == [SetArms(((1, True),))]


def test_restore_after_the_track_count_changed_does_nothing():
    assert arm.restore(TAKEN, NOW + (False,)) == []


def test_restore_with_nothing_saved_does_nothing():
    assert arm.restore(State(), NOW) == []


def test_follow_moves_the_arm_to_a_midi_track():
    state, actions, moved = arm.follow(TAKEN, Snap(NOW), View(4), "needs MIDI")
    assert moved
    assert actions == [SetArms(((2, False), (4, True)))]
    assert state.arm_track == 4 and state.set_arms == (False, False, False, None, True)


def test_follow_on_a_non_midi_track_says_so_once():
    state, actions, moved = arm.follow(TAKEN, Snap(NOW), View(0, False), "needs MIDI")
    assert not moved and actions == [ShowMessage("needs MIDI")]
    assert state.arm_track == 2 and state.arm_refused == 0
    assert arm.follow(state, Snap(NOW), View(0, False), "needs MIDI") == (state, [], False)


def test_follow_on_the_same_track_does_nothing():
    refused = replace(TAKEN, arm_refused=0)
    state, actions, moved = arm.follow(refused, Snap(NOW), View(2), "needs MIDI")
    assert state == TAKEN and actions == [] and not moved


def test_release_clears_the_fields():
    assert arm.release(TAKEN) == State()
