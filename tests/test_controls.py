from dataclasses import replace

from BleakLoop.core import controls
from BleakLoop.core.leds import BLUE, GREEN, LIME, OFF, ORANGE, WHITE, Blink, Light
from BleakLoop.core.model import (
    Redo,
    ShowMessage,
    SlotView,
    Snapshot,
    ToggleMetronome,
    TrackView,
    Undo,
)

BASE = Snapshot(
    is_playing=False, song_beats=0.0, tempo=120.0, metronome=False, session_view=True
)

EMPTY = SlotView()
CLIP = SlotView(has_clip=True)
PLAYING = SlotView(has_clip=True, is_playing=True)


def with_tracks(*slot_rows, scene_count=7):
    tracks = tuple(TrackView(index=i, slots=slots) for i, slots in enumerate(slot_rows))
    return replace(BASE, tracks=tracks, track_count=len(tracks), scene_count=scene_count)


def test_metronome_light():
    assert controls.metronome_light(BASE) == Light(ORANGE)
    assert controls.metronome_light(replace(BASE, metronome=True)) == Light(ORANGE, Blink.FAST)


def test_play_light():
    assert controls.play_light(BASE) == Light(BLUE)
    assert controls.play_light(replace(BASE, is_playing=True)) == Light(GREEN, Blink.TEMPO)


def test_metronome_turns_on():
    assert controls.metronome(BASE) == [ToggleMetronome(), ShowMessage("Metronome ON")]


def test_metronome_turns_off():
    assert controls.metronome(replace(BASE, metronome=True)) == [
        ToggleMetronome(),
        ShowMessage("Metronome OFF"),
    ]


def test_undo():
    assert controls.undo(replace(BASE, can_undo=True)) == [Undo(), ShowMessage("Undo")]


def test_nothing_to_undo():
    assert controls.undo(BASE) == [ShowMessage("Nothing to undo")]


def test_redo():
    assert controls.redo(replace(BASE, can_redo=True)) == [Redo(), ShowMessage("Redo")]


def test_nothing_to_redo():
    assert controls.redo(BASE) == [ShowMessage("Nothing to redo")]


def test_scene_light_past_the_end():
    snapshot = with_tracks((CLIP,) * 7, scene_count=5)
    assert controls.scene_light(snapshot, 2, 3) == Light(OFF)


def test_scene_light_playing_beats_has_clip():
    snapshot = with_tracks((CLIP,), (PLAYING,))
    assert controls.scene_light(snapshot, 0, 0) == Light(LIME, Blink.TEMPO)


def test_scene_light_has_clip():
    snapshot = with_tracks((EMPTY,), (CLIP,))
    assert controls.scene_light(snapshot, 0, 0) == Light(WHITE)


def test_scene_light_empty():
    snapshot = with_tracks((EMPTY,), (EMPTY,))
    assert controls.scene_light(snapshot, 0, 0) == Light(OFF)


def test_scene_light_skips_short_slots():
    snapshot = with_tracks((EMPTY,), (EMPTY, PLAYING))
    assert controls.scene_light(snapshot, 0, 1) == Light(LIME, Blink.TEMPO)
    assert controls.scene_light(with_tracks((CLIP,)), 0, 1) == Light(OFF)
