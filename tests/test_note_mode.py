from dataclasses import replace

import pytest

from BleakLoop.core import controls, layout, note_mode, values
from BleakLoop.core.layout import Window
from BleakLoop.core.leds import BLUE, GREEN, LIME, MAGENTA, OFF, PINK, WHITE, Blink, Light
from BleakLoop.core.model import (
    AddScene,
    CaptureMidi,
    ControlCC,
    EnterMode,
    FireScene,
    FireSlot,
    PadPress,
    SelectedTrack,
    ShowClip,
    ShowMessage,
    SlotView,
    Snapshot,
    StopTrackClips,
    TogglePlay,
    TrackView,
)
from BleakLoop.core.modes import Mode, State

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

NOTE = State(mode=Mode.NOTE)
SCENES = replace(NOTE, scene_page=True)

F, T = False, True
ARMED = SelectedTrack(index=2, name="Keys", armed=True, clips=(F, F, F, F))


def cc(key, value=127):
    # CC 102 is pad 8.
    return ControlCC(values.CONTROL_CC_BASE + layout.ROWS - key[1], value)


def with_track(snapshot=BASE, **k):
    return replace(snapshot, selected_track=replace(ARMED, **k))


# Input


CONTROLS = [
    layout.UNDO,
    layout.RECORD_CLIP,
    layout.CAPTURE,
    layout.SCENE_PAGE,
    layout.METRONOME,
    layout.PLAY_STOP,
    layout.RECORD,
    layout.MODE_PAD,
]


@pytest.mark.parametrize("key", CONTROLS)
def test_any_value_is_a_press(key):
    snap = with_track()
    assert note_mode.handle(NOTE, cc(key, 0), snap) == note_mode.handle(NOTE, cc(key, 127), snap)


@pytest.mark.parametrize("number", [1, 101, 110])
def test_ignores_ccs_outside_column_1(number):
    assert note_mode.handle(NOTE, ControlCC(number, 127), BASE) == (NOTE, [])


def test_ignores_pads():
    assert note_mode.handle(NOTE, PadPress(1, 8, True), BASE) == (NOTE, [])


@pytest.mark.parametrize("can_undo", [True, False])
def test_undo(can_undo):
    snap = replace(BASE, can_undo=can_undo)
    assert note_mode.handle(NOTE, cc(layout.UNDO), snap) == (NOTE, controls.undo(snap))


@pytest.mark.parametrize("on", [True, False])
def test_metronome(on):
    snap = replace(BASE, metronome=on)
    assert note_mode.handle(NOTE, cc(layout.METRONOME), snap) == (NOTE, controls.metronome(snap))


# Record Clip


def record_clip(snapshot, state=NOTE):
    return note_mode.handle(state, cc(layout.RECORD_CLIP), snapshot)


def test_record_clip_without_selected_track():
    assert record_clip(BASE) == (NOTE, [ShowMessage("No selected track")])


def test_record_clip_on_group_track():
    snap = with_track(is_foldable=True, armed=True)
    assert record_clip(snap) == (NOTE, [ShowMessage("Cannot record on a group track")])


def test_record_clip_on_unarmed_track():
    assert record_clip(with_track(armed=False)) == (NOTE, [ShowMessage("Track not armed")])


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
    state, actions = record_clip(snap)
    assert state == NOTE
    assert actions == [
        FireSlot(2, scene, legato=False, record_length=None),
        ShowClip(2, scene),
        ShowMessage("Record Clip"),
    ]


def test_record_clip_adds_scene_when_full():
    snap = replace(with_track(clips=(T, T, T)), scene_count=3)
    state, actions = record_clip(snap)
    assert state == NOTE
    assert actions == [
        AddScene(),
        FireSlot(2, 3, legato=False, record_length=None),
        ShowClip(2, 3),
        ShowMessage("Record Clip: new scene"),
    ]


@pytest.mark.parametrize("numerator, beats", [(4, 8.0), (3, 6.0)])
def test_record_clip_uses_fixed_length(numerator, beats):
    snap = replace(with_track(), signature_numerator=numerator)
    _, actions = record_clip(snap, replace(NOTE, fixed_length=2))
    assert actions[0] == FireSlot(2, 0, legato=False, record_length=beats)


# Capture MIDI


def test_capture_midi_with_nothing_to_capture():
    actions = [ShowMessage("Nothing to capture")]
    assert note_mode.handle(NOTE, cc(layout.CAPTURE), BASE) == (NOTE, actions)


def test_capture_midi():
    snap = replace(BASE, can_capture_midi=True)
    actions = [CaptureMidi(), ShowMessage("Capture MIDI")]
    assert note_mode.handle(NOTE, cc(layout.CAPTURE), snap) == (NOTE, actions)


# Pad 6


def test_pad_6_stops_selected_track_in_session_view():
    actions = [StopTrackClips(2), ShowMessage("Stop clips: Keys")]
    assert note_mode.handle(NOTE, cc(layout.PLAY_STOP), with_track()) == (NOTE, actions)


def test_pad_6_without_selected_track_in_session_view():
    actions = [ShowMessage("No selected track")]
    assert note_mode.handle(NOTE, cc(layout.PLAY_STOP), BASE) == (NOTE, actions)


@pytest.mark.parametrize("snap", [ARRANGEMENT, with_track(ARRANGEMENT)])
def test_pad_6_toggles_play_in_arrangement_view(snap):
    assert note_mode.handle(NOTE, cc(layout.PLAY_STOP), snap) == (NOTE, [TogglePlay()])


@pytest.mark.parametrize("snap", [BASE, ARRANGEMENT])
def test_record_pad(snap):
    assert note_mode.handle(NOTE, cc(layout.RECORD), snap) == (NOTE, controls.record(snap))


# Pages and mode


def test_mode_pad_enters_session():
    state, actions = note_mode.handle(NOTE, cc(layout.MODE_PAD), BASE)
    assert state.mode is Mode.SESSION
    assert not state.scene_page
    assert actions == [EnterMode(Mode.SESSION)]


def test_pad_4_opens_scene_page():
    assert note_mode.handle(NOTE, cc(layout.SCENE_PAGE), BASE) == (SCENES, [])


def test_scene_page_launches_window_scene():
    state = replace(SCENES, window=Window(scene=3))
    snap = replace(BASE, scene_count=10)
    assert note_mode.handle(state, cc((1, 2)), snap) == (
        replace(state, scene_page=False),
        [FireScene(4, legato=False)],
    )


def test_scene_page_past_end_does_nothing():
    state = replace(SCENES, window=Window(scene=2))
    assert note_mode.handle(state, cc((1, 3)), BASE) == (state, [])


def test_scene_page_pad_8_returns():
    assert note_mode.handle(SCENES, cc(layout.MODE_PAD), BASE) == (NOTE, [])


@pytest.mark.parametrize("pad", [3, 5, 6, 7])
def test_scene_page_pads_launch_scenes(pad):
    snap = replace(with_track(), scene_count=10, can_capture_midi=True)
    assert note_mode.handle(SCENES, cc((1, pad)), snap) == (
        NOTE,
        [FireScene(pad - 1, legato=False)],
    )


# Rendering


def test_controls_page_lights():
    frame = note_mode.render(NOTE, BASE)
    assert frame == {
        (1, 1): Light(WHITE),
        (1, 2): Light(MAGENTA),
        (1, 3): Light(LIME),
        (1, 4): Light(PINK),
        (1, 5): controls.metronome_light(BASE),
        (1, 6): Light(GREEN),
        (1, 7): controls.record_light(BASE),
        (1, 8): Light(WHITE),
    }


def test_controls_page_metronome_light():
    snap = replace(BASE, metronome=True)
    assert note_mode.render(NOTE, snap)[layout.METRONOME] == controls.metronome_light(snap)


@pytest.mark.parametrize(
    "playing, light", [(False, Light(BLUE)), (True, Light(GREEN, Blink.TEMPO))]
)
def test_pad_6_light_in_arrangement_view(playing, light):
    snap = replace(ARRANGEMENT, is_playing=playing)
    assert note_mode.render(NOTE, snap)[layout.PLAY_STOP] == light


def test_pad_6_light_in_session_view_while_playing():
    snap = replace(BASE, is_playing=True)
    assert note_mode.render(NOTE, snap)[layout.PLAY_STOP] == Light(GREEN)


@pytest.mark.parametrize(
    "snap",
    [
        replace(BASE, session_record=True),
        replace(ARRANGEMENT, arrangement_record=True),
        replace(ARRANGEMENT, back_to_arranger=True),
    ],
)
def test_record_light(snap):
    assert note_mode.render(NOTE, snap)[layout.RECORD] == controls.record_light(snap)


def test_scene_page_lights():
    clip = SlotView(has_clip=True)
    playing = SlotView(has_clip=True, is_playing=True)
    empty = SlotView()
    tracks = (TrackView(index=0, slots=(clip, playing, empty)),)
    snap = replace(BASE, tracks=tracks, scene_count=5)
    state = replace(SCENES, window=Window(scene=2))
    frame = note_mode.render(state, snap)
    assert set(frame) == {(1, p) for p in range(1, 9)}
    for pad in range(1, 8):
        assert frame[(1, pad)] == controls.scene_light(snap, 2, pad - 1)
    assert frame[(1, 1)] == Light(WHITE)
    assert frame[(1, 2)] == Light(LIME, Blink.TEMPO)
    assert frame[(1, 4)] == Light(OFF)  # past the end of the Set
    assert frame[layout.MODE_PAD] == Light(WHITE)
