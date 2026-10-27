from dataclasses import replace

import pytest

from BleakLoop.core import column_1, controls, engine, fx, layout, modes, session
from BleakLoop.core.layout import Window
from BleakLoop.core.leds import (
    BLUE,
    CYAN,
    GREEN,
    LIME,
    MAGENTA,
    OFF,
    ORANGE,
    PINK,
    RED,
    WHITE,
    YELLOW,
    Blink,
    Light,
)
from BleakLoop.core.model import (
    BindFader,
    ToggleDetailView,
    ArmExclusive,
    CaptureAndInsertScene,
    ClearBackToArrangement,
    ClipTarget,
    ClipView,
    CopyClip,
    CopyGroupClips,
    CopyScene,
    DeleteClip,
    DeleteGroupClips,
    DeleteScene,
    EndUndoStep,
    EnterMode,
    HighlightSlot,
    FireScene,
    FireSlot,
    PadPress,
    QuantizeClip,
    RecallFxSnapshot,
    Redo,
    SaveFxScenes,
    SceneSelected,
    SelectTrack,
    SeqEntry,
    SetArms,
    SetArm,
    SetArrangementRecord,
    SetLaunchQuantization,
    SetMixer,
    SetSessionRecord,
    SetTempo,
    ShowClip,
    ShowMessage,
    StepDevice,
    StepTrack,
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
    UnarmAll,
    UnmuteAll,
    UnsoloAll,
)
from BleakLoop.core.modes import ClipSource, FxRack, GroupSource, Mode, SceneSource, State


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


@pytest.mark.parametrize("pad", range(1, 9))
@pytest.mark.parametrize("state", [SESSION, SHIFT])
def test_column_0_does_nothing(state, pad):
    assert handle(state, (0, pad)) == (state, [])


@pytest.mark.parametrize(
    "key", [layout.UNDO, layout.METRONOME, layout.PLAY_STOP, layout.MODE_PAD, (2, 1), (2, 8),
            (layout.NAV_COLUMN, 1), (layout.NAV_COLUMN, 6), (layout.SCENE_COLUMN, 1)]
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


def test_mode_pad_enters_linnstrument():
    state = State(shift=False, window=Window(2, 1))
    new, actions = handle(state, layout.MODE_PAD)
    assert new == State(mode=Mode.LINNSTRUMENT, window=Window(2, 1))
    assert actions == [EnterMode(Mode.LINNSTRUMENT)]


@pytest.mark.parametrize("key", [layout.RECORD, layout.MODE_PAD])
def test_shift_record_and_mode_pad_do_nothing(key):
    assert handle(SHIFT, key) == (SHIFT, [])


def test_shift_record_pad_does_nothing():
    assert handle(SHIFT, layout.RECORD) == (SHIFT, [])


# Clip slots


def test_slot_launch():
    assert handle(SESSION, (2, 1)) == (SESSION, [FireSlot(0, 0, legato=False)])
    assert handle(SESSION, (14, 6)) == (SESSION, [FireSlot(12, 5, legato=False)])


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


# Mute and select rows


def test_mute_row_toggles_mute():
    assert handle(SESSION, (3, 7)) == (SESSION, [ToggleMute(1)])


def test_shift_mute_row_toggles_solo():
    assert handle(SHIFT, (3, 7)) == (SHIFT, [ToggleSolo(1)])


def test_select_row_selects_and_arms_exclusively():
    assert handle(SESSION, (3, 8)) == (SESSION, [SelectTrack(1), ArmExclusive(1, True)])


def test_select_row_on_selected_armed_track_disarms_it():
    snapshot = with_track(SNAP, 3, arm=True, selected=True)
    assert handle(SESSION, (3, 8), snapshot) == (SESSION, [SetArm(1, False)])


def test_select_row_on_armed_track_not_selected_selects_and_arms_exclusively():
    snapshot = with_track(SNAP, 3, arm=True)
    assert handle(SESSION, (3, 8), snapshot) == (
        SESSION,
        [SelectTrack(1), ArmExclusive(1, True)],
    )


@pytest.mark.parametrize("track", [{"selected": True}, {"implicit_arm": True, "selected": True}])
def test_select_row_on_selected_track_not_explicitly_armed_arms_it(track):
    snapshot = with_track(SNAP, 3, **track)
    assert handle(SESSION, (3, 8), snapshot) == (
        SESSION,
        [SelectTrack(1), ArmExclusive(1, True)],
    )


@pytest.mark.parametrize("selected", [False, True])
def test_select_row_on_unarmable_track_only_selects(selected):
    snapshot = with_track(SNAP, 3, can_be_armed=False, selected=selected)
    assert handle(SESSION, (3, 8), snapshot) == (SESSION, [SelectTrack(1)])


@pytest.mark.parametrize(
    "track, arm",
    [({}, True), ({"arm": True}, False), ({"selected": True}, True),
     ({"arm": True, "selected": True}, False), ({"implicit_arm": True}, True)],
)
def test_shift_select_row_toggles_arm_alone(track, arm):
    snapshot = with_track(SNAP, 3, **track)
    assert handle(SHIFT, (3, 8), snapshot) == (SHIFT, [SetArm(1, arm)])


@pytest.mark.parametrize("selected", [False, True])
def test_shift_select_row_on_unarmable_track_does_nothing(selected):
    snapshot = with_track(SNAP, 3, can_be_armed=False, selected=selected)
    assert handle(SHIFT, (3, 8), snapshot) == (SHIFT, [])


def test_rows_use_track_list_index():
    window = Window(5, 0)
    state = State(window=window)
    snapshot = session_snapshot(window=window)
    assert handle(state, (2, 7), snapshot) == (state, [ToggleMute(5)])
    assert handle(state, (2, 8), snapshot) == (state, [SelectTrack(5), ArmExclusive(5, True)])


@pytest.mark.parametrize("pad", [layout.MUTE_ROW, layout.SELECT_ROW])
@pytest.mark.parametrize("state", [SESSION, SHIFT])
def test_rows_without_track_do_nothing(state, pad):
    assert handle(state, (5, pad), session_snapshot(track_count=3)) == (state, [])


# Column 16


@pytest.mark.parametrize(
    "pad, window",
    [(1, Window(3, 2)), (2, Window(3, 4)), (3, Window(2, 3)), (4, Window(4, 3))],
)
def test_shift_moves_window(pad, window):
    state = replace(SHIFT, window=Window(3, 3))
    new, _ = handle(state, (layout.NAV_COLUMN, pad), session_snapshot(scene_count=20))
    assert new.window == window


def test_window_message():
    state = replace(SHIFT, window=Window(0, 0))
    _, actions = handle(state, (layout.NAV_COLUMN, 4))
    assert actions == [ShowMessage("Tracks 2–14, Scenes 1–6")]


def test_window_message_capped_at_counts():
    snapshot = session_snapshot(track_count=5, scene_count=9)
    _, actions = handle(SHIFT, (layout.NAV_COLUMN, 2), snapshot)
    assert actions == [ShowMessage("Tracks 1–5, Scenes 2–7")]


def test_window_at_edge_does_nothing():
    assert handle(SHIFT, (layout.NAV_COLUMN, 1)) == (SHIFT, [])
    assert handle(SHIFT, (layout.NAV_COLUMN, 3)) == (SHIFT, [])


def test_shift_stop_all_clips():
    assert handle(SHIFT, layout.PLAY_STOP) == (
        SHIFT,
        [StopAllClips(), ShowMessage("Stop all clips")],
    )


MIXING = State(mixer=True)
FX_ON = State(fx=True)


@pytest.mark.parametrize(
    "state, key, mixer, fx",
    [
        (SESSION, layout.MIXER, True, False),
        (SESSION, layout.FX, False, True),
        (MIXING, layout.SESSION, False, False),
        (MIXING, layout.FX, False, True),
        (MIXING, layout.MIXER, False, False),
        (FX_ON, layout.SESSION, False, False),
        (FX_ON, layout.MIXER, True, False),
        (FX_ON, layout.FX, False, False),
    ],
)
def test_mode_pads_switch(state, key, mixer, fx):
    new, _ = handle(state, key)
    assert (new.mixer, new.fx) == (mixer, fx)


# Split view


SPLIT = State(split=True)


def test_session_pad_toggles_the_split_view():
    state, actions = handle(SESSION, layout.SESSION)
    assert state.split and actions == [ShowMessage("Split view ON")]
    state, actions = handle(state, layout.SESSION)
    assert not state.split and actions == [ShowMessage("Split view OFF")]


@pytest.mark.parametrize("key", [layout.MIXER, layout.FX])
def test_session_from_mixer_or_fx_returns_to_the_split_view(key):
    state, _ = handle(SPLIT, key)
    state, _ = handle(state, layout.SESSION)
    assert state.split and not state.mixer and not state.fx


def test_the_split_window_is_8_tracks_wide():
    snapshot = session_snapshot(track_count=20)
    state, actions = handle(replace(SPLIT, shift=True, window=Window(11, 0)), layout.MIXER, snapshot)
    assert state.window == Window(12, 0)
    assert actions == [ShowMessage("Tracks 13–20, Scenes 1–6")]
    assert handle(state, layout.MIXER, snapshot)[0].window == Window(12, 0)


def test_turning_the_split_off_reclamps_the_window():
    snapshot = session_snapshot(track_count=20)
    state, _ = handle(replace(SPLIT, window=Window(12, 0)), layout.SESSION, snapshot)
    assert state.window == Window(7, 0)
    state, _ = handle(replace(SPLIT, window=Window(3, 0)), layout.SESSION, snapshot)
    assert state.window == Window(3, 0)


@pytest.mark.parametrize("key", [layout.MIXER, layout.FX])
def test_mixer_or_fx_from_the_split_view_reclamps_the_window(key):
    snapshot = session_snapshot(track_count=20)
    state, _ = handle(replace(SPLIT, window=Window(12, 0)), key, snapshot)
    assert state.window == Window(7, 0)
    state, _ = handle(state, key, snapshot)
    assert state.split and state.window == Window(7, 0)


def test_window_tracks():
    assert controls.window_tracks(SPLIT) == 8
    assert controls.window_tracks(SESSION) == 13
    assert controls.window_tracks(replace(SPLIT, mixer=True)) == 13
    assert controls.window_tracks(replace(SPLIT, fx=True)) == 13


def test_split_routes_column_9_to_the_clips_and_10_to_the_faders():
    assert handle(SPLIT, (9, 1)) == (SPLIT, [FireSlot(7, 0, legato=False)])
    assert handle(SPLIT, (9, layout.MUTE_ROW)) == (SPLIT, [ToggleMute(7)])
    # Pad 1 of column 10 is a fader row here: no parameter in SNAP, so nothing.
    assert handle(SPLIT, (10, 1)) == (SPLIT, [])
    assert handle(SPLIT, (10, layout.MUTE_ROW)) == (SPLIT, [])


def test_stop_and_a_split_fader_column_does_nothing():
    state = replace(SPLIT, stop=True)
    assert handle(state, (12, 3)) == (state, [])
    assert handle(state, (9, 3))[1] == [StopTrackClips(7), ShowMessage("Stop clips: T8")]


def test_split_render():
    frame = session.render(SPLIT, SNAP)
    assert frame[layout.SESSION] == Light(PINK)
    assert frame[(9, layout.MUTE_ROW)] == Light(PINK)
    assert all(frame[(column, pad)] == Light(OFF) for column in range(10, 15) for pad in (7, 8))


def test_mixer_mode_ignores_the_split():
    state = replace(SPLIT, mixer=True)
    frame = session.render(state, SNAP)
    assert frame[layout.MIXER] == Light(BLUE) and frame[layout.SESSION] == Light(CYAN)
    assert frame[(14, layout.MUTE_ROW)] == Light(PINK)


@pytest.mark.parametrize("key", [layout.SESSION, layout.FX, layout.MIXER])
def test_leaving_mixer_closes_its_undo_step(key):
    state = State(mixer=True, undo_open=True, touches=(), glides=())
    new, actions = handle(state, key)
    assert not new.mixer
    assert not new.undo_open
    assert actions[:2] == [EndUndoStep(), SetMixer(False)]


@pytest.mark.parametrize(
    "state, current", [(SESSION, layout.SESSION), (MIXING, layout.MIXER), (FX_ON, layout.FX)]
)
def test_mode_pad_lights(state, current):
    frame = session.render(state, SNAP)
    for key in (layout.SESSION, layout.MIXER, layout.FX):
        assert frame[key] == Light(BLUE if key == current else CYAN)
    assert all(frame[key] == Light(OFF) for key in layout.RESERVED)


def test_normal_layer_column_16():
    frame = session.render(SESSION, SNAP)
    assert [frame[(layout.NAV_COLUMN, p)] for p in range(1, 9)] == [
        Light(MAGENTA), Light(RED), Light(BLUE), Light(CYAN),
        Light(CYAN), Light(OFF), Light(CYAN), Light(ORANGE),
    ]


@pytest.mark.parametrize("state", [SHIFT, replace(MIXING, shift=True), replace(FX_ON, shift=True)])
def test_shift_column_16_keeps_window_moves_and_tempo(state):
    state = replace(state, window=Window(3, 3))
    snapshot = session_snapshot(scene_count=20)
    assert handle(state, layout.SESSION, snapshot)[0].window == Window(2, 3)
    assert handle(state, layout.MIXER, snapshot)[0].window == Window(4, 3)
    assert handle(state, layout.FX, snapshot) == (state, [])
    assert handle(state, (layout.NAV_COLUMN, 7), snapshot)[1][0] == SetTempo(121.0)


def test_shift_pad_6_does_nothing():
    assert handle(SHIFT, (layout.NAV_COLUMN, 6)) == (SHIFT, [])


def test_shift_tempo_up_and_down():
    assert handle(SHIFT, (layout.NAV_COLUMN, 7)) == (
        SHIFT,
        [SetTempo(121.0), ShowMessage("Tempo 121.0 BPM")],
    )
    assert handle(SHIFT, (layout.NAV_COLUMN, 8)) == (
        SHIFT,
        [SetTempo(119.0), ShowMessage("Tempo 119.0 BPM")],
    )


def test_tempo_clamps_at_999():
    snapshot = replace(SNAP, tempo=998.5)
    assert handle(SHIFT, (layout.NAV_COLUMN, 7), snapshot) == (
        SHIFT,
        [SetTempo(999), ShowMessage("Tempo 999.0 BPM")],
    )


def test_tempo_clamps_at_20():
    snapshot = replace(SNAP, tempo=20.5)
    assert handle(SHIFT, (layout.NAV_COLUMN, 8), snapshot) == (
        SHIFT,
        [SetTempo(20), ShowMessage("Tempo 20.0 BPM")],
    )


# Device/Clip


DEVICE_CLIP = State(device_clip=True)


@pytest.mark.parametrize("state", [SESSION, MIXING, FX_ON])
def test_device_clip_is_held(state):
    held, actions = handle(state, layout.DEVICE_CLIP)
    assert held.device_clip and actions == []
    assert handle(held, layout.DEVICE_CLIP, pressed=False) == (state, [ToggleDetailView()])


def engine_presses(state, *presses, snapshot=SNAP):
    # Through engine.handle, which marks a Device/Clip hold used; returns every action.
    actions = []
    for key, pressed in presses:
        state, more = engine.handle(state, press(key, pressed), snapshot)
        actions += more
    return state, actions


DOWN, UP = True, False


def test_device_clip_tap_flips_the_detail_view():
    state, actions = engine_presses(SESSION, (layout.DEVICE_CLIP, DOWN), (layout.DEVICE_CLIP, UP))
    assert actions == [ToggleDetailView()]
    assert not state.device_clip and not state.device_clip_used


@pytest.mark.parametrize("key", [(16, 2), layout.SHIFT, (3, 1), (1, 4)])
def test_device_clip_with_another_press_does_not_flip(key):
    state, actions = engine_presses(
        SESSION, (layout.DEVICE_CLIP, DOWN), (key, DOWN), (key, UP), (layout.DEVICE_CLIP, UP)
    )
    assert ToggleDetailView() not in actions
    assert not state.device_clip and not state.device_clip_used


def test_device_clip_and_a_mapped_fx_row_binds_without_flipping():
    mapped = replace(FX_ON, fader_source="mapped")
    _, actions = engine_presses(
        mapped, (layout.DEVICE_CLIP, DOWN), ((5, 3), DOWN), ((5, 3), UP), (layout.DEVICE_CLIP, UP)
    )
    assert actions == [BindFader(2)]


def test_device_clip_on_shifts_layer_never_flips():
    state, actions = engine_presses(SHIFT, (layout.DEVICE_CLIP, DOWN), (layout.DEVICE_CLIP, UP))
    assert actions == [SetTempo(119.0), ShowMessage("Tempo 119.0 BPM")]
    assert not state.device_clip


@pytest.mark.parametrize("mode", [Mode.SESSION, Mode.LINNSTRUMENT, Mode.SEQUENCER])
def test_mode_entry_clears_the_device_clip_hold(mode):
    state = modes.enter(State(device_clip=True, device_clip_used=True), mode)
    assert not state.device_clip and not state.device_clip_used


@pytest.mark.parametrize(
    "key, actions",
    [
        ((16, 1), [StepTrack(-1)]),
        ((16, 2), [StepTrack(1)]),
        ((16, 3), [StepDevice(-1)]),
        ((16, 4), [StepDevice(1)]),
        ((16, 6), []),
        ((16, 7), []),
    ],
)
@pytest.mark.parametrize("state", [DEVICE_CLIP, replace(DEVICE_CLIP, shift=True), replace(DEVICE_CLIP, fx=True)])
def test_device_clip_layer(state, key, actions):
    assert handle(state, key) == (state, actions)


def test_device_clip_toggles_the_fader_source():
    state, actions = handle(DEVICE_CLIP, layout.DEVICE_CLIP_SOURCE)
    assert state.fader_source == "mapped"
    assert actions == [ShowMessage("Mapped FX")]
    state, actions = handle(state, layout.DEVICE_CLIP_SOURCE)
    assert state.fader_source == "device"
    assert actions == [ShowMessage("Device FX")]


def test_device_clip_on_shifts_layer_steps_the_tempo():
    assert handle(SHIFT, layout.DEVICE_CLIP) == (
        SHIFT,
        [SetTempo(119.0), ShowMessage("Tempo 119.0 BPM")],
    )


def test_device_clip_pad_lights():
    assert session.render(SESSION, SNAP)[layout.DEVICE_CLIP] == Light(ORANGE)
    assert session.render(SHIFT, SNAP)[layout.DEVICE_CLIP] == Light(GREEN)


@pytest.mark.parametrize("state", [DEVICE_CLIP, replace(DEVICE_CLIP, shift=True)])
def test_device_clip_layer_lights(state):
    frame = session.render(state, SNAP)
    assert [frame[(layout.NAV_COLUMN, p)] for p in range(1, 9)] == [
        Light(LIME), Light(LIME), Light(MAGENTA), Light(MAGENTA),
        Light(ORANGE), Light(OFF), Light(OFF), Light(ORANGE, Blink.FAST),
    ]


def test_entering_a_mode_drops_device_clip():
    state = session.handle(DEVICE_CLIP, press(layout.MODE_PAD), SNAP)[0]
    assert state.mode is Mode.LINNSTRUMENT and not state.device_clip


# Column 15


def test_scene_launch():
    assert handle(SESSION, (layout.SCENE_COLUMN, 1)) == (SESSION, [FireScene(0, legato=False)])


def test_shift_scene_launch_is_legato():
    assert handle(SHIFT, (layout.SCENE_COLUMN, 3)) == (SHIFT, [FireScene(2, legato=True)])


def test_scene_launch_with_offset():
    state = State(window=Window(0, 3))
    assert handle(state, (layout.SCENE_COLUMN, 2)) == (state, [FireScene(4, legato=False)])


def test_scene_past_the_end_does_nothing():
    snapshot = session_snapshot(scene_count=4)
    assert handle(SESSION, (layout.SCENE_COLUMN, 5), snapshot) == (SESSION, [])


SCENE_SNAPSHOT = (FxRack("A", "R", 0, (1.0,)),)


def with_scene_snapshot(state, scene):
    return replace(state, fx_scenes=(None,) * scene + (SCENE_SNAPSHOT,))


@pytest.mark.parametrize(
    "state",
    [State(), State(mixer=True), State(fx=True), State(split=True)],
    ids=["session", "mixer", "fx", "split"],
)
def test_scene_launch_fires_the_scenes_snapshot(state):
    state = with_scene_snapshot(replace(state, window=Window(0, 1)), 2)
    snapshot = replace(session_snapshot(window=Window(0, 1)), is_playing=True, song_beats=5.5)
    assert handle(state, (layout.SCENE_COLUMN, 2), snapshot) == (
        state,
        [FireScene(2, legato=False), RecallFxSnapshot(2, None, scene=True, end_beats=8.0)],
    )


def test_legato_scene_launch_leaves_the_snapshot():
    state = with_scene_snapshot(SHIFT, 2)
    assert handle(state, (layout.SCENE_COLUMN, 3)) == (state, [FireScene(2, legato=True)])


def test_scene_launch_without_a_snapshot_fires_only_the_scene():
    state = with_scene_snapshot(SESSION, 1)
    assert handle(state, (layout.SCENE_COLUMN, 3)) == (state, [FireScene(2, legato=False)])


# Unmute all and Stop


def test_unmute_all():
    assert handle(SESSION, layout.UNMUTE_ALL) == (
        SESSION,
        [UnmuteAll(), ShowMessage("Unmute all")],
    )


def test_shift_unsolo_all():
    assert handle(SHIFT, layout.UNMUTE_ALL) == (SHIFT, [UnsoloAll(), ShowMessage("Unsolo all")])


@pytest.mark.parametrize("state", [State(mixer=True), State(fx=True)])
def test_unmute_all_in_mixer_and_fx(state):
    assert handle(state, layout.UNMUTE_ALL) == (state, [UnmuteAll(), ShowMessage("Unmute all")])


STOPPING = State(stop=True)
UNARM_ALL = [UnarmAll(), ShowMessage("Unarm all")]


def test_stop_press_holds():
    assert handle(SESSION, layout.STOP) == (STOPPING, [])


@pytest.mark.parametrize("state", [SESSION, State(mixer=True), State(fx=True)])
def test_stop_tap_does_nothing(state):
    held, actions = handle(state, layout.STOP)
    assert actions == []
    assert handle(held, layout.STOP, pressed=False) == (state, [])


@pytest.mark.parametrize("state", [SHIFT, State(mixer=True, shift=True), State(fx=True, shift=True)])
def test_shift_stop_unarms_all(state):
    assert handle(state, layout.STOP) == (state, UNARM_ALL)
    assert handle(state, layout.STOP, pressed=False) == (state, [])


@pytest.mark.parametrize("pad", range(1, 9))
def test_stop_held_with_track_pad_stops_the_track(pad):
    state, actions = handle(STOPPING, (3, pad))
    assert state == STOPPING
    assert actions == [StopTrackClips(1), ShowMessage("Stop clips: T2")]


def test_stop_held_with_shift_still_stops_the_track():
    state = State(stop=True, shift=True)
    _, actions = handle(state, (3, 1))
    assert actions == [StopTrackClips(1), ShowMessage("Stop clips: T2")]


def test_stop_held_stops_several_tracks_then_release_does_nothing():
    state, first = handle(STOPPING, (3, 1))
    state, second = handle(state, (4, 7))
    assert (first[0], second[0]) == (StopTrackClips(1), StopTrackClips(2))
    assert handle(state, layout.STOP, pressed=False) == (SESSION, [])


def test_stop_held_track_pad_release_does_nothing():
    assert handle(STOPPING, (3, 1), pressed=False) == (STOPPING, [])


def test_stop_held_with_empty_column_does_nothing():
    state = handle(STOPPING, (5, 1), session_snapshot(track_count=3))
    assert state == (STOPPING, [])


@pytest.mark.parametrize("pad", [1, 8])
def test_stop_held_in_mixer_stops_the_track(pad):
    state = State(mixer=True, stop=True)
    new, actions = handle(state, (3, pad))
    assert new == state
    assert actions == [StopTrackClips(1), ShowMessage("Stop clips: T2")]


def test_stop_held_in_fx_leaves_the_grid_to_fx():
    state = State(fx=True, stop=True)
    _, actions = handle(state, layout.FX_SLOTS[0])
    assert all(not isinstance(action, StopTrackClips) for action in actions)
    assert handle(state, layout.STOP, pressed=False) == (State(fx=True), [])


def test_stop_release_without_press_does_nothing():
    assert handle(SESSION, layout.STOP, pressed=False) == (SESSION, [])


def test_stop_hold_ends_on_mode_entry():
    state, _ = handle(STOPPING, layout.MODE_PAD)
    assert not state.stop


# Capture, record and quantize


def test_capture():
    assert handle(SESSION, layout.CAPTURE) == (
        SESSION,
        [CaptureAndInsertScene(), ShowMessage("Capture and Insert Scene")],
    )


def test_record_in_session_view():
    snapshot = replace(SNAP, session_record=True)
    assert handle(SESSION, layout.RECORD, snapshot) == (SESSION, [SetSessionRecord(False)])


def test_record_in_arrangement_view():
    snapshot = replace(SNAP, session_view=False, back_to_arranger=True)
    assert handle(SESSION, layout.RECORD, snapshot) == (
        SESSION,
        [ClearBackToArrangement(), SetArrangementRecord(True)],
    )


MIDI_CLIP = ClipView(is_midi=True)
AUDIO_CLIP = ClipView(is_midi=False)


@pytest.mark.parametrize(
    "clips, target",
    [
        ({"highlighted_clip": MIDI_CLIP, "detail_clip": AUDIO_CLIP, "playing_clip": AUDIO_CLIP},
         ClipTarget.HIGHLIGHTED),
        ({"detail_clip": MIDI_CLIP, "playing_clip": AUDIO_CLIP}, ClipTarget.DETAIL),
        ({"playing_clip": MIDI_CLIP}, ClipTarget.PLAYING),
    ],
)
def test_quantize_takes_first_candidate(clips, target):
    assert handle(SHIFT, layout.QUANTIZE, replace(SNAP, **clips)) == (
        SHIFT,
        [QuantizeClip(target), ShowMessage("Quantize 1/16")],
    )


def test_quantize_refuses_audio_first_candidate():
    snapshot = replace(SNAP, highlighted_clip=AUDIO_CLIP, detail_clip=MIDI_CLIP,
                       playing_clip=MIDI_CLIP)
    assert handle(SHIFT, layout.QUANTIZE, snapshot) == (
        SHIFT,
        [ShowMessage("Cannot quantize an audio clip")],
    )


def test_quantize_without_clip():
    assert handle(SHIFT, layout.QUANTIZE) == (SHIFT, [ShowMessage("No clip to quantize")])


# Fixed Length


@pytest.mark.parametrize(
    "bars, after, text",
    [(None, 1, "Fixed Length 1 bar"), (1, 2, "Fixed Length 2 bars"),
     (2, 4, "Fixed Length 4 bars"), (4, 8, "Fixed Length 8 bars"), (8, None, "Fixed Length OFF")],
)
def test_fixed_length_cycles(bars, after, text):
    state, actions = handle(State(fixed_length=bars), layout.FIXED_LENGTH)
    assert state.fixed_length == after
    assert actions == [ShowMessage(text)]


def test_shift_fixed_length_pads_move_window():
    state, _ = handle(
        replace(SHIFT, window=Window(3, 3)), (layout.NAV_COLUMN, 2), session_snapshot(scene_count=20)
    )
    assert state.window == Window(3, 4)
    assert state.fixed_length is None


# Recording presses


def recording_snapshot(slot=SlotView(), **track):
    snapshot = with_track(SNAP, 2, **track)
    slots = list(snapshot.tracks[0].slots)
    slots[0] = slot
    return with_track(snapshot, 2, slots=tuple(slots))


ARMED = {"arm": True}
ARMED_AUDIO = recording_snapshot(**ARMED)
ARMED_MIDI = recording_snapshot(has_midi_input=True, **ARMED)
PLAYING_CLIP = SlotView(has_clip=True, is_playing=True)


def test_empty_armed_slot_with_fixed_length():
    state, actions = handle(State(fixed_length=2), (2, 1), ARMED_AUDIO)
    assert actions[0] == FireSlot(0, 0, legato=False, record_length=8.0)


def test_empty_armed_slot_without_fixed_length():
    _, actions = handle(SESSION, (2, 1), ARMED_AUDIO)
    assert actions[0] == FireSlot(0, 0, legato=False, record_length=None)


def test_shift_empty_armed_slot_is_legato_with_record_length():
    _, actions = handle(replace(SHIFT, fixed_length=1), (2, 1), ARMED_AUDIO)
    assert actions[0] == FireSlot(0, 0, legato=True, record_length=4.0)


def test_implicit_arm_counts_as_armed():
    state = State(fixed_length=1)
    _, actions = handle(state, (2, 1), recording_snapshot(implicit_arm=True))
    assert actions == [FireSlot(0, 0, legato=False, record_length=4.0), ShowClip(0, 0)]


@pytest.mark.parametrize("slot", [SlotView(has_clip=True), PLAYING_CLIP,
                                  SlotView(has_clip=True, is_recording=True)])
def test_slot_with_clip_gets_no_record_length(slot):
    _, actions = handle(State(fixed_length=4), (2, 1), recording_snapshot(slot, **ARMED))
    assert actions[0] == FireSlot(0, 0, legato=False)


def test_midi_recording_enters_linnstrument_mode():
    state, actions = handle(SESSION, (2, 1), ARMED_MIDI)
    assert actions == [FireSlot(0, 0, legato=False), ShowClip(0, 0), EnterMode(Mode.LINNSTRUMENT)]
    assert state.mode is Mode.LINNSTRUMENT


def test_audio_recording_shows_clip_and_stays():
    assert handle(SESSION, (2, 1), ARMED_AUDIO) == (
        SESSION,
        [FireSlot(0, 0, legato=False), ShowClip(0, 0)],
    )


def test_recording_slot_counts_as_recording():
    # Unarmed: only the slot's own recording state counts.
    snapshot = recording_snapshot(SlotView(has_clip=True, is_recording=True))
    assert handle(SESSION, (2, 1), snapshot) == (
        SESSION,
        [FireSlot(0, 0, legato=False), ShowClip(0, 0)],
    )


def test_playing_clip_with_session_record_on_armed_track_records():
    snapshot = replace(recording_snapshot(PLAYING_CLIP, **ARMED), session_record=True)
    _, actions = handle(SESSION, (2, 1), snapshot)
    assert actions == [FireSlot(0, 0, legato=False), ShowClip(0, 0)]


def test_playing_clip_with_session_record_on_unarmed_track_does_not_record():
    snapshot = replace(recording_snapshot(PLAYING_CLIP), session_record=True)
    assert handle(SESSION, (2, 1), snapshot) == (SESSION, [FireSlot(0, 0, legato=False)])


def test_playing_clip_with_only_arrangement_overdub_does_not_record():
    snapshot = replace(recording_snapshot(PLAYING_CLIP, **ARMED), arrangement_overdub=True)
    assert handle(SESSION, (2, 1), snapshot) == (SESSION, [FireSlot(0, 0, legato=False)])


def test_playing_clip_without_session_record_does_not_record():
    snapshot = recording_snapshot(PLAYING_CLIP, **ARMED)
    assert handle(SESSION, (2, 1), snapshot) == (SESSION, [FireSlot(0, 0, legato=False)])


def test_empty_unarmed_slot_plain_fire():
    assert handle(State(fixed_length=2), (2, 1)) == (
        State(fixed_length=2),
        [FireSlot(0, 0, legato=False)],
    )


def test_back_after_auto_linnstrument_mode_returns_to_session():
    state, _ = handle(SESSION, (2, 1), ARMED_MIDI)
    state, actions = column_1.handle(state, press(layout.MODE_PAD), ARMED_MIDI)
    assert (state.mode, state.mixer, state.fx) == (Mode.SESSION, False, False)
    assert actions == [EnterMode(Mode.SESSION)]


def test_fixed_length_survives_auto_linnstrument_mode():
    state, _ = handle(State(fixed_length=4), (2, 1), ARMED_MIDI)
    assert state.mode is Mode.LINNSTRUMENT
    assert state.fixed_length == 4


# Capture follow-up


@pytest.mark.parametrize(
    "scene, window",
    [(2, Window(1, 2)), (14, Window(1, 9)), (9, Window(1, 4))],
)
def test_scene_selected_scrolls_window(scene, window):
    state = State(window=Window(1, 4))
    snapshot = session_snapshot(scene_count=20, window=Window(1, 4))
    assert session.handle(state, SceneSelected(scene), snapshot) == (State(window=window), [])


# Copy and Delete pads


def test_copy_press():
    new, actions = handle(SESSION, layout.COPY)
    assert new == State(copy=True)
    assert actions == [ShowMessage("Copy: pick a clip or scene")]


def test_delete_press():
    new, actions = handle(SESSION, layout.DELETE)
    assert new == State(delete=True)
    assert actions == [ShowMessage("Delete Mode ON")]


@pytest.mark.parametrize("key", [layout.COPY, layout.DELETE])
def test_copy_and_delete_pads_move_the_window_under_shift(key):
    state = replace(SHIFT, window=Window(3, 3))
    new, _ = handle(state, key, session_snapshot(scene_count=20))
    assert new == replace(state, window=Window(3, layout.WINDOW_MOVES[key][1] + 3))


@pytest.mark.parametrize("held", [{"copy": True}, {"delete": True}])
def test_copy_press_while_held_modifier_hides_shift(held):
    state = State(shift=True, **held)
    new, actions = handle(state, layout.COPY)
    assert new == replace(state, copy=True)
    assert actions == [ShowMessage("Copy: pick a clip or scene")]


@pytest.mark.parametrize("key", [layout.COPY, layout.DELETE])
def test_copy_and_delete_do_nothing_in_mixer(key):
    state = State(mixer=True)
    assert handle(state, key) == (state, [])


def test_copy_release_clears_source():
    state = State(copy=True, delete=True, copy_source=ClipSource(0, 0, True))
    assert handle(state, layout.COPY, pressed=False) == (State(delete=True), [])


def test_delete_release_leaves_copy():
    state = State(copy=True, delete=True, copy_source=SceneSource(1))
    assert handle(state, layout.DELETE, pressed=False) == (replace(state, delete=False), [])


def test_shift_toggles_while_copy_held():
    state, _ = handle(State(copy=True), layout.SHIFT)
    assert state == State(copy=True, shift=True)
    state, _ = handle(state, layout.SHIFT, pressed=False)
    assert state == State(copy=True)


COPY = State(copy=True)
DELETE = State(delete=True)

INERT_WHILE_HELD = (
    [(c, p) for c in layout.GRID_COLUMNS for p in (layout.MUTE_ROW, layout.SELECT_ROW)]
    + [(layout.NAV_COLUMN, p) for p in range(3, 8)]
    + [layout.UNMUTE_ALL, layout.STOP]
    + [(1, p) for p in range(1, 8)]
)


@pytest.mark.parametrize("key", INERT_WHILE_HELD)
@pytest.mark.parametrize("state", [COPY, DELETE, replace(COPY, shift=True),
                                   replace(DELETE, shift=True)])
def test_other_pads_inert_while_copy_or_delete_held(state, key):
    snapshot = replace(SNAP, can_undo=True, can_redo=True)
    assert handle(state, key, snapshot) == (state, [])


# Copy: clip slots


def slots_snapshot(*tracks, scene_count=10):
    # tracks: dicts of TrackView fields, with "clips" naming the window rows that have one.
    views = []
    for i, k in enumerate(tracks):
        clips = k.pop("clips", ())
        slots = tuple(SlotView(has_clip=row in clips) for row in range(layout.WINDOW_SCENES))
        views.append(TrackView(index=i, slots=slots, **k))
    return replace(SNAP, tracks=tuple(views), track_count=len(views), scene_count=scene_count)


MIDI = {"has_midi_input": True}
COPY_SNAP = slots_snapshot(
    dict(clips=(0,), **MIDI), dict(clips=(0,)), dict(MIDI), dict(), dict(is_foldable=True)
)


def test_copy_slot_with_clip_becomes_source():
    state, actions = handle(COPY, (2, 1), COPY_SNAP)
    assert state.copy_source == ClipSource(0, 0, True)
    assert actions == [ShowMessage("Copy: pick an empty slot")]


def test_copy_audio_source_records_kind():
    state, _ = handle(COPY, (3, 1), COPY_SNAP)
    assert state.copy_source == ClipSource(1, 0, False)


def test_copy_empty_slot_without_source_hints():
    assert handle(COPY, (2, 2), COPY_SNAP) == (COPY, [ShowMessage("Copy: pick a clip or scene")])


def test_copy_slot_with_scene_source_keeps_source():
    state = replace(COPY, copy_source=SceneSource(0))
    assert handle(state, (2, 2), COPY_SNAP) == (state, [ShowMessage("Pick a scene target")])


@pytest.mark.parametrize("key", [(3, 1), (2, 1)])  # another clip, and the source itself
def test_copy_to_slot_with_clip_drops_source(key):
    state = replace(COPY, copy_source=ClipSource(0, 0, True))
    assert handle(state, key, COPY_SNAP) == (COPY, [ShowMessage("Target not empty")])


@pytest.mark.parametrize(
    "source, key",
    [
        (ClipSource(0, 0, True), (5, 2)),  # MIDI to audio
        (ClipSource(1, 0, False), (4, 2)),  # audio to MIDI
    ],
)
def test_copy_mismatch_drops_source(source, key):
    state = replace(COPY, copy_source=source)
    assert handle(state, key, COPY_SNAP) == (
        COPY,
        [ShowMessage("Cannot copy between MIDI and audio tracks")],
    )


def test_copy_clip_to_group_track_drops_source():
    state = replace(COPY, copy_source=ClipSource(0, 0, True))
    assert handle(state, (6, 2), COPY_SNAP) == (
        COPY,
        [ShowMessage("Cannot copy into a group track")],
    )


def test_copy_midi_to_midi_on_another_track():
    state = replace(COPY, copy_source=ClipSource(0, 0, True))
    assert handle(state, (4, 3), COPY_SNAP) == (
        COPY,
        [CopyClip(0, 0, 2, 2), ShowMessage("Clip copied")],
    )


def test_copy_audio_to_audio_with_window_offset():
    window = Window(0, 3)
    state = State(copy=True, window=window, copy_source=ClipSource(1, 0, False))
    assert handle(state, (5, 2), COPY_SNAP) == (
        replace(state, copy_source=None),
        [CopyClip(1, 0, 3, 4), ShowMessage("Clip copied")],
    )


def test_copy_slot_outside_session_does_nothing():
    state = replace(COPY, copy_source=ClipSource(0, 0, True))
    assert handle(state, (8, 2), COPY_SNAP) == (state, [])
    short = replace(COPY_SNAP, scene_count=1)
    assert handle(state, (4, 2), short) == (state, [])


def test_copy_and_delete_held_follow_copy():
    state = State(copy=True, delete=True)
    new, actions = handle(state, (2, 1), COPY_SNAP)
    assert new.copy_source == ClipSource(0, 0, True)
    assert actions == [ShowMessage("Copy: pick an empty slot")]


def test_copy_and_shift_held_follow_copy():
    state = State(copy=True, shift=True)
    _, actions = handle(state, (2, 2), COPY_SNAP)
    assert actions == [ShowMessage("Copy: pick a clip or scene")]


# Copy: group track slots


def group_snapshot(*rows):
    # rows: member_clips per window row of the group track at index 4 (column 6).
    slots = tuple(
        SlotView(member_clips=rows[row] if row < len(rows) else ())
        for row in range(layout.WINDOW_SCENES)
    )
    return with_track(COPY_SNAP, 6, slots=slots)


def test_copy_group_slot_with_member_clips_becomes_source():
    state, actions = handle(COPY, (6, 2), group_snapshot((False, False), (True, False)))
    assert state.copy_source == GroupSource(4, 1)
    assert actions == [ShowMessage("Copy: pick an empty slot")]


@pytest.mark.parametrize("members", [(False, False), ()])
def test_copy_group_slot_without_member_clips_hints(members):
    snapshot = group_snapshot(members)
    assert handle(COPY, (6, 1), snapshot) == (COPY, [ShowMessage("Copy: pick a clip or scene")])


GROUP_COPY = replace(COPY, copy_source=GroupSource(4, 0))


def test_copy_group_to_another_track_drops_source():
    snapshot = group_snapshot((True, False))
    assert handle(GROUP_COPY, (4, 2), snapshot) == (
        COPY,
        [ShowMessage("Pick a slot in the same group")],
    )


@pytest.mark.parametrize("pad", [2, 1])  # a source member filled, and the source itself
def test_copy_group_to_filled_member_drops_source(pad):
    snapshot = group_snapshot((True, False), (True, True))
    assert handle(GROUP_COPY, (6, pad), snapshot) == (COPY, [ShowMessage("Target not empty")])


@pytest.mark.parametrize("target", [(False, False), (False, True)])
def test_copy_group_clips(target):
    # A member without a source clip may have a clip in the target row.
    snapshot = group_snapshot((True, False), target)
    assert handle(GROUP_COPY, (6, 2), snapshot) == (
        COPY,
        [CopyGroupClips(4, 0, 1), ShowMessage("Clips copied")],
    )


def test_copy_group_clips_with_window_offset():
    window = Window(0, 3)
    state = State(copy=True, window=window, copy_source=GroupSource(4, 4))
    snapshot = group_snapshot((), (True, False), (False, True))
    assert handle(state, (6, 3), snapshot) == (
        replace(state, copy_source=None),
        [CopyGroupClips(4, 4, 5), ShowMessage("Clips copied")],
    )


def test_copy_group_source_outside_window_drops_source():
    state = replace(COPY, copy_source=GroupSource(4, 9))
    assert handle(state, (6, 2), group_snapshot((True, False))) == (COPY, [])


# Copy: scenes


SCENES = replace(COPY_SNAP, scene_clips=(True, False, True))


def test_copy_scene_with_clips_becomes_source():
    state, actions = handle(COPY, (layout.SCENE_COLUMN, 1), SCENES)
    assert state.copy_source == SceneSource(0)
    assert actions == [ShowMessage("Copy: pick an empty scene")]


def test_copy_scene_source_with_window_offset():
    state, _ = handle(State(copy=True, window=Window(0, 2)), (layout.SCENE_COLUMN, 3), SCENES)
    assert state.copy_source == SceneSource(4)


def test_copy_empty_scene_without_source_hints():
    assert handle(COPY, (layout.SCENE_COLUMN, 2), SCENES) == (COPY, [ShowMessage("Scene is empty")])


@pytest.mark.parametrize("source", [ClipSource(0, 0, True), GroupSource(4, 0)])
def test_copy_scene_with_clip_source_keeps_source(source):
    state = replace(COPY, copy_source=source)
    assert handle(state, (layout.SCENE_COLUMN, 2), SCENES) == (
        state,
        [ShowMessage("Pick a clip target")],
    )


@pytest.mark.parametrize("pad", [3, 1])  # another scene, and the source itself
def test_copy_to_scene_with_clips_drops_source(pad):
    state = replace(COPY, copy_source=SceneSource(0))
    assert handle(state, (layout.SCENE_COLUMN, pad), SCENES) == (
        COPY,
        [ShowMessage("Target scene not empty")],
    )


def test_copy_scene():
    state = replace(COPY, copy_source=SceneSource(0))
    assert handle(state, (layout.SCENE_COLUMN, 2), SCENES) == (
        COPY,
        [CopyScene(0, 1), ShowMessage("Scene copied")],
    )


def test_copy_scene_copies_its_snapshot():
    state = replace(COPY, copy_source=SceneSource(0), fx_scenes=(SCENE_SNAPSHOT,))
    state, actions = handle(state, (layout.SCENE_COLUMN, 2), SCENES)
    scenes = (SCENE_SNAPSHOT, SCENE_SNAPSHOT) + (None,) * (SCENES.scene_count - 2)
    assert state.fx_scenes == scenes
    assert actions == [
        CopyScene(0, 1),
        SaveFxScenes(fx.dump_scenes(scenes)),
        ShowMessage("Scene copied"),
    ]


def test_copy_scene_without_a_snapshot_keeps_the_targets():
    state = replace(COPY, copy_source=SceneSource(0), fx_scenes=(None, SCENE_SNAPSHOT))
    state, actions = handle(state, (layout.SCENE_COLUMN, 2), SCENES)
    assert state.fx_scenes == (None, SCENE_SNAPSHOT)
    assert actions == [CopyScene(0, 1), ShowMessage("Scene copied")]


def test_copy_scene_with_short_scene_clips_counts_as_empty():
    state = replace(COPY, copy_source=SceneSource(0))
    assert handle(state, (layout.SCENE_COLUMN, 5), SCENES) == (
        COPY,
        [CopyScene(0, 4), ShowMessage("Scene copied")],
    )
    assert handle(COPY, (layout.SCENE_COLUMN, 5), SCENES) == (COPY, [ShowMessage("Scene is empty")])


def test_copy_scene_past_the_end_does_nothing():
    snapshot = replace(SCENES, scene_count=3)
    assert handle(COPY, (layout.SCENE_COLUMN, 4), snapshot) == (COPY, [])


# Delete


def test_delete_clip():
    assert handle(DELETE, (3, 1), COPY_SNAP) == (DELETE, [DeleteClip(1, 0)])


def test_delete_clip_with_window_offset():
    state = State(delete=True, window=Window(0, 2))
    assert handle(state, (2, 1), COPY_SNAP) == (state, [DeleteClip(0, 2)])


def test_delete_empty_slot_does_nothing():
    assert handle(DELETE, (2, 2), COPY_SNAP) == (DELETE, [])


def test_delete_slot_outside_session_does_nothing():
    assert handle(DELETE, (8, 1), COPY_SNAP) == (DELETE, [])
    assert handle(DELETE, (2, 1), replace(COPY_SNAP, scene_count=0)) == (DELETE, [])


def test_delete_group_slot_deletes_its_members_clips():
    snapshot = slot_snapshot(GROUP, is_foldable=True, can_be_armed=False)
    assert handle(DELETE, (2, 1), snapshot) == (DELETE, [DeleteGroupClips(0, 0)])


def test_delete_empty_group_slot_does_nothing():
    snapshot = slot_snapshot(SlotView(), is_foldable=True, can_be_armed=False)
    assert handle(DELETE, (2, 1), snapshot) == (DELETE, [])


def test_shift_delete_clip_deletes():
    state = State(delete=True, shift=True)
    assert handle(state, (2, 1), COPY_SNAP) == (state, [DeleteClip(0, 0)])


def test_delete_scene():
    assert handle(DELETE, (layout.SCENE_COLUMN, 3)) == (DELETE, [DeleteScene(2)])


def test_delete_last_scene_refused():
    snapshot = session_snapshot(scene_count=1)
    assert handle(DELETE, (layout.SCENE_COLUMN, 1), snapshot) == (
        DELETE,
        [ShowMessage("Cannot delete last scene")],
    )


def test_delete_scene_past_the_end_does_nothing():
    assert handle(DELETE, (layout.SCENE_COLUMN, 5), session_snapshot(scene_count=4)) == (DELETE, [])


def test_delete_scene_with_window_at_bottom_moves_up():
    state = State(delete=True, window=Window(2, 4))
    snapshot = session_snapshot(scene_count=10, window=Window(2, 4))
    assert handle(state, (layout.SCENE_COLUMN, 6), snapshot) == (
        replace(state, window=Window(2, 3)),
        [DeleteScene(9)],
    )


def test_delete_scene_with_room_keeps_window():
    state = State(delete=True, window=Window(2, 1))
    snapshot = session_snapshot(scene_count=10, window=Window(2, 1))
    assert handle(state, (layout.SCENE_COLUMN, 1), snapshot) == (state, [DeleteScene(1)])


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


GROUP = SlotView(controls_other_clips=True)


@pytest.mark.parametrize(
    "slot, light",
    [
        (SlotView(controls_other_clips=True, is_playing=True, is_recording=True), Light(RED)),
        (SlotView(controls_other_clips=True, is_playing=True, is_triggered=True),
         Light(YELLOW)),
        (SlotView(controls_other_clips=True, is_playing=True), Light(RED, Blink.TEMPO)),
        (GROUP, Light(RED)),
    ],
)
def test_group_slot_shows_its_members(slot, light):
    snapshot = slot_snapshot(slot, is_foldable=True, can_be_armed=False)
    assert session.render(SESSION, snapshot)[(2, 1)] == light


def test_group_slot_press_fires_it():
    snapshot = slot_snapshot(GROUP, is_foldable=True, can_be_armed=False)
    assert handle(SESSION, (2, 1), snapshot) == (SESSION, [FireSlot(0, 0, legato=False)])


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
    "track, light", [({}, Light(PINK)), ({"mute": True}, Light(ORANGE))]
)
def test_mute_row_light(track, light):
    assert session.render(SESSION, with_track(SNAP, 2, **track))[(2, 7)] == light


@pytest.mark.parametrize("track, light", [({}, Light(CYAN)), ({"solo": True}, Light(BLUE))])
def test_shift_mute_row_light_shows_solo(track, light):
    snapshot = with_track(SNAP, 2, mute=True, **track)
    assert session.render(SHIFT, snapshot)[(2, 7)] == light


@pytest.mark.parametrize(
    "track, light",
    [
        ({}, Light(LIME)),
        ({"selected": True}, Light(WHITE)),
        ({"arm": True}, Light(RED)),
        ({"implicit_arm": True}, Light(RED)),
        ({"arm": True, "selected": True}, Light(RED)),
        ({"can_be_armed": False}, Light(OFF)),
        ({"can_be_armed": False, "selected": True}, Light(WHITE)),
    ],
)
@pytest.mark.parametrize("state", [SESSION, SHIFT])
def test_select_row_light(state, track, light):
    assert session.render(state, with_track(SNAP, 2, **track))[(2, 8)] == light


@pytest.mark.parametrize("state", [SESSION, SHIFT])
def test_rows_without_track_are_off(state):
    frame = session.render(state, session_snapshot(track_count=3))
    assert frame[(5, 7)] == frame[(5, 8)] == Light(OFF)


@pytest.mark.parametrize("held", [{"copy": True}, {"delete": True}])
def test_rows_show_normal_layer_while_copy_or_delete_held_with_shift(held):
    frame = session.render(State(shift=True, **held), with_track(SNAP, 3, mute=True))
    assert frame[(2, 7)] == Light(PINK)
    assert frame[(3, 7)] == Light(ORANGE)


@pytest.mark.parametrize("muted, light", [(False, Light(OFF)), (True, Light(ORANGE))])
def test_unmute_all_light(muted, light):
    snapshot = replace(SNAP, any_muted=muted, any_soloed=True)
    assert session.render(SESSION, snapshot)[layout.UNMUTE_ALL] == light


@pytest.mark.parametrize("soloed, light", [(False, Light(OFF)), (True, Light(BLUE))])
def test_shift_unmute_all_light_shows_solo(soloed, light):
    snapshot = replace(SNAP, any_muted=True, any_soloed=soloed)
    assert session.render(SHIFT, snapshot)[layout.UNMUTE_ALL] == light


@pytest.mark.parametrize("state", [SESSION, State(mixer=True), State(fx=True)])
@pytest.mark.parametrize("armed", [False, True])
def test_stop_light(state, armed):
    snapshot = replace(SNAP, any_armed=armed)
    assert session.render(state, snapshot)[layout.STOP] == Light(RED)
    held = replace(state, stop=True)
    assert session.render(held, snapshot)[layout.STOP] == Light(RED, Blink.FAST)


@pytest.mark.parametrize("state", [SHIFT, State(mixer=True, shift=True), State(fx=True, shift=True)])
@pytest.mark.parametrize("armed, light", [(False, Light(OFF)), (True, Light(RED))])
def test_shift_stop_light_shows_an_arm(state, armed, light):
    assert session.render(state, replace(SNAP, any_armed=armed))[layout.STOP] == light


def test_stop_held_keeps_its_light_under_shift():
    state = State(stop=True, shift=True)
    assert session.render(state, SNAP)[layout.STOP] == Light(RED, Blink.FAST)


def test_normal_layer_column_1():
    frame = session.render(SESSION, SNAP)
    assert frame[layout.UNDO] == Light(WHITE)
    assert frame[layout.METRONOME] == Light(ORANGE)
    assert frame[layout.PLAY_STOP] == Light(BLUE)
    assert frame[layout.MODE_PAD] == Light(MAGENTA)
    assert frame[layout.COPY] == Light(MAGENTA)
    assert frame[layout.CAPTURE] == Light(LIME)
    assert frame[layout.DELETE] == Light(RED)
    assert frame[layout.RECORD] == Light(RED)


def test_normal_layer_column_1_playing_with_metronome():
    frame = session.render(SESSION, replace(SNAP, is_playing=True, metronome=True))
    assert frame[layout.METRONOME] == Light(ORANGE, Blink.FAST)
    assert frame[layout.PLAY_STOP] == Light(GREEN, Blink.TEMPO)


def test_normal_layer_column_15():
    snapshot = with_track(SNAP, 2, slots=(CLIP,) + SNAP.tracks[0].slots[1:])
    frame = session.render(SESSION, snapshot)
    assert frame[(layout.SCENE_COLUMN, 1)] == Light(WHITE)
    assert frame[(layout.SCENE_COLUMN, 2)] == Light(OFF)
    assert frame[layout.SHIFT] == Light(WHITE)


def test_scene_lights_follow_window_offset():
    window = Window(0, 8)
    state = State(window=window)
    frame = session.render(state, session_snapshot(scene_count=10, window=window))
    assert frame[(layout.SCENE_COLUMN, 2)] == Light(OFF)
    assert frame[(layout.SCENE_COLUMN, 3)] == Light(OFF)


@pytest.mark.parametrize("quantization, light", [(4, Light(GREEN)), (0, Light(RED))])
def test_shift_layer_column_1(quantization, light):
    frame = session.render(SHIFT, replace(SNAP, launch_quantization=quantization))
    assert frame[layout.PLAY_STOP] == Light(RED)
    assert frame[layout.UNDO] == Light(WHITE)
    assert frame[layout.LAUNCH_QUANTIZATION] == light
    assert frame[layout.QUANTIZE] == Light(MAGENTA)
    assert frame[layout.RECORD] == frame[layout.FIXED_LENGTH] == frame[layout.MODE_PAD] == Light(OFF)


def test_shift_layer_column_16():
    frame = session.render(SHIFT, SNAP)
    assert [frame[(layout.NAV_COLUMN, p)] for p in range(1, 9)] == [
        Light(YELLOW), Light(YELLOW), Light(YELLOW), Light(YELLOW),
        Light(OFF), Light(OFF), Light(GREEN), Light(GREEN),
    ]


def test_shift_layer_column_15():
    snapshot = with_track(SNAP, 2, slots=(CLIP,) + SNAP.tracks[0].slots[1:])
    frame = session.render(SHIFT, snapshot)
    assert frame[(layout.SCENE_COLUMN, 1)] == Light(WHITE)
    assert frame[layout.SHIFT] == Light(WHITE, Blink.FAST)


@pytest.mark.parametrize("shift", [False, True])
def test_copy_and_delete_lights_while_held(shift):
    frame = session.render(State(copy=True, delete=True, shift=shift), SNAP)
    assert frame[layout.COPY] == Light(RED, Blink.FAST)
    assert frame[layout.DELETE] == Light(RED, Blink.FAST)


def test_delete_light_while_shift_and_delete_held():
    frame = session.render(State(delete=True, shift=True), SNAP)
    assert frame[layout.COPY] == Light(MAGENTA)
    assert frame[layout.DELETE] == Light(RED, Blink.FAST)


def test_record_light_follows_session_record():
    frame = session.render(SESSION, replace(SNAP, session_record=True))
    assert frame[layout.RECORD] == Light(RED, Blink.TEMPO)


def test_record_light_in_arrangement_view():
    frame = session.render(SESSION, replace(SNAP, session_view=False, back_to_arranger=True))
    assert frame[layout.RECORD] == Light(ORANGE, Blink.TEMPO)


@pytest.mark.parametrize(
    "bars, colour", [(None, OFF), (1, CYAN), (2, BLUE), (4, MAGENTA), (8, PINK)]
)
def test_fixed_length_colour(bars, colour):
    assert session.render(State(fixed_length=bars), SNAP)[layout.FIXED_LENGTH] == Light(colour)


def test_shift_layer_hides_fixed_length():
    frame = session.render(replace(SHIFT, fixed_length=4), SNAP)
    assert all(frame[(layout.NAV_COLUMN, p)] == Light(YELLOW) for p in range(1, 5))


@pytest.mark.parametrize("held", [{"copy": True}, {"delete": True}])
def test_copy_or_delete_with_shift_draws_normal_layer(held):
    state = State(shift=True, **held)
    frame = session.render(state, with_track(SNAP, 3, mute=True))
    assert frame[layout.COPY] == (Light(RED, Blink.FAST) if held.get("copy") else Light(MAGENTA))
    assert frame[layout.MIXER] == Light(CYAN)
    assert frame[layout.CAPTURE] == Light(LIME)
    assert frame[layout.RECORD] == Light(RED)
    assert frame[layout.SHIFT] == Light(WHITE, Blink.FAST)


def test_clip_source_blinks_over_playing_clip():
    window = Window(0, 2)
    snapshot = slot_snapshot(SlotView(has_clip=True, is_playing=True))
    state = State(copy=True, window=window, copy_source=ClipSource(0, 2, True))
    frame = session.render(state, snapshot)
    assert frame[(2, 1)] == Light(RED, Blink.FAST)


def test_group_source_blinks():
    window = Window(0, 2)
    state = State(copy=True, window=window, copy_source=GroupSource(1, 3))
    frame = session.render(state, session_snapshot(window=window))
    assert frame[(3, 2)] == Light(RED, Blink.FAST)


def test_scene_source_blinks_over_lime():
    snapshot = slot_snapshot(SlotView(has_clip=True, is_playing=True))
    assert session.render(SESSION, snapshot)[(layout.SCENE_COLUMN, 1)] == Light(LIME, Blink.TEMPO)
    state = State(copy=True, copy_source=SceneSource(0))
    assert session.render(state, snapshot)[(layout.SCENE_COLUMN, 1)] == Light(RED, Blink.FAST)


@pytest.mark.parametrize(
    "source", [ClipSource(0, 9, True), ClipSource(13, 0, True), ClipSource(3, 0, True),
               GroupSource(4, 9), GroupSource(3, 2), SceneSource(9), SceneSource(0)],
)
def test_source_outside_window_not_drawn(source):
    window = Window(4, 2)
    snapshot = session_snapshot(window=window)
    state = State(copy=True, window=window)
    assert session.render(replace(state, copy_source=source), snapshot) == session.render(
        state, snapshot
    )


# Shift + 16/7 and 16/8 are the tempo steps.
@pytest.mark.parametrize(
    "state, key",
    [(state, key) for state in (SESSION, SHIFT) for key in layout.RESERVED
     if not (state.shift and key in layout.TEMPO_STEPS)],
)
def test_reserved_pads(state, key):
    assert handle(state, key) == (state, [])
    assert session.render(state, SNAP)[key] == Light(OFF)


def test_shift_midi_recording_enters_linnstrument_without_shift():
    # A legato press that starts a MIDI recording still switches, and Shift ends.
    snapshot = with_track(SNAP, 2, arm=True, has_midi_input=True)
    state, actions = handle(SHIFT, (2, 1), snapshot)
    assert state.mode is Mode.LINNSTRUMENT
    assert not state.shift
    assert actions == [FireSlot(0, 0, legato=True), ShowClip(0, 0), EnterMode(Mode.LINNSTRUMENT)]


# Seq: entering Sequencer Mode


def seq_snapshot(entry=None, arms=(False, True, None, False), **k):
    # Window tracks T1-T4 are song.tracks 0-3: T1 and T4 MIDI, T2 audio (armed), T3 a group.
    snapshot = replace(SNAP, arms=arms, seq_entry=entry, **k)
    snapshot = with_track(snapshot, 2, set_index=0, has_midi_input=True)
    snapshot = with_track(snapshot, 3, set_index=1)
    snapshot = with_track(snapshot, 4, set_index=2, has_midi_input=True, is_foldable=True)
    return with_track(snapshot, 5, set_index=3, has_midi_input=True)


SEQ_HELD = State(seq_held=True)
ENTERED = [SetArms(((0, True), (1, False))), EnterMode(Mode.SEQUENCER), ShowMessage("Sequencer")]


def tap(state, snapshot):
    held, actions = handle(state, layout.SEQ, snapshot)
    assert held.seq_held and not held.seq_used and actions == []
    return handle(held, layout.SEQ, snapshot, pressed=False)


def test_seq_tap_on_a_highlighted_clip():
    snapshot = seq_snapshot(SeqEntry(selected=0, selected_midi=True, has_clip=True))
    state, actions = tap(SESSION, snapshot)
    assert state.mode is Mode.SEQUENCER
    assert actions == ENTERED
    assert state.seq_track == 0
    assert state.seq_saved_arms == (False, True, None, False)
    assert state.seq_set_arms == (True, False, None, False)


def test_seq_tap_on_an_empty_slot_moves_to_the_detail_clip():
    entry = SeqEntry(selected=0, selected_midi=True, scene=2, detail=(3, 5), playing_scene=1)
    state, actions = tap(SESSION, seq_snapshot(entry))
    assert actions[0] == HighlightSlot(3, 5)
    assert state.seq_track == 3
    assert actions[1] == SetArms(((1, False), (3, True)))


def test_seq_tap_on_an_empty_slot_moves_to_the_playing_clip():
    entry = SeqEntry(selected=0, selected_midi=True, scene=2, playing_scene=1)
    state, actions = tap(SESSION, seq_snapshot(entry))
    assert actions == [HighlightSlot(0, 1)] + ENTERED


def test_seq_tap_on_an_empty_slot_with_no_other_clip_stays():
    entry = SeqEntry(selected=0, selected_midi=True, scene=2)
    state, actions = tap(SESSION, seq_snapshot(entry))
    assert state.mode is Mode.SEQUENCER
    assert actions == ENTERED


@pytest.mark.parametrize("entry", [None, SeqEntry(), SeqEntry(selected=1, has_clip=True)])
def test_seq_tap_needs_a_midi_track(entry):
    state, actions = tap(SESSION, seq_snapshot(entry))
    assert state == SESSION
    assert actions == [ShowMessage("Sequencer needs a MIDI track")]


@pytest.mark.parametrize("pad", [1, 4])
def test_seq_and_a_slot_enters_on_it(pad):
    # A clip or an empty slot alike; the clip doesn't launch.
    snapshot = seq_snapshot()
    snapshot = with_track(snapshot, 2, slots=tuple(SlotView(has_clip=p == 0) for p in range(6)))
    state, actions = handle(SEQ_HELD, (2, pad), snapshot)
    assert state.mode is Mode.SEQUENCER
    assert actions == [HighlightSlot(0, pad - 1)] + ENTERED


def test_seq_and_a_slot_uses_the_window():
    state = replace(SEQ_HELD, window=Window(0, 3))
    _, actions = handle(state, (5, 2), seq_snapshot())
    assert actions[0] == HighlightSlot(3, 4)


@pytest.mark.parametrize("column", [3, 4])
def test_seq_and_an_audio_or_group_slot_refuses(column):
    state, actions = handle(SEQ_HELD, (column, 1), seq_snapshot())
    assert state == replace(SEQ_HELD, seq_used=True)
    assert actions == [ShowMessage("Sequencer needs a MIDI track")]


def test_the_release_after_seq_and_a_slot_does_nothing():
    snapshot = seq_snapshot(SeqEntry(selected=0, selected_midi=True, has_clip=True))
    state, _ = handle(SEQ_HELD, (3, 1), snapshot)
    assert handle(state, layout.SEQ, snapshot, pressed=False) == (SESSION, [])


@pytest.mark.parametrize("key", [(2, 7), (2, 8), layout.UNMUTE_ALL, layout.MIXER, layout.PLAY_STOP])
def test_seq_and_any_other_pad_does_nothing(key):
    assert handle(SEQ_HELD, key, seq_snapshot()) == (replace(SEQ_HELD, seq_used=True), [])


def test_shift_and_seq_is_the_tempo_step():
    snapshot = seq_snapshot(SeqEntry(selected=0, selected_midi=True, has_clip=True))
    state, actions = handle(SHIFT, layout.SEQ, snapshot)
    assert state == SHIFT
    assert actions[0] == SetTempo(121.0)
    assert handle(state, layout.SEQ, snapshot, pressed=False) == (SHIFT, [])


@pytest.mark.parametrize("state", [MIXING, FX_ON])
def test_seq_tap_from_mixer_and_fx(state):
    snapshot = seq_snapshot(SeqEntry(selected=0, selected_midi=True, has_clip=True))
    entered, actions = tap(state, snapshot)
    assert entered.mode is Mode.SEQUENCER
    assert not entered.mixer and not entered.fx
    assert actions == ENTERED


@pytest.mark.parametrize("state", [MIXING, FX_ON])
def test_mixer_and_fx_grid_ignore_presses_while_seq_is_held(state):
    held = replace(state, seq_held=True)
    assert handle(held, (2, 1), seq_snapshot()) == (replace(held, seq_used=True), [])


def test_seq_entry_closes_a_mixer_gesture():
    state = replace(MIXING, seq_held=True, undo_open=True)
    snapshot = seq_snapshot(SeqEntry(selected=0, selected_midi=True, has_clip=True))
    entered, actions = handle(state, layout.SEQ, snapshot, pressed=False)
    assert not entered.undo_open
    assert actions[0] == EndUndoStep()


def test_seq_entry_sets_only_changed_arms():
    snapshot = seq_snapshot(
        SeqEntry(selected=0, selected_midi=True, has_clip=True), arms=(True, False, None)
    )
    _, actions = tap(SESSION, snapshot)
    assert actions == [EnterMode(Mode.SEQUENCER), ShowMessage("Sequencer")]


def test_seq_blinks_while_held():
    assert session.render(SESSION, SNAP)[layout.SEQ] == Light(CYAN)
    assert session.render(SEQ_HELD, SNAP)[layout.SEQ] == Light(CYAN, Blink.FAST)
