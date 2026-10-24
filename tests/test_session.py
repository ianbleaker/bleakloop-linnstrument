from dataclasses import replace

import pytest

from BleakLoop.core import layout, session
from BleakLoop.core.layout import Window
from BleakLoop.core.leds import (
    BLUE,
    CYAN,
    GREEN,
    LIME,
    MAGENTA,
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
    CaptureAndInsertScene,
    ClearBackToArrangement,
    ClipTarget,
    ClipView,
    ControlCC,
    CopyClip,
    CopyScene,
    DeleteClip,
    DeleteScene,
    EnterMode,
    FireScene,
    FireSlot,
    PadPress,
    QuantizeClip,
    Redo,
    SceneSelected,
    SelectTrack,
    SetArrangementRecord,
    SetLaunchQuantization,
    SetSessionRecord,
    SetTempo,
    ShowClip,
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
from BleakLoop.core.modes import ClipSource, Mode, SceneSource, State, TrackControl


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


def test_shift_record_pad_does_nothing():
    assert handle(SHIFT, layout.RECORD) == (SHIFT, [])


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
    "pad, bars, text",
    [(1, 1, "Fixed Length 1 bar"), (2, 2, "Fixed Length 2 bars"), (3, 4, "Fixed Length 4 bars"),
     (4, 8, "Fixed Length 8 bars")],
)
def test_fixed_length_selects(pad, bars, text):
    state, actions = handle(SESSION, (15, pad))
    assert state.fixed_length == bars
    assert actions == [ShowMessage(text)]


def test_fixed_length_switches():
    state, actions = handle(State(fixed_length=2), (15, 4))
    assert state.fixed_length == 8
    assert actions == [ShowMessage("Fixed Length 8 bars")]


def test_fixed_length_clears():
    state, actions = handle(State(fixed_length=4), (15, 3))
    assert state.fixed_length is None
    assert actions == [ShowMessage("Fixed Length OFF")]


def test_shift_fixed_length_pads_move_window():
    state, _ = handle(replace(SHIFT, window=Window(3, 3)), (15, 2), session_snapshot(scene_count=20))
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


def test_midi_recording_enters_note_mode():
    state, actions = handle(SESSION, (2, 1), ARMED_MIDI)
    assert actions == [FireSlot(0, 0, legato=False), ShowClip(0, 0), EnterMode(Mode.NOTE)]
    assert state.mode is Mode.NOTE


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


def test_fixed_length_survives_auto_note_mode():
    state, _ = handle(State(fixed_length=4), (2, 1), ARMED_MIDI)
    assert state.mode is Mode.NOTE
    assert state.fixed_length == 4


# Capture follow-up


@pytest.mark.parametrize(
    "scene, window",
    [(2, Window(1, 2)), (14, Window(1, 8)), (6, Window(1, 4))],
)
def test_scene_selected_scrolls_window(scene, window):
    state = State(window=Window(1, 4))
    snapshot = session_snapshot(scene_count=20, window=Window(1, 4))
    assert session.handle(state, SceneSelected(scene), snapshot) == (State(window=window), [])


# Copy and Delete pads


@pytest.mark.parametrize("state", [SESSION, SHIFT])
def test_copy_press(state):
    new, actions = handle(state, layout.COPY)
    assert new == replace(state, copy=True)
    assert actions == [ShowMessage("Copy: pick a clip or scene")]


@pytest.mark.parametrize("state", [SESSION, SHIFT])
def test_delete_press(state):
    new, actions = handle(state, layout.DELETE)
    assert new == replace(state, delete=True)
    assert actions == [ShowMessage("Delete Mode ON")]


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
    [(c, 8) for c in layout.GRID_COLUMNS]
    + [(15, p) for p in range(1, 9)]
    + [(1, p) for p in [1, 3, 5, 6, 7, 8]]
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
        slots = tuple(SlotView(has_clip=row in clips) for row in range(7))
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
        (ClipSource(0, 0, True), (6, 2)),  # MIDI to a group track
    ],
)
def test_copy_mismatch_drops_source(source, key):
    state = replace(COPY, copy_source=source)
    assert handle(state, key, COPY_SNAP) == (
        COPY,
        [ShowMessage("Cannot copy between MIDI and audio tracks")],
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


# Copy: scenes


SCENES = replace(COPY_SNAP, scene_clips=(True, False, True))


def test_copy_scene_with_clips_becomes_source():
    state, actions = handle(COPY, (16, 1), SCENES)
    assert state.copy_source == SceneSource(0)
    assert actions == [ShowMessage("Copy: pick an empty scene")]


def test_copy_scene_source_with_window_offset():
    state, _ = handle(State(copy=True, window=Window(0, 2)), (16, 3), SCENES)
    assert state.copy_source == SceneSource(4)


def test_copy_empty_scene_without_source_hints():
    assert handle(COPY, (16, 2), SCENES) == (COPY, [ShowMessage("Scene is empty")])


def test_copy_scene_with_clip_source_keeps_source():
    state = replace(COPY, copy_source=ClipSource(0, 0, True))
    assert handle(state, (16, 2), SCENES) == (state, [ShowMessage("Pick a clip target")])


@pytest.mark.parametrize("pad", [3, 1])  # another scene, and the source itself
def test_copy_to_scene_with_clips_drops_source(pad):
    state = replace(COPY, copy_source=SceneSource(0))
    assert handle(state, (16, pad), SCENES) == (COPY, [ShowMessage("Target scene not empty")])


def test_copy_scene():
    state = replace(COPY, copy_source=SceneSource(0))
    assert handle(state, (16, 2), SCENES) == (
        COPY,
        [CopyScene(0, 1), ShowMessage("Scene copied")],
    )


def test_copy_scene_with_short_scene_clips_counts_as_empty():
    state = replace(COPY, copy_source=SceneSource(0))
    assert handle(state, (16, 5), SCENES) == (
        COPY,
        [CopyScene(0, 4), ShowMessage("Scene copied")],
    )
    assert handle(COPY, (16, 5), SCENES) == (COPY, [ShowMessage("Scene is empty")])


def test_copy_scene_past_the_end_does_nothing():
    snapshot = replace(SCENES, scene_count=3)
    assert handle(COPY, (16, 4), snapshot) == (COPY, [])


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


def test_shift_delete_clip_deletes():
    state = State(delete=True, shift=True)
    assert handle(state, (2, 1), COPY_SNAP) == (state, [DeleteClip(0, 0)])


def test_delete_scene():
    assert handle(DELETE, (16, 3)) == (DELETE, [DeleteScene(2)])


def test_delete_last_scene_refused():
    snapshot = session_snapshot(scene_count=1)
    assert handle(DELETE, (16, 1), snapshot) == (
        DELETE,
        [ShowMessage("Cannot delete last scene")],
    )


def test_delete_scene_past_the_end_does_nothing():
    assert handle(DELETE, (16, 5), session_snapshot(scene_count=4)) == (DELETE, [])


def test_delete_scene_with_window_at_bottom_moves_up():
    state = State(delete=True, window=Window(2, 3))
    snapshot = session_snapshot(scene_count=10, window=Window(2, 3))
    assert handle(state, (16, 7), snapshot) == (
        replace(state, window=Window(2, 2)),
        [DeleteScene(9)],
    )


def test_delete_scene_with_room_keeps_window():
    state = State(delete=True, window=Window(2, 1))
    snapshot = session_snapshot(scene_count=10, window=Window(2, 1))
    assert handle(state, (16, 1), snapshot) == (state, [DeleteScene(1)])


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
    assert frame[layout.COPY] == Light(MAGENTA)
    assert frame[layout.CAPTURE] == Light(LIME)
    assert frame[layout.DELETE] == Light(RED)
    assert frame[layout.RECORD] == Light(RED)


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
    assert all(frame[(15, p)] == Light(CYAN) for p in range(1, 5))
    assert frame[(15, 5)] == Light(WHITE)  # S-59
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
    assert frame[layout.COPY] == Light(MAGENTA)
    assert frame[layout.QUANTIZE] == Light(MAGENTA)
    assert frame[layout.DELETE] == Light(RED)
    assert all(frame[(1, p)] == Light(OFF) for p in [6, 7, 8])


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


def test_fixed_length_selected_blinks():
    frame = session.render(State(fixed_length=4), SNAP)
    assert [frame[(15, p)] for p in range(1, 5)] == [
        Light(CYAN), Light(CYAN), Light(CYAN, Blink.FAST), Light(CYAN),
    ]


def test_shift_layer_hides_fixed_length():
    frame = session.render(replace(SHIFT, fixed_length=4), SNAP)
    assert all(frame[(15, p)] == Light(YELLOW) for p in range(1, 5))


@pytest.mark.parametrize("held", [{"copy": True}, {"delete": True}])
def test_copy_or_delete_with_shift_draws_normal_layer(held):
    state = State(shift=True, track_control=TrackControl.MUTE, **held)
    frame = session.render(state, with_track(SNAP, 3, mute=True))
    assert frame[(2, 8)] == Light(ORANGE)
    assert frame[(3, 8)] == Light(LIME)
    assert all(frame[(15, p)] == Light(CYAN) for p in range(1, 5))
    assert frame[layout.CAPTURE] == Light(LIME)
    assert frame[layout.RECORD] == Light(RED)
    assert frame[layout.SHIFT] == Light(WHITE, Blink.FAST)


def test_clip_source_blinks_over_playing_clip():
    window = Window(0, 2)
    snapshot = slot_snapshot(SlotView(has_clip=True, is_playing=True))
    state = State(copy=True, window=window, copy_source=ClipSource(0, 2, True))
    frame = session.render(state, snapshot)
    assert frame[(2, 1)] == Light(RED, Blink.FAST)


def test_scene_source_blinks_over_lime():
    snapshot = slot_snapshot(SlotView(has_clip=True, is_playing=True))
    assert session.render(SESSION, snapshot)[(16, 1)] == Light(LIME, Blink.TEMPO)
    state = State(copy=True, copy_source=SceneSource(0))
    assert session.render(state, snapshot)[(16, 1)] == Light(RED, Blink.FAST)


@pytest.mark.parametrize(
    "source", [ClipSource(0, 9, True), ClipSource(13, 0, True), ClipSource(3, 0, True),
               SceneSource(9), SceneSource(0)],
)
def test_source_outside_window_not_drawn(source):
    window = Window(4, 2)
    snapshot = session_snapshot(window=window)
    state = State(copy=True, window=window)
    assert session.render(replace(state, copy_source=source), snapshot) == session.render(
        state, snapshot
    )
