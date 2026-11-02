from dataclasses import replace

import pytest

from BleakLoop.core import controls, global_column, layout, modes
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
    SetTempo,
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
    return global_column.handle(state, press(key, pressed), snapshot)


def with_track(snapshot=BASE, **k):
    return replace(snapshot, selected_track=replace(ARMED, **k))


# Shift


@pytest.mark.parametrize("state", MODES)
def test_shift_press_and_release(state):
    assert handle(state, layout.GLOBAL.shift) == (shifted(state), [])
    assert handle(shifted(state), layout.GLOBAL.shift, pressed=False) == (state, [])


@pytest.mark.parametrize("state", MODES + [shifted(SESSION), shifted(LINNSTRUMENT)])
@pytest.mark.parametrize("pad", range(1, 8))
def test_releases_do_nothing(state, pad):
    assert handle(state, (layout.GLOBAL_COLUMN, pad), with_track(), pressed=False) == (state, [])


# Pad 1: Play/Stop


@pytest.mark.parametrize("state", MODES)
@pytest.mark.parametrize("snapshot", [BASE, ARRANGEMENT, with_track()])
def test_play_stop_is_transport(state, snapshot):
    assert handle(state, layout.GLOBAL.play_stop, snapshot) == (state, [TogglePlay()])


def test_shift_play_stop_stops_all_in_session():
    state = shifted(SESSION)
    assert handle(state, layout.GLOBAL.play_stop, with_track()) == (
        state,
        [StopAllClips(), ShowMessage("Stop all clips")],
    )


def test_shift_play_stop_stops_selected_track_in_linnstrument():
    state = shifted(LINNSTRUMENT)
    assert handle(state, layout.GLOBAL.play_stop, with_track()) == (
        state,
        [StopTrackClips(2), ShowMessage("Stop clips: Keys")],
    )


def test_shift_play_stop_without_selected_track_in_linnstrument():
    state = shifted(LINNSTRUMENT)
    assert handle(state, layout.GLOBAL.play_stop) == (state, [ShowMessage("No selected track")])


# Pad 2: Record


@pytest.mark.parametrize("snapshot", [BASE, ARRANGEMENT])
def test_record_in_session(snapshot):
    assert handle(SESSION, layout.GLOBAL.record, snapshot) == (SESSION, controls.record(snapshot))


@pytest.mark.parametrize("snapshot", [BASE, ARRANGEMENT])
def test_shift_record_in_linnstrument(snapshot):
    state = shifted(LINNSTRUMENT)
    assert handle(state, layout.GLOBAL.record, snapshot) == (state, controls.record(snapshot))


def record_clip(snapshot, state=LINNSTRUMENT):
    return handle(state, layout.GLOBAL.record, snapshot)


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
    assert handle(SESSION, layout.GLOBAL.capture) == (
        SESSION,
        [CaptureAndInsertScene(), ShowMessage("Capture and Insert Scene")],
    )


def test_capture_midi_with_nothing_to_capture():
    assert handle(LINNSTRUMENT, layout.GLOBAL.capture) == (
        LINNSTRUMENT,
        [ShowMessage("Nothing to capture")],
    )


def test_capture_midi():
    snap = replace(BASE, can_capture_midi=True)
    assert handle(LINNSTRUMENT, layout.GLOBAL.capture, snap) == (
        LINNSTRUMENT,
        [CaptureMidi(), ShowMessage("Capture MIDI")],
    )


@pytest.mark.parametrize("state", MODES)
def test_shift_capture_quantizes(state):
    snap = replace(BASE, detail_clip=ClipView(is_midi=True))
    assert handle(shifted(state), layout.GLOBAL_SHIFT.quantize, snap) == (
        shifted(state),
        [QuantizeClip(ClipTarget.DETAIL), ShowMessage("Quantize 1/16")],
    )


# Pad 4: Metronome


@pytest.mark.parametrize("state", MODES)
@pytest.mark.parametrize("on", [True, False])
def test_metronome(state, on):
    snap = replace(BASE, metronome=on)
    assert handle(state, layout.GLOBAL.metronome, snap) == (state, controls.metronome(snap))


@pytest.mark.parametrize("state", MODES)
def test_shift_metronome_toggles_launch_quantization(state):
    new, actions = handle(
        shifted(state), layout.GLOBAL_SHIFT.launch_quantization, replace(BASE, launch_quantization=7)
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
    new, actions = handle(replace(state, fixed_length=bars), layout.GLOBAL.fixed_length)
    assert new == replace(state, fixed_length=after)
    assert actions == [ShowMessage(text)]


def test_fixed_length_survives_a_mode_change():
    state, _ = handle(SESSION, layout.GLOBAL.fixed_length)
    state, _ = handle(state, layout.GLOBAL.linnstrument_mode)
    assert state.mode is Mode.LINNSTRUMENT
    assert state.fixed_length == 1
    state, _ = handle(state, layout.GLOBAL.fixed_length)
    state, _ = handle(state, layout.GLOBAL.linnstrument_mode)
    assert state.mode is Mode.SESSION
    assert state.fixed_length == 2


# Pad 6: Undo


@pytest.mark.parametrize("state", MODES)
@pytest.mark.parametrize("can_undo", [True, False])
def test_undo(state, can_undo):
    snap = replace(BASE, can_undo=can_undo)
    assert handle(state, layout.GLOBAL.undo, snap) == (state, controls.undo(snap))


@pytest.mark.parametrize("state", MODES)
@pytest.mark.parametrize("can_redo", [True, False])
def test_shift_undo_redoes(state, can_redo):
    snap = replace(BASE, can_redo=can_redo)
    assert handle(shifted(state), layout.GLOBAL.undo, snap) == (shifted(state), controls.redo(snap))


# Pad 7: Mode


def test_mode_pad_enters_linnstrument():
    state = State(window=Window(2, 1), fixed_length=4)
    assert handle(state, layout.GLOBAL.linnstrument_mode) == (
        modes.enter(state, Mode.LINNSTRUMENT),
        [EnterMode(Mode.LINNSTRUMENT)],
    )


def test_mode_pad_enters_session():
    state, actions = handle(LINNSTRUMENT, layout.GLOBAL.linnstrument_mode)
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
    state, _ = handle(start, layout.GLOBAL.linnstrument_mode)
    assert state.mode is Mode.LINNSTRUMENT
    state, actions = handle(state, layout.GLOBAL.linnstrument_mode)
    assert state.mode is Mode.SESSION
    assert (state.mixer, state.fx) == (mixer, fx)
    assert actions == [EnterMode(Mode.SESSION)] + more


def test_back_after_scene_page_still_returns_to_mixer():
    state, _ = handle(State(mixer=True), layout.GLOBAL.linnstrument_mode)
    state = replace(state, scene_page=True)
    state, _ = handle(state, layout.GLOBAL.shift)
    state, _ = handle(state, layout.GLOBAL.linnstrument_mode)
    assert state.mixer


# Session-only empty Shift slots, and Shift + Fixed Length in both modes.
EMPTY_SHIFT = [
    (SESSION, layout.GLOBAL.record),
    (SESSION, layout.GLOBAL.linnstrument_mode),
    (SESSION, layout.GLOBAL.fixed_length),
    (LINNSTRUMENT, layout.GLOBAL.fixed_length),
]


@pytest.mark.parametrize("state, key", EMPTY_SHIFT)
def test_empty_shift_slots_do_nothing(state, key):
    assert handle(shifted(state), key, with_track()) == (shifted(state), [])


@pytest.mark.parametrize("state, key", EMPTY_SHIFT)
def test_empty_shift_slots_are_unlit(state, key):
    assert global_column.render(shifted(state), BASE)[key] == Light(OFF)


def test_shift_mode_in_session_keeps_the_mode():
    state, actions = handle(shifted(SESSION), layout.GLOBAL.linnstrument_mode)
    assert state.mode is Mode.SESSION
    assert actions == []


# Scene page


def test_shift_mode_opens_scene_page():
    state = shifted(LINNSTRUMENT)
    assert handle(state, layout.LINNSTRUMENT_SHIFT.scene_page) == (replace(state, scene_page=True), [])


def test_scene_page_survives_the_shift_release():
    assert handle(shifted(SCENES), layout.GLOBAL.shift, pressed=False) == (SCENES, [])


@pytest.mark.parametrize("pad", range(1, 8))
def test_scene_page_ignores_other_releases(pad):
    assert handle(SCENES, (layout.GLOBAL_COLUMN, pad), pressed=False) == (SCENES, [])


def test_scene_page_closes_on_a_shift_press():
    assert handle(SCENES, layout.GLOBAL.shift) == (LINNSTRUMENT, [])


@pytest.mark.parametrize("pad", range(1, 7))
def test_scene_page_launches_and_closes(pad):
    snap = replace(BASE, scene_count=10)
    assert handle(SCENES, (layout.GLOBAL_COLUMN, pad), snap) == (LINNSTRUMENT, [FireScene(pad - 1, legato=False)])


def test_scene_page_pad_7_is_dark_and_does_nothing():
    snap = replace(BASE, scene_count=10)
    assert handle(SCENES, layout.GLOBAL.linnstrument_mode, snap) == (SCENES, [])
    assert global_column.render(SCENES, snap)[layout.GLOBAL.linnstrument_mode] == Light(OFF)


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
    frame = global_column.render(state, snap)
    assert set(frame) == {(layout.GLOBAL_COLUMN, p) for p in range(1, 9)}
    assert frame[(1, 1)] == Light(WHITE)
    assert frame[(1, 2)] == Light(LIME)
    assert frame[(1, 3)] == Light(OFF)  # no clip
    assert frame[(1, 4)] == Light(OFF)  # past the end of the Set
    assert frame[layout.GLOBAL.shift] == Light(WHITE)


# Lights


@pytest.mark.parametrize("state", MODES)
def test_normal_lights(state):
    frame = global_column.render(state, BASE)
    assert frame == {
        layout.GLOBAL.play_stop: controls.play_light(BASE),
        layout.GLOBAL.record: (
            Light(RED) if state.mode is Mode.LINNSTRUMENT else controls.record_light(BASE)
        ),
        layout.GLOBAL.capture: Light(LIME),
        layout.GLOBAL.metronome: controls.metronome_light(BASE),
        layout.GLOBAL.fixed_length: Light(OFF),
        layout.GLOBAL.undo: Light(WHITE),
        layout.GLOBAL.linnstrument_mode: Light(MAGENTA),
        layout.GLOBAL.shift: Light(WHITE),
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
    frame = global_column.render(state, snapshot)
    assert frame[layout.GLOBAL.play_stop] == controls.play_light(snapshot)
    assert frame[layout.GLOBAL.metronome] == controls.metronome_light(snapshot)
    if state.mode is Mode.SESSION:
        assert frame[layout.GLOBAL.record] == controls.record_light(snapshot)
    else:
        assert frame[layout.GLOBAL.record] == Light(RED)


@pytest.mark.parametrize("state", MODES)
@pytest.mark.parametrize(
    "bars, colour", [(None, OFF), (1, CYAN), (2, BLUE), (4, MAGENTA), (8, PINK)]
)
def test_fixed_length_colour(state, bars, colour):
    frame = global_column.render(replace(state, fixed_length=bars), BASE)
    assert frame[layout.GLOBAL.fixed_length] == Light(colour)


@pytest.mark.parametrize("quantization, light", [(4, Light(GREEN)), (0, Light(RED))])
@pytest.mark.parametrize("state", MODES)
def test_shift_lights(state, quantization, light):
    snap = replace(BASE, launch_quantization=quantization, session_record=True)
    frame = global_column.render(shifted(state), snap)
    linnstrument = state.mode is Mode.LINNSTRUMENT
    assert frame == {
        layout.GLOBAL.play_stop: Light(RED),
        layout.GLOBAL.record: controls.record_light(snap) if linnstrument else Light(OFF),
        layout.GLOBAL_SHIFT.quantize: Light(MAGENTA),
        layout.GLOBAL_SHIFT.launch_quantization: light,
        layout.GLOBAL.fixed_length: Light(OFF),
        layout.GLOBAL.undo: Light(WHITE),
        layout.LINNSTRUMENT_SHIFT.scene_page: Light(PINK) if linnstrument else Light(OFF),
        layout.GLOBAL.shift: Light(WHITE, Blink.FAST),
    }


@pytest.mark.parametrize("held", [{"copy": True}, {"delete": True}])
def test_copy_or_delete_hides_the_shift_layer(held):
    frame = global_column.render(State(shift=True, **held), BASE)
    assert frame[layout.GLOBAL.capture] == Light(LIME)
    assert frame[layout.GLOBAL.shift] == Light(WHITE, Blink.FAST)


def test_a_mode_moves_its_own_buttons_alone(monkeypatch):
    # Sequencer Mode's Play and Undo swap pads; Session Mode's stay put.
    # Each is a fallback until moved, and the first move hides the other's fallback.
    undo, play = layout.GLOBAL.undo, layout.GLOBAL.play_stop
    monkeypatch.setattr(layout.SEQUENCER_GLOBAL, "play_stop", undo, raising=False)
    monkeypatch.setattr(layout.SEQUENCER_GLOBAL, "undo", play, raising=False)
    sequencer = State(mode=Mode.SEQUENCER)
    assert handle(sequencer, layout.GLOBAL.undo, BASE)[1] == [TogglePlay()]
    assert handle(SESSION, layout.GLOBAL.play_stop, BASE)[1] == [TogglePlay()]
    frame = global_column.render(sequencer, BASE)
    assert frame[layout.GLOBAL.undo] == controls.play_light(BASE)


def test_any_song_level_function_works_in_column_1(monkeypatch):
    # Tempo +1 on Linnstrument Mode's Fixed Length pad: it overrides the fallback there only.
    monkeypatch.setattr(layout.LINNSTRUMENT, "tempo", {layout.GLOBAL.fixed_length: 1}, raising=False)
    snapshot = replace(BASE, tempo=120.0)
    _, actions = handle(LINNSTRUMENT, layout.GLOBAL.fixed_length, snapshot)
    assert SetTempo(121.0) in actions
    assert global_column.render(LINNSTRUMENT, snapshot)[layout.GLOBAL.fixed_length] == Light(GREEN)
    assert handle(SESSION, layout.GLOBAL.fixed_length)[0].fixed_length == 1


def test_every_moved_function_runs_in_all_its_modes():
    from BleakLoop.core import catalogue, functions

    moved = {
        "play_stop", "record", "capture", "record_clip", "capture_midi", "metronome",
        "fixed_length", "undo", "redo", "back", "linnstrument_mode", "stop_all", "stop_track",
        "quantize", "launch_quantization", "scene_page", "close_scenes", "tempo", "unmute_all",
        "unsolo_all", "unarm_all", "window", "fader_source", "device_clip", "shift", "stop",
    }
    assert {(name, mode) for name in moved for mode in catalogue.MODES[name]} <= functions.registered()
    both = {"session", "mixer", "fx", "seq", "copy", "delete"}
    assert {(name, mode) for name in both for mode in catalogue.MODES[name]} <= functions.registered()
    own = {"reserved", "double", "halve", "follow", "up", "down", "view", "rates", "triplet", "pages", "slots", "scene_slots", "bars"}
    assert {(name, mode) for name in own for mode in catalogue.MODES[name]} <= functions.registered()
