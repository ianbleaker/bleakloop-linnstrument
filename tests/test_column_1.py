from dataclasses import replace

import pytest

from BleakLoop.core import column_1, controls, layout, modes
from BleakLoop.core.layout import Window
from BleakLoop.core.leds import (
    BLUE,
    CYAN,
    GREEN,
    LIME,
    MAGENTA,
    OFF,
    PINK,
    RED,
    WHITE,
    Blink,
    Light,
)
from BleakLoop.core.model import (
    AddScene,
    CaptureAndInsertScene,
    CaptureMidi,
    ClipTarget,
    ClipView,
    EnterMode,
    FireScene,
    FireSlot,
    PadPress,
    QuantizeClip,
    RecallFxSnapshot,
    SelectedTrack,
    SetLaunchQuantization,
    SetMixer,
    ShowClip,
    ShowMessage,
    SlotView,
    Snapshot,
    StopAllClips,
    StopTrackClips,
    TogglePlay,
    TrackView,
)
from BleakLoop.core.modes import FxRack, Mode, State

BASE = Snapshot(
    is_playing=False,
    song_beats=0.0,
    tempo=120.0,
    metronome=False,
    session_view=True,
    track_count=4,
    scene_count=4,
)
ARRANGEMENT = replace(BASE, session_view=False)

SESSION = State()
LINNSTRUMENT = State(mode=Mode.LINNSTRUMENT)
MODES = [SESSION, LINNSTRUMENT]
SCENES = replace(LINNSTRUMENT, scene_page=True)

F, T = False, True
ARMED = SelectedTrack(index=2, name="Keys", armed=True, clips=(F, F, F, F))


def shifted(state):
    return replace(state, shift=True)


def press(key, pressed=True):
    return PadPress(*key, pressed)


def handle(state, key, snapshot=BASE, pressed=True):
    return column_1.handle(state, press(key, pressed), snapshot)


def with_track(snapshot=BASE, **k):
    return replace(snapshot, selected_track=replace(ARMED, **k))


# Shift


@pytest.mark.parametrize("state", MODES)
def test_shift_press_and_release(state):
    assert handle(state, layout.SHIFT) == (shifted(state), [])
    assert handle(shifted(state), layout.SHIFT, pressed=False) == (state, [])


@pytest.mark.parametrize("state", MODES + [shifted(SESSION), shifted(LINNSTRUMENT)])
@pytest.mark.parametrize("pad", range(1, 8))
def test_releases_do_nothing(state, pad):
    assert handle(state, (1, pad), with_track(), pressed=False) == (state, [])


# Pad 1: Play/Stop


@pytest.mark.parametrize("state", MODES)
@pytest.mark.parametrize("snapshot", [BASE, ARRANGEMENT, with_track()])
def test_play_stop_is_transport(state, snapshot):
    assert handle(state, layout.PLAY_STOP, snapshot) == (state, [TogglePlay()])


def test_shift_play_stop_stops_all_in_session():
    state = shifted(SESSION)
    assert handle(state, layout.PLAY_STOP, with_track()) == (
        state,
        [StopAllClips(), ShowMessage("Stop all clips")],
    )


def test_shift_play_stop_stops_selected_track_in_linnstrument():
    state = shifted(LINNSTRUMENT)
    assert handle(state, layout.PLAY_STOP, with_track()) == (
        state,
        [StopTrackClips(2), ShowMessage("Stop clips: Keys")],
    )


def test_shift_play_stop_without_selected_track_in_linnstrument():
    state = shifted(LINNSTRUMENT)
    assert handle(state, layout.PLAY_STOP) == (state, [ShowMessage("No selected track")])


# Pad 2: Record


@pytest.mark.parametrize("snapshot", [BASE, ARRANGEMENT])
def test_record_in_session(snapshot):
    assert handle(SESSION, layout.RECORD, snapshot) == (SESSION, controls.record(snapshot))


@pytest.mark.parametrize("snapshot", [BASE, ARRANGEMENT])
def test_shift_record_in_linnstrument(snapshot):
    state = shifted(LINNSTRUMENT)
    assert handle(state, layout.RECORD, snapshot) == (state, controls.record(snapshot))


def record_clip(snapshot, state=LINNSTRUMENT):
    return handle(state, layout.RECORD, snapshot)


def test_record_clip_without_selected_track():
    assert record_clip(BASE) == (LINNSTRUMENT, [ShowMessage("No selected track")])


def test_record_clip_on_group_track():
    snap = with_track(is_foldable=True, armed=True)
    assert record_clip(snap) == (LINNSTRUMENT, [ShowMessage("Cannot record on a group track")])


def test_record_clip_on_unarmed_track():
    assert record_clip(with_track(armed=False)) == (LINNSTRUMENT, [ShowMessage("Track not armed")])


@pytest.mark.parametrize(
    "selected, clips, scene",
    [
        (2, (F, F, F, F), 2),  # the highlighted scene is the first candidate
        (2, (F, F, T, T), 0),  # wraps to the top
        (1, (T, T, F), 2),
    ],
)
def test_record_clip_search(selected, clips, scene):
    snap = replace(with_track(clips=clips), selected_scene=selected, scene_count=len(clips))
    assert record_clip(snap) == (
        LINNSTRUMENT,
        [
            FireSlot(2, scene, legato=False, record_length=None),
            ShowClip(2, scene),
            ShowMessage("Record Clip"),
        ],
    )


def test_record_clip_adds_scene_when_full():
    snap = replace(with_track(clips=(T, T, T)), scene_count=3)
    assert record_clip(snap) == (
        LINNSTRUMENT,
        [
            AddScene(),
            FireSlot(2, 3, legato=False, record_length=None),
            ShowClip(2, 3),
            ShowMessage("Record Clip: new scene"),
        ],
    )


@pytest.mark.parametrize("numerator, beats", [(4, 8.0), (3, 6.0)])
def test_record_clip_uses_fixed_length(numerator, beats):
    snap = replace(with_track(), signature_numerator=numerator)
    _, actions = record_clip(snap, replace(LINNSTRUMENT, fixed_length=2))
    assert actions[0] == FireSlot(2, 0, legato=False, record_length=beats)


# Pad 3: Capture


def test_capture_in_session():
    assert handle(SESSION, layout.CAPTURE) == (
        SESSION,
        [CaptureAndInsertScene(), ShowMessage("Capture and Insert Scene")],
    )


def test_capture_midi_with_nothing_to_capture():
    assert handle(LINNSTRUMENT, layout.CAPTURE) == (
        LINNSTRUMENT,
        [ShowMessage("Nothing to capture")],
    )


def test_capture_midi():
    snap = replace(BASE, can_capture_midi=True)
    assert handle(LINNSTRUMENT, layout.CAPTURE, snap) == (
        LINNSTRUMENT,
        [CaptureMidi(), ShowMessage("Capture MIDI")],
    )


@pytest.mark.parametrize("state", MODES)
def test_shift_capture_quantizes(state):
    snap = replace(BASE, detail_clip=ClipView(is_midi=True))
    assert handle(shifted(state), layout.QUANTIZE, snap) == (
        shifted(state),
        [QuantizeClip(ClipTarget.DETAIL), ShowMessage("Quantize 1/16")],
    )


# Pad 4: Metronome


@pytest.mark.parametrize("state", MODES)
@pytest.mark.parametrize("on", [True, False])
def test_metronome(state, on):
    snap = replace(BASE, metronome=on)
    assert handle(state, layout.METRONOME, snap) == (state, controls.metronome(snap))


@pytest.mark.parametrize("state", MODES)
def test_shift_metronome_toggles_launch_quantization(state):
    new, actions = handle(
        shifted(state), layout.LAUNCH_QUANTIZATION, replace(BASE, launch_quantization=7)
    )
    assert new == replace(shifted(state), quantization_memory=7)
    assert actions == [SetLaunchQuantization(0), ShowMessage("Launch Quantization: None")]


# Pad 5: Fixed Length


@pytest.mark.parametrize("state", MODES)
@pytest.mark.parametrize(
    "bars, after, text",
    [
        (None, 1, "Fixed Length 1 bar"),
        (1, 2, "Fixed Length 2 bars"),
        (2, 4, "Fixed Length 4 bars"),
        (4, 8, "Fixed Length 8 bars"),
        (8, None, "Fixed Length OFF"),
    ],
)
def test_fixed_length_cycles(state, bars, after, text):
    new, actions = handle(replace(state, fixed_length=bars), layout.FIXED_LENGTH)
    assert new == replace(state, fixed_length=after)
    assert actions == [ShowMessage(text)]


def test_fixed_length_survives_a_mode_change():
    state, _ = handle(SESSION, layout.FIXED_LENGTH)
    state, _ = handle(state, layout.MODE_PAD)
    assert state.mode is Mode.LINNSTRUMENT
    assert state.fixed_length == 1
    state, _ = handle(state, layout.FIXED_LENGTH)
    state, _ = handle(state, layout.MODE_PAD)
    assert state.mode is Mode.SESSION
    assert state.fixed_length == 2


# Pad 6: Undo


@pytest.mark.parametrize("state", MODES)
@pytest.mark.parametrize("can_undo", [True, False])
def test_undo(state, can_undo):
    snap = replace(BASE, can_undo=can_undo)
    assert handle(state, layout.UNDO, snap) == (state, controls.undo(snap))


@pytest.mark.parametrize("state", MODES)
@pytest.mark.parametrize("can_redo", [True, False])
def test_shift_undo_redoes(state, can_redo):
    snap = replace(BASE, can_redo=can_redo)
    assert handle(shifted(state), layout.UNDO, snap) == (shifted(state), controls.redo(snap))


# Pad 7: Mode


def test_mode_pad_enters_linnstrument():
    state = State(window=Window(2, 1), fixed_length=4)
    assert handle(state, layout.MODE_PAD) == (
        modes.enter(state, Mode.LINNSTRUMENT),
        [EnterMode(Mode.LINNSTRUMENT)],
    )


def test_mode_pad_enters_session():
    state, actions = handle(LINNSTRUMENT, layout.MODE_PAD)
    assert state == SESSION
    assert actions == [EnterMode(Mode.SESSION)]


@pytest.mark.parametrize(
    "start, mixer, fx, more",
    [
        (SESSION, False, False, []),
        (State(mixer=True), True, False, [SetMixer(True), ShowMessage("Mixer Mode ON")]),
        (State(fx=True), False, True, [ShowMessage("FX Mode ON")]),
    ],
)
def test_back_returns_to_the_mode_left(start, mixer, fx, more):
    state, _ = handle(start, layout.MODE_PAD)
    assert state.mode is Mode.LINNSTRUMENT
    state, actions = handle(state, layout.MODE_PAD)
    assert state.mode is Mode.SESSION
    assert (state.mixer, state.fx) == (mixer, fx)
    assert actions == [EnterMode(Mode.SESSION)] + more


def test_back_after_scene_page_still_returns_to_mixer():
    state, _ = handle(State(mixer=True), layout.MODE_PAD)
    state = replace(state, scene_page=True)
    state, _ = handle(state, layout.SHIFT)
    state, _ = handle(state, layout.MODE_PAD)
    assert state.mixer


# Session-only empty Shift slots, and Shift + Fixed Length in both modes.
EMPTY_SHIFT = [
    (SESSION, layout.RECORD),
    (SESSION, layout.MODE_PAD),
    (SESSION, layout.FIXED_LENGTH),
    (LINNSTRUMENT, layout.FIXED_LENGTH),
]


@pytest.mark.parametrize("state, key", EMPTY_SHIFT)
def test_empty_shift_slots_do_nothing(state, key):
    assert handle(shifted(state), key, with_track()) == (shifted(state), [])


@pytest.mark.parametrize("state, key", EMPTY_SHIFT)
def test_empty_shift_slots_are_unlit(state, key):
    assert column_1.render(shifted(state), BASE)[key] == Light(OFF)


def test_shift_mode_in_session_keeps_the_mode():
    state, actions = handle(shifted(SESSION), layout.MODE_PAD)
    assert state.mode is Mode.SESSION
    assert actions == []


# Scene page


def test_shift_mode_opens_scene_page():
    state = shifted(LINNSTRUMENT)
    assert handle(state, layout.SCENE_PAGE) == (replace(state, scene_page=True), [])


def test_scene_page_survives_the_shift_release():
    assert handle(shifted(SCENES), layout.SHIFT, pressed=False) == (SCENES, [])


@pytest.mark.parametrize("pad", range(1, 8))
def test_scene_page_ignores_other_releases(pad):
    assert handle(SCENES, (1, pad), pressed=False) == (SCENES, [])


def test_scene_page_closes_on_a_shift_press():
    assert handle(SCENES, layout.SHIFT) == (LINNSTRUMENT, [])


@pytest.mark.parametrize("pad", range(1, 7))
def test_scene_page_launches_and_closes(pad):
    snap = replace(BASE, scene_count=10)
    assert handle(SCENES, (1, pad), snap) == (LINNSTRUMENT, [FireScene(pad - 1, legato=False)])


def test_scene_page_pad_7_is_dark_and_does_nothing():
    snap = replace(BASE, scene_count=10)
    assert handle(SCENES, layout.MODE_PAD, snap) == (SCENES, [])
    assert column_1.render(SCENES, snap)[layout.MODE_PAD] == Light(OFF)


def test_scene_page_launches_from_the_window():
    state = replace(SCENES, window=Window(scene=3))
    assert handle(state, (1, 2), replace(BASE, scene_count=10)) == (
        replace(state, scene_page=False),
        [FireScene(4, legato=False)],
    )


def test_scene_page_launch_fires_the_scenes_snapshot():
    state = replace(SCENES, fx_scenes=(None, None, (FxRack("A", "R", 0, (1.0,)),)))
    assert handle(state, (1, 3), replace(BASE, scene_count=10)) == (
        replace(state, scene_page=False),
        [FireScene(2, legato=False), RecallFxSnapshot(2, None, scene=True)],
    )


def test_scene_page_past_end_does_nothing():
    state = replace(SCENES, window=Window(scene=2))
    assert handle(state, (1, 3)) == (state, [])


def test_scene_page_lights():
    clip = SlotView(has_clip=True)
    playing = SlotView(has_clip=True, is_playing=True)
    tracks = (TrackView(index=0, slots=(clip, playing, SlotView())),)
    snap = replace(BASE, tracks=tracks, scene_count=5)
    state = replace(SCENES, window=Window(scene=2))
    frame = column_1.render(state, snap)
    assert set(frame) == {(1, p) for p in range(1, 9)}
    assert frame[(1, 1)] == Light(WHITE)
    assert frame[(1, 2)] == Light(LIME, Blink.TEMPO)
    assert frame[(1, 3)] == Light(OFF)  # no clip
    assert frame[(1, 4)] == Light(OFF)  # past the end of the Set
    assert frame[layout.SHIFT] == Light(WHITE)


# Lights


@pytest.mark.parametrize("state", MODES)
def test_normal_lights(state):
    frame = column_1.render(state, BASE)
    assert frame == {
        layout.PLAY_STOP: controls.play_light(BASE),
        layout.RECORD: (
            Light(RED) if state.mode is Mode.LINNSTRUMENT else controls.record_light(BASE)
        ),
        layout.CAPTURE: Light(LIME),
        layout.METRONOME: controls.metronome_light(BASE),
        layout.FIXED_LENGTH: Light(OFF),
        layout.UNDO: Light(WHITE),
        layout.MODE_PAD: Light(MAGENTA),
        layout.SHIFT: Light(WHITE),
    }


@pytest.mark.parametrize("state", MODES)
@pytest.mark.parametrize(
    "snapshot",
    [
        replace(BASE, is_playing=True, metronome=True, session_record=True),
        replace(ARRANGEMENT, arrangement_record=True),
    ],
)
def test_normal_lights_follow_live(state, snapshot):
    frame = column_1.render(state, snapshot)
    assert frame[layout.PLAY_STOP] == controls.play_light(snapshot)
    assert frame[layout.METRONOME] == controls.metronome_light(snapshot)
    if state.mode is Mode.SESSION:
        assert frame[layout.RECORD] == controls.record_light(snapshot)
    else:
        assert frame[layout.RECORD] == Light(RED)


@pytest.mark.parametrize("state", MODES)
@pytest.mark.parametrize(
    "bars, colour", [(None, OFF), (1, CYAN), (2, BLUE), (4, MAGENTA), (8, PINK)]
)
def test_fixed_length_colour(state, bars, colour):
    frame = column_1.render(replace(state, fixed_length=bars), BASE)
    assert frame[layout.FIXED_LENGTH] == Light(colour)


@pytest.mark.parametrize("quantization, light", [(4, Light(GREEN)), (0, Light(RED))])
@pytest.mark.parametrize("state", MODES)
def test_shift_lights(state, quantization, light):
    snap = replace(BASE, launch_quantization=quantization, session_record=True)
    frame = column_1.render(shifted(state), snap)
    linnstrument = state.mode is Mode.LINNSTRUMENT
    assert frame == {
        layout.PLAY_STOP: Light(RED),
        layout.RECORD: controls.record_light(snap) if linnstrument else Light(OFF),
        layout.QUANTIZE: Light(MAGENTA),
        layout.LAUNCH_QUANTIZATION: light,
        layout.FIXED_LENGTH: Light(OFF),
        layout.UNDO: Light(WHITE),
        layout.SCENE_PAGE: Light(PINK) if linnstrument else Light(OFF),
        layout.SHIFT: Light(WHITE, Blink.FAST),
    }


@pytest.mark.parametrize("held", [{"copy": True}, {"delete": True}])
def test_copy_or_delete_hides_the_shift_layer(held):
    frame = column_1.render(State(shift=True, **held), BASE)
    assert frame[layout.CAPTURE] == Light(LIME)
    assert frame[layout.SHIFT] == Light(WHITE, Blink.FAST)
