from dataclasses import replace

import pytest

from BleakLoop.core import layout, session
from BleakLoop.core.layout import Window
from BleakLoop.core.leds import (
    BLUE,
    GREEN,
    LIME,
    OFF,
    ORANGE,
    RED,
    WHITE,
    YELLOW,
    Blink,
    Light,
)
from BleakLoop.core.model import (
    ArmExclusive,
    ControlCC,
    EnterMode,
    FireScene,
    FireSlot,
    PadPress,
    Redo,
    SelectTrack,
    SetLaunchQuantization,
    SetTempo,
    ShowMessage,
    SlotView,
    Snapshot,
    StopAllClips,
    StopTrackClips,
    ToggleMetronome,
    ToggleMute,
    TogglePlay,
    ToggleSolo,
    TrackView,
    Undo,
)
from BleakLoop.core.modes import Mode, State, TrackControl


def session_snapshot(track_count=20, scene_count=10, window=Window(), **k):
    visible = range(window.track, min(window.track + 13, track_count))
    rows = range(window.scene, min(window.scene + 7, scene_count))
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
SESSION = State()
SHIFT = State(shift=True)


def press(key, pressed=True):
    return PadPress(column=key[0], pad=key[1], pressed=pressed)


def handle(state, key, snapshot=SNAP, pressed=True):
    return session.handle(state, press(key, pressed), snapshot)


def with_track(snapshot, column, **k):
    tracks = list(snapshot.tracks)
    tracks[column - 2] = replace(tracks[column - 2], **k)
    return replace(snapshot, tracks=tuple(tracks))


# Common rules


@pytest.mark.parametrize("cc", range(1, 9))
def test_ignores_control_cc(cc):
    assert session.handle(SESSION, ControlCC(cc, 127), SNAP) == (SESSION, [])


@pytest.mark.parametrize("pad", range(1, 9))
@pytest.mark.parametrize("state", [SESSION, SHIFT])
def test_column_0_does_nothing(state, pad):
    assert handle(state, (0, pad)) == (state, [])


@pytest.mark.parametrize(
    "key", [layout.UNDO, layout.METRONOME, layout.PLAY_STOP, layout.MODE_PAD, (2, 1), (2, 8),
            (15, 1), (15, 6), (16, 1)]
)
def test_release_does_nothing(key):
    assert handle(SESSION, key, pressed=False) == (SESSION, [])


# Shift


def test_shift_press_and_release():
    state, actions = handle(SESSION, layout.SHIFT)
    assert state == SHIFT
    assert actions == []
    assert handle(state, layout.SHIFT, pressed=False) == (SESSION, [])


# Column 1


def test_undo():
    snapshot = replace(SNAP, can_undo=True)
    assert handle(SESSION, layout.UNDO, snapshot) == (SESSION, [Undo(), ShowMessage("Undo")])


def test_nothing_to_undo():
    assert handle(SESSION, layout.UNDO) == (SESSION, [ShowMessage("Nothing to undo")])


def test_shift_redo():
    snapshot = replace(SNAP, can_redo=True)
    assert handle(SHIFT, layout.UNDO, snapshot) == (SHIFT, [Redo(), ShowMessage("Redo")])


def test_shift_nothing_to_redo():
    assert handle(SHIFT, layout.UNDO) == (SHIFT, [ShowMessage("Nothing to redo")])


def test_metronome():
    assert handle(SESSION, layout.METRONOME) == (
        SESSION,
        [ToggleMetronome(), ShowMessage("Metronome ON")],
    )


def test_launch_quantization_off_remembers_value():
    state, actions = handle(SHIFT, layout.LAUNCH_QUANTIZATION, replace(SNAP, launch_quantization=7))
    assert state.quantization_memory == 7
    assert actions == [SetLaunchQuantization(0), ShowMessage("Launch Quantization: None")]


def test_launch_quantization_round_trip():
    state, actions = handle(SHIFT, layout.LAUNCH_QUANTIZATION, replace(SNAP, launch_quantization=4))
    assert state.quantization_memory == 4
    assert actions == [SetLaunchQuantization(0), ShowMessage("Launch Quantization: None")]
    state, actions = handle(state, layout.LAUNCH_QUANTIZATION, replace(SNAP, launch_quantization=0))
    assert actions == [SetLaunchQuantization(4), ShowMessage("Launch Quantization: 1 Bar")]


def test_launch_quantization_restores_memory():
    state = replace(SHIFT, quantization_memory=7)
    _, actions = handle(state, layout.LAUNCH_QUANTIZATION, replace(SNAP, launch_quantization=0))
    assert actions == [SetLaunchQuantization(7), ShowMessage("Launch Quantization: 1/4")]


def test_launch_quantization_on_without_memory_is_1_bar():
    _, actions = handle(SHIFT, layout.LAUNCH_QUANTIZATION, replace(SNAP, launch_quantization=0))
    assert actions == [SetLaunchQuantization(4), ShowMessage("Launch Quantization: 1 Bar")]


def test_play_stop():
    assert handle(SESSION, layout.PLAY_STOP) == (SESSION, [TogglePlay()])


def test_mode_pad_enters_note():
    state = State(shift=False, track_control=TrackControl.SOLO, window=Window(2, 1))
    new, actions = handle(state, layout.MODE_PAD)
    assert new == State(mode=Mode.NOTE, track_control=TrackControl.SOLO, window=Window(2, 1))
    assert actions == [EnterMode(Mode.NOTE)]


@pytest.mark.parametrize("key", [layout.PLAY_STOP, layout.MODE_PAD])
def test_shift_play_stop_and_mode_pad_do_nothing(key):
    assert handle(SHIFT, key) == (SHIFT, [])


@pytest.mark.parametrize("pad", [2, 3, 4, 7])
@pytest.mark.parametrize("state", [SESSION, SHIFT])
def test_column_1_unassigned_pads_do_nothing(state, pad):
    assert handle(state, (1, pad)) == (state, [])


# Clip slots


def test_slot_launch():
    assert handle(SESSION, (2, 1)) == (SESSION, [FireSlot(0, 0, legato=False)])
    assert handle(SESSION, (14, 7)) == (SESSION, [FireSlot(12, 6, legato=False)])


def test_shift_slot_launch_is_legato():
    assert handle(SHIFT, (3, 2)) == (SHIFT, [FireSlot(1, 1, legato=True)])


def test_slot_with_window_offset():
    window = Window(4, 2)
    state = State(window=window)
    snapshot = session_snapshot(window=window)
    assert handle(state, (2, 1), snapshot) == (state, [FireSlot(4, 2, legato=False)])


def test_slot_past_last_track():
    snapshot = session_snapshot(track_count=3)
    assert handle(SESSION, (5, 1), snapshot) == (SESSION, [])


def test_slot_past_last_scene():
    snapshot = session_snapshot(scene_count=3)
    assert handle(SESSION, (2, 4), snapshot) == (SESSION, [])


def test_slot_past_last_scene_with_offset():
    window = Window(0, 3)
    state = State(window=window)
    snapshot = session_snapshot(scene_count=8, window=window)
    assert handle(state, (2, 5), snapshot) == (state, [FireSlot(0, 7, legato=False)])
    assert handle(state, (2, 6), snapshot) == (state, [])


# Per-track switches


def mode(track_control, shift=False):
    return State(track_control=track_control, shift=shift)


def test_mute_toggles():
    state = mode(TrackControl.MUTE)
    assert handle(state, (3, 8)) == (state, [ToggleMute(1)])


def test_shift_mute_stops_track_clips():
    state = mode(TrackControl.MUTE, shift=True)
    assert handle(state, (3, 8)) == (state, [StopTrackClips(1), ShowMessage("Stop clips: T2")])


def test_solo_toggles():
    state = mode(TrackControl.SOLO)
    assert handle(state, (3, 8)) == (state, [ToggleSolo(1)])


def test_arm_selects_and_arms():
    assert handle(SESSION, (3, 8)) == (SESSION, [SelectTrack(1), ArmExclusive(1, True)])


def test_arm_on_armed_track_disarms():
    snapshot = with_track(SNAP, 3, arm=True)
    assert handle(SESSION, (3, 8), snapshot) == (
        SESSION,
        [SelectTrack(1), ArmExclusive(1, False)],
    )


def test_arm_on_unarmable_track_only_selects():
    snapshot = with_track(SNAP, 3, can_be_armed=False)
    assert handle(SESSION, (3, 8), snapshot) == (SESSION, [SelectTrack(1)])


def test_arm_uses_track_list_index():
    window = Window(5, 0)
    state = State(window=window)
    snapshot = session_snapshot(window=window)
    assert handle(state, (2, 8), snapshot) == (state, [SelectTrack(5), ArmExclusive(5, True)])


@pytest.mark.parametrize("track_control", [TrackControl.SOLO, TrackControl.ARM])
def test_shift_solo_and_arm_do_nothing(track_control):
    state = mode(track_control, shift=True)
    assert handle(state, (3, 8)) == (state, [])


@pytest.mark.parametrize("track_control", list(TrackControl))
@pytest.mark.parametrize("shift", [False, True])
def test_track_switch_without_track_does_nothing(track_control, shift):
    state = mode(track_control, shift)
    assert handle(state, (5, 8), session_snapshot(track_count=3)) == (state, [])


# Column 15


@pytest.mark.parametrize("pad", range(1, 6))
def test_column_15_pads_1_to_5_do_nothing(pad):
    assert handle(SESSION, (15, pad)) == (SESSION, [])


@pytest.mark.parametrize(
    "pad, window",
    [(1, Window(3, 2)), (2, Window(3, 4)), (3, Window(2, 3)), (4, Window(4, 3))],
)
def test_shift_moves_window(pad, window):
    state = replace(SHIFT, window=Window(3, 3))
    new, _ = handle(state, (15, pad), session_snapshot(scene_count=20))
    assert new.window == window


def test_window_message():
    state = replace(SHIFT, window=Window(0, 0))
    _, actions = handle(state, (15, 4))
    assert actions == [ShowMessage("Tracks 2–14, Scenes 1–7")]


def test_window_message_capped_at_counts():
    snapshot = session_snapshot(track_count=5, scene_count=9)
    _, actions = handle(SHIFT, (15, 2), snapshot)
    assert actions == [ShowMessage("Tracks 1–5, Scenes 2–8")]


def test_window_at_edge_does_nothing():
    assert handle(SHIFT, (15, 1)) == (SHIFT, [])
    assert handle(SHIFT, (15, 3)) == (SHIFT, [])


def test_shift_stop_all_clips():
    assert handle(SHIFT, layout.STOP_ALL) == (
        SHIFT,
        [StopAllClips(), ShowMessage("Stop all clips")],
    )


@pytest.mark.parametrize(
    "pad, track_control, text",
    [
        (6, TrackControl.MUTE, "Track Control: Mute"),
        (7, TrackControl.SOLO, "Track Control: Solo"),
        (8, TrackControl.ARM, "Track Control: Arm"),
    ],
)
def test_track_control_mode(pad, track_control, text):
    state, actions = handle(SESSION, (15, pad))
    assert state.track_control is track_control
    assert actions == [ShowMessage(text)]


def test_track_control_mode_already_selected_still_posts():
    assert handle(SESSION, (15, 8)) == (SESSION, [ShowMessage("Track Control: Arm")])


def test_shift_pad_6_does_nothing():
    assert handle(SHIFT, (15, 6)) == (SHIFT, [])


def test_shift_tempo_up_and_down():
    assert handle(SHIFT, (15, 7)) == (SHIFT, [SetTempo(121.0), ShowMessage("Tempo 121.0 BPM")])
    assert handle(SHIFT, (15, 8)) == (SHIFT, [SetTempo(119.0), ShowMessage("Tempo 119.0 BPM")])


def test_tempo_clamps_at_999():
    snapshot = replace(SNAP, tempo=998.5)
    assert handle(SHIFT, (15, 7), snapshot) == (
        SHIFT,
        [SetTempo(999), ShowMessage("Tempo 999.0 BPM")],
    )


def test_tempo_clamps_at_20():
    snapshot = replace(SNAP, tempo=20.5)
    assert handle(SHIFT, (15, 8), snapshot) == (
        SHIFT,
        [SetTempo(20), ShowMessage("Tempo 20.0 BPM")],
    )


# Column 16


def test_scene_launch():
    assert handle(SESSION, (16, 1)) == (SESSION, [FireScene(0, legato=False)])


def test_shift_scene_launch_is_legato():
    assert handle(SHIFT, (16, 3)) == (SHIFT, [FireScene(2, legato=True)])


def test_scene_launch_with_offset():
    state = State(window=Window(0, 3))
    assert handle(state, (16, 2)) == (state, [FireScene(4, legato=False)])


def test_scene_past_the_end_does_nothing():
    assert handle(SESSION, (16, 5), session_snapshot(scene_count=4)) == (SESSION, [])


# Rendering

CLIP = SlotView(has_clip=True)
RED_TRACK = 0xFF0000


def slot_snapshot(slot, **track):
    snapshot = with_track(SNAP, 2, colour=RED_TRACK, **track)
    slots = list(snapshot.tracks[0].slots)
    slots[0] = slot
    return with_track(snapshot, 2, slots=tuple(slots))


def test_frame_keys():
    for state in [SESSION, SHIFT]:
        frame = session.render(state, SNAP)
        assert set(frame) == {(c, p) for c in range(1, 17) for p in range(1, 9)}
        assert len(frame) == 128


@pytest.mark.parametrize(
    "slot, light",
    [
        (SlotView(has_clip=True, is_playing=True, is_triggered=True, is_recording=True),
         Light(RED)),
        (SlotView(has_clip=True, is_playing=True, is_triggered=True), Light(YELLOW)),
        (SlotView(has_clip=True, is_playing=True), Light(RED, Blink.TEMPO)),
        (CLIP, Light(RED)),
        (SlotView(), Light(OFF)),
    ],
)
def test_slot_priority(slot, light):
    assert session.render(SESSION, slot_snapshot(slot))[(2, 1)] == light


def test_slot_uses_track_colour():
    snapshot = with_track(slot_snapshot(CLIP), 2, colour=0x0000FF)
    assert session.render(SESSION, snapshot)[(2, 1)] == Light(BLUE)


@pytest.mark.parametrize("arm", [{"arm": True}, {"implicit_arm": True}])
def test_empty_slot_on_armed_track_is_white(arm):
    assert session.render(SESSION, slot_snapshot(SlotView(), **arm))[(2, 1)] == Light(WHITE)


def test_slot_without_track_is_off():
    frame = session.render(SESSION, session_snapshot(track_count=3))
    assert all(frame[(c, p)] == Light(OFF) for c in range(5, 15) for p in range(1, 9))


def test_slot_past_last_scene_is_off():
    snapshot = session_snapshot(scene_count=2)
    armed = with_track(snapshot, 2, arm=True)
    frame = session.render(SESSION, armed)
    assert frame[(2, 2)] == Light(WHITE)
    assert frame[(2, 3)] == Light(OFF)


def test_slots_are_the_same_on_the_shift_layer():
    snapshot = slot_snapshot(SlotView(has_clip=True, is_playing=True))
    assert session.render(SHIFT, snapshot)[(2, 1)] == Light(RED, Blink.TEMPO)


@pytest.mark.parametrize(
    "track_control, track, light",
    [
        (TrackControl.MUTE, {}, Light(ORANGE)),
        (TrackControl.MUTE, {"mute": True}, Light(LIME)),
        (TrackControl.SOLO, {}, Light(LIME)),
        (TrackControl.SOLO, {"solo": True}, Light(BLUE)),
        (TrackControl.ARM, {}, Light(LIME)),
        (TrackControl.ARM, {"arm": True}, Light(RED)),
        (TrackControl.ARM, {"implicit_arm": True}, Light(RED)),
    ],
)
def test_track_switch_light(track_control, track, light):
    snapshot = with_track(SNAP, 2, **track)
    assert session.render(mode(track_control), snapshot)[(2, 8)] == light


@pytest.mark.parametrize(
    "track_control, light",
    [(TrackControl.MUTE, Light(RED)), (TrackControl.SOLO, Light(OFF)),
     (TrackControl.ARM, Light(OFF))],
)
def test_track_switch_shift_light(track_control, light):
    assert session.render(mode(track_control, shift=True), SNAP)[(2, 8)] == light


@pytest.mark.parametrize("state", [SESSION, SHIFT])
def test_track_switch_without_track_is_off(state):
    assert session.render(state, session_snapshot(track_count=3))[(5, 8)] == Light(OFF)


def test_normal_layer_column_1():
    frame = session.render(SESSION, SNAP)
    assert frame[layout.UNDO] == Light(WHITE)
    assert frame[layout.METRONOME] == Light(ORANGE)
    assert frame[layout.PLAY_STOP] == Light(BLUE)
    assert frame[layout.MODE_PAD] == Light(WHITE)
    assert all(frame[(1, p)] == Light(OFF) for p in [2, 3, 4, 7])


def test_normal_layer_column_1_playing_with_metronome():
    frame = session.render(SESSION, replace(SNAP, is_playing=True, metronome=True))
    assert frame[layout.METRONOME] == Light(ORANGE, Blink.FAST)
    assert frame[layout.PLAY_STOP] == Light(GREEN, Blink.TEMPO)


@pytest.mark.parametrize(
    "track_control, blinking", [(TrackControl.MUTE, 6), (TrackControl.SOLO, 7),
                                (TrackControl.ARM, 8)]
)
def test_normal_layer_column_15(track_control, blinking):
    frame = session.render(mode(track_control), SNAP)
    assert all(frame[(15, p)] == Light(OFF) for p in range(1, 6))
    colours = {6: ORANGE, 7: BLUE, 8: RED}
    for pad, colour in colours.items():
        blink = Blink.TEMPO if pad == blinking else Blink.STEADY
        assert frame[(15, pad)] == Light(colour, blink)


def test_normal_layer_column_16():
    snapshot = with_track(SNAP, 2, slots=(CLIP,) + SNAP.tracks[0].slots[1:])
    frame = session.render(SESSION, snapshot)
    assert frame[(16, 1)] == Light(WHITE)
    assert frame[(16, 2)] == Light(OFF)
    assert frame[layout.SHIFT] == Light(WHITE)


def test_scene_lights_follow_window_offset():
    window = Window(0, 8)
    state = State(window=window)
    frame = session.render(state, session_snapshot(scene_count=10, window=window))
    assert frame[(16, 2)] == Light(OFF)
    assert frame[(16, 3)] == Light(OFF)


@pytest.mark.parametrize("quantization, light", [(4, Light(GREEN)), (0, Light(RED))])
def test_shift_layer_column_1(quantization, light):
    frame = session.render(SHIFT, replace(SNAP, launch_quantization=quantization))
    assert frame[layout.UNDO] == Light(WHITE)
    assert frame[layout.LAUNCH_QUANTIZATION] == light
    assert all(frame[(1, p)] == Light(OFF) for p in [2, 3, 4, 6, 7, 8])


def test_shift_layer_column_15():
    frame = session.render(SHIFT, SNAP)
    assert [frame[(15, p)] for p in range(1, 9)] == [
        Light(YELLOW), Light(YELLOW), Light(YELLOW), Light(YELLOW),
        Light(RED), Light(OFF), Light(GREEN), Light(GREEN),
    ]


def test_shift_layer_column_16():
    snapshot = with_track(SNAP, 2, slots=(CLIP,) + SNAP.tracks[0].slots[1:])
    frame = session.render(SHIFT, snapshot)
    assert frame[(16, 1)] == Light(WHITE)
    assert frame[layout.SHIFT] == Light(WHITE, Blink.FAST)
