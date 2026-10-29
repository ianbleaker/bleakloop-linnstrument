"""The arm a mode takes on entry and gives back on leaving, shared by Sequencer and Chord Mode.

Track indexes are song.tracks indexes. snapshot.arms holds each track's arm, None where the
track can't be armed.
"""

from dataclasses import replace

from .model import SetArms, ShowMessage


def take(state, snapshot, track):
    # Arm the target alone, remembering every track's arm and what BleakLoop set.
    arms = snapshot.arms
    wanted = tuple(None if arm is None else i == track for i, arm in enumerate(arms))
    changes = tuple(
        (i, want)
        for i, (arm, want) in enumerate(zip(arms, wanted))
        if arm is not None and arm != want
    )
    state = replace(state, saved_arms=arms, set_arms=wanted, arm_track=track, arm_refused=None)
    return state, [SetArms(changes)] if changes else []


def restore(state, arms):
    # On leaving, and on unload while the arms are saved (Linnstrument Mode keeps them). A
    # track's arm goes back only if it's still what BleakLoop set; with the track count
    # changed, the indexes don't line up and nothing is restored.
    saved, wanted = state.saved_arms, state.set_arms
    if saved is None or wanted is None or not len(saved) == len(arms) == len(wanted):
        return []
    changes = tuple(
        (i, before)
        for i, (before, set_, now) in enumerate(zip(saved, wanted, arms))
        if now is not None and before is not None and now == set_ and now != before
    )
    return [SetArms(changes)] if changes else []


def follow(state, snapshot, view, message):
    # On every display tick: the arm follows Live's selected track to any MIDI track. view
    # is the mode's selected-track view (track, is_midi); message is shown once per non-MIDI
    # track the selection moves to. moved is True when the arm moved to a new track.
    if view.track is not None and view.track == state.arm_track:
        return replace(state, arm_refused=None), [], False
    if view.track is None or not view.is_midi:
        refused = -1 if view.track is None else view.track
        if state.arm_refused == refused:
            return state, [], False
        return replace(state, arm_refused=refused), [ShowMessage(message)], False
    old, new, arms = state.arm_track, view.track, snapshot.arms
    changes = []
    if old is not None and old < len(arms) and arms[old]:
        changes.append((old, False))
    if new < len(arms) and arms[new] is False:
        changes.append((new, True))
    wanted = state.set_arms
    if wanted is not None:
        wanted = list(wanted)
        for i, arm in ((old, False), (new, True)):
            if i is not None and i < len(wanted) and wanted[i] is not None:
                wanted[i] = arm
        wanted = tuple(wanted)
    state = replace(state, arm_track=new, set_arms=wanted, arm_refused=None)
    return state, [SetArms(tuple(changes))] if changes else [], True


def release(state):
    return replace(state, saved_arms=None, set_arms=None, arm_track=None, arm_refused=None)
