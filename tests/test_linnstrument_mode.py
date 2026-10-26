import pytest

from BleakLoop.core import column_1, layout, linnstrument_mode
from BleakLoop.core.model import PadPress, Snapshot, YAxis
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
def test_column_1_goes_to_column_1(pressed):
    event = PadPress(*layout.SHIFT, pressed)
    assert linnstrument_mode.handle(LINNSTRUMENT, event, BASE) == column_1.handle(
        LINNSTRUMENT, event, BASE
    )


@pytest.mark.parametrize("column", [2, 16])
def test_ignores_pads_outside_column_1(column):
    assert linnstrument_mode.handle(LINNSTRUMENT, PadPress(column, 8, True), BASE) == (
        LINNSTRUMENT,
        [],
    )


def test_ignores_other_events():
    assert linnstrument_mode.handle(LINNSTRUMENT, YAxis(1, 8, 64), BASE) == (LINNSTRUMENT, [])


def test_render_is_column_1():
    assert linnstrument_mode.render(LINNSTRUMENT, BASE) == column_1.render(LINNSTRUMENT, BASE)
    assert set(linnstrument_mode.render(LINNSTRUMENT, BASE)) == {(1, p) for p in range(1, 9)}
