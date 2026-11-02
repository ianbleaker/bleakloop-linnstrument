import pytest

from BleakLoop.core import global_column, layout, linnstrument_mode
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
def test_global_column_goes_to_global_column(pressed):
    event = PadPress(*layout.SHIFT, pressed)
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
