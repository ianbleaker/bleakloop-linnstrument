from BleakLoop.core import layout, views
from BleakLoop.core.modes import Mode, State


def test_the_geometry_is_layouts():
    assert views.ROWS == range(1, layout.ROWS + 1)
    assert views.COLUMNS == range(1, layout.COLUMNS)
    assert views.GLOBAL_COLUMN == range(layout.GLOBAL_COLUMN, layout.GLOBAL_COLUMN + 1)
    assert views.GRID_COLUMNS == layout.GRID_COLUMNS
    assert views.SCENE_COLUMN == range(layout.SCENE_COLUMN, layout.SCENE_COLUMN + 1)
    assert views.SCENES == range(1, layout.WINDOW_SCENES + 1)
    first = layout.GRID_COLUMNS[0]
    assert views.SPLIT_TRACK_COLUMNS == range(first, first + layout.SPLIT_TRACKS)
    assert views.SPLIT_FADER_COLUMNS == layout.SPLIT_FADER_COLUMNS
    assert views.FX_FADER_COLUMNS == layout.FX_FADER_COLUMNS
    assert views.SEQ_STEP_COLUMNS == layout.SEQ_STEP_COLUMNS
    assert views.SEQ_NOTE_COLUMNS == layout.SEQ_NOTE_COLUMNS


def test_every_mode_and_sub_state_has_its_view():
    cases = {
        State(): "session",
        State(split=True): "split",
        State(split=True, split_snapshots=True): "split-snapshots",
        State(mixer=True): "mixer",
        State(mixer=True, mixer_split=True): "mixer-split",
        State(fx=True): "fx",
        State(mode=Mode.SEQUENCER): "sequencer",
        State(mode=Mode.SEQUENCER, seq_settings=True): "sequencer-settings",
        State(mode=Mode.LINNSTRUMENT): "linnstrument",
    }
    for state, name in cases.items():
        assert views.view_of(state).name == name
        assert views.view_of(state).mode == state.mode.name


def test_a_layer_takes_the_place_of_the_sections_it_replaces():
    session = views.BY_NAME["session"]
    assert views.live(session, ("shift",)) == ("global-shift", "view-shift", "navigation-shift")
    assert views.live(session, ("shift", "device_clip")) == ("global-shift", "view-shift", "device-clip")
    sequencer = views.BY_NAME["sequencer"]
    assert views.live(sequencer, ("shift",)) == ("sequencer-global-shift", "sequencer-nav-shift", "sequencer-grid")


def test_linnstrument_modes_sections_reach_column_1_only():
    for section in ("linnstrument", "linnstrument-shift", "linnstrument-scenes"):
        assert views.columns(section) == {1}
    assert views.columns("global") == set(range(1, 17))
