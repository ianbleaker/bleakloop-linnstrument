import pytest

from BleakLoop.core import controls, engine, global_column, layout, linnstrument_mode
from BleakLoop.core.leds import LIME, OFF, ORANGE, Blink, Light
from BleakLoop.core.model import PadPress, Snapshot, StepTrack, ToggleDetailView, YAxis
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

LINNSTRUMENT = State(mode=Mode.LINNSTRUMENT)


@pytest.mark.parametrize("pressed", [True, False])
def test_global_column_goes_to_global_column(pressed):
    event = PadPress(*layout.GLOBAL.shift, pressed)
    assert linnstrument_mode.handle(LINNSTRUMENT, event, BASE) == global_column.handle(
        LINNSTRUMENT, event, BASE
    )


@pytest.mark.parametrize("column", [2, 16])
def test_ignores_pads_outside_global_column(column):
    assert linnstrument_mode.handle(LINNSTRUMENT, PadPress(column, 8, True), BASE) == (
        LINNSTRUMENT,
        [],
    )


def test_ignores_other_events():
    assert linnstrument_mode.handle(LINNSTRUMENT, YAxis(1, 8, 64), BASE) == (LINNSTRUMENT, [])


def test_render_is_global_column():
    assert linnstrument_mode.render(LINNSTRUMENT, BASE) == global_column.render(LINNSTRUMENT, BASE)
    assert set(linnstrument_mode.render(LINNSTRUMENT, BASE)) == {(layout.GLOBAL_COLUMN, p) for p in range(1, 9)}


@pytest.fixture
def device_clip_layer(monkeypatch):
    # Device/Clip on Fixed Length's pad, and Track-/+ on its layer's pads 1 and 2.
    monkeypatch.delattr(layout.LINNSTRUMENT, "fixed_length")
    monkeypatch.setattr(layout.LINNSTRUMENT, "device_clip", (1, 5), raising=False)
    monkeypatch.setattr(layout.LINNSTRUMENT_DEVICE_CLIP, "tracks", {(1, 1): -1, (1, 2): 1}, raising=False)


def _press(state, key, pressed=True, snapshot=BASE):
    return engine.handle(state, PadPress(*key, pressed), snapshot)


def test_device_clip_held_steps_the_track_on_its_layer(device_clip_layer):
    held, _ = _press(LINNSTRUMENT, (1, 5))
    assert held.device_clip
    stepped, actions = _press(held, (1, 2))
    assert actions[0] == StepTrack(1)
    released, actions = _press(stepped, (1, 5), pressed=False)
    assert not released.device_clip and actions == []


def test_a_device_clip_tap_flips_the_detail_view(device_clip_layer):
    held, _ = _press(LINNSTRUMENT, (1, 5))
    _, actions = _press(held, (1, 5), pressed=False)
    assert actions[0] == ToggleDetailView()


def test_the_layer_shows_while_device_clip_is_held(device_clip_layer):
    assert linnstrument_mode.render(LINNSTRUMENT, BASE)[(1, 1)] == controls.play_light(BASE)
    held, _ = _press(LINNSTRUMENT, (1, 5))
    frame = linnstrument_mode.render(held, BASE)
    assert frame[(1, 1)] == frame[(1, 2)] == Light(LIME)
    assert frame[(1, 5)] == Light(ORANGE, Blink.FAST)
    assert all(frame[(1, pad)] == Light(OFF) for pad in (3, 4, 6, 7, 8))
