"""The user's buttons file: its changes merge over the shipped file, within the rules."""

from pathlib import Path

import pytest

from BleakLoop.core import buttons, layout, userfile

FIXTURES = Path(__file__).parent / "fixtures" / "userfile"


@pytest.fixture
def shipped():
    # Puts the shipped layout back after a test reloads with a user file.
    yield
    buttons.reload(buttons.PATH)


def _load(stem):
    return buttons.load(buttons.PATH, FIXTURES / f"{stem}.toml")


def test_a_moved_pad_merges_over_the_shipped_one():
    registry = _load("moved_pad")
    assert registry.pos("global.metronome") == (1, 5)
    assert registry.pos("global.fixed_length") == (1, 4)
    assert registry.pos("global.undo") == (1, 6)
    assert registry.overlay == {
        "global": {"metronome": {"pad": [1, 5]}, "fixed_length": {"pad": [1, 4]}}
    }


def test_a_new_tempo_button_joins_the_group():
    registry = _load("new_tempo")
    assert registry.group("global-shift", "tempo") == {(1, 2): 5}
    assert registry.group("navigation-shift", "tempo") == {(16, 1): 1, (16, 2): -1}


def test_a_removed_button_is_gone():
    registry = _load("removed_button")
    assert "navigation_shift.fader_source" not in registry.entries()


def test_removing_a_linnstrument_button_leaves_its_pad_empty(shipped):
    assert layout.LINNSTRUMENT.at((1, 2))[1] == "record_clip"
    buttons.reload(buttons.PATH, FIXTURES / "removed_linnstrument.toml")
    assert layout.LINNSTRUMENT.at((1, 2)) is None
    assert layout.GLOBAL.at((1, 2))[1] == "record"


@pytest.mark.parametrize(
    "stem, error",
    [
        ("removed_slot", "slots buttons can't be removed"),
        ("changed_page", "pages values can't change"),
        ("added_rate", "rates buttons can't be added"),
        ("unknown_outcome", "no such message 'maybe'"),
        ("extra_placeholder", "unknown placeholder {time}; it may use {bpm}"),
        ("manual", "manual feeds the repo's manual"),
        ("manual_format", "manual_format feeds the repo's manual"),
        ("clash", "taken by"),
    ],
)
def test_a_change_outside_the_rules_is_refused_naming_the_user_file(stem, error):
    path = FIXTURES / f"{stem}.toml"
    with pytest.raises(ValueError, match=error) as raised:
        buttons.load(buttons.PATH, path)
    assert str(raised.value).startswith(f"{path}: ")


@pytest.mark.parametrize(
    "text, error",
    [
        ("[fx.bank_8]\nremoved = true\n", "banks buttons can't be removed"),
        ("[fx.bank_2]\nvalue = 3\n", "banks values can't change"),
        ('[fx.bank_9]\npad = [14, 8]\ndoes = "banks"\nvalue = 9\n', "banks buttons can't be added"),
    ],
)
def test_banks_are_a_fixed_group(tmp_path, text, error):
    path = tmp_path / "buttons.toml"
    path.write_text(text)
    with pytest.raises(ValueError, match=error):
        buttons.load(buttons.PATH, path)


def test_a_bank_may_move(tmp_path):
    path = tmp_path / "buttons.toml"
    path.write_text("[fx.bank_8]\npad = [14, 8]\n")
    assert buttons.load(buttons.PATH, path).pos("fx.bank_8") == (14, 8)


def test_a_full_copy_of_the_shipped_file_loads_unchanged(tmp_path):
    copy = tmp_path / "buttons.toml"
    copy.write_bytes(buttons.PATH.read_bytes())
    registry = buttons.load(buttons.PATH, copy)
    assert registry.entries() == buttons.load(buttons.PATH).entries()


def test_docs_fields_equal_to_the_shipped_ones_merge_and_changed_ones_dont():
    shipped = buttons._read(buttons.PATH)
    name, item = next((name, item) for name, item in shipped["functions"].items() if "manual" in item)
    same = {"manual_format": shipped["manual_format"], "functions": {name: {"manual": item["manual"]}}}
    merged, _ = userfile.merge(shipped, same)
    assert merged == shipped
    with pytest.raises(ValueError, match="manual_format feeds the repo's manual"):
        userfile.merge(shipped, {"manual_format": shipped["manual_format"] + "!"})


def test_a_broken_user_file_falls_back_to_the_shipped_layout(shipped, monkeypatch):
    monkeypatch.setattr(buttons, "USER_PATH", FIXTURES / "broken.toml")
    monkeypatch.setattr(buttons, "_registry", None)
    assert buttons.pos("global.metronome") == (1, 4)
    assert buttons.user_error.startswith(str(FIXTURES / "broken.toml"))


def test_a_missing_user_file_is_no_change(tmp_path):
    registry = buttons.load(buttons.PATH, tmp_path / "buttons.toml")
    assert registry.overlay == {}
    assert registry.editor == userfile.EDITOR


def test_editor_settings_come_out_of_the_merge():
    merged, editor = userfile.merge({"system": {}}, {"editor": {"port": 50000}})
    assert editor == {"enabled": True, "port": 50000}
    assert "editor" not in merged


def test_the_user_path_is_only_set_inside_remote_scripts():
    assert buttons.USER_PATH is None
    library = Path("/Users/x/Music/Ableton/User Library")
    assert buttons.user_path(library / "Remote Scripts" / "BleakLoop") == library / "BleakLoop" / "buttons.toml"


def test_stamps_change_when_a_file_is_saved_created_or_deleted(tmp_path):
    shipped, user = tmp_path / "shipped.toml", tmp_path / "user.toml"
    shipped.write_text("a = 1\n")
    before = buttons.stamps(shipped, user)
    assert before[1] is None
    user.write_text("b = 22\n")
    created = buttons.stamps(shipped, user)
    assert created != before
    user.write_text("b = 333\n")
    assert buttons.stamps(shipped, user) != created
    user.unlink()
    assert buttons.stamps(shipped, user) == before


def test_the_writer_round_trips_through_tomllib():
    import tomllib

    overlay = {
        "editor": {"enabled": False, "port": 50000},
        "system": {"track": 'Quote " back \\ slash\nnew {track} — é ✓'},
        "functions": {
            "metronome": {
                "label": "Métro",
                "show": True,
                "outcomes": {"on": "On\t{x}", "off": "Off"},
            },
            "odd key": {"refusals": {"a.b": "x"}},
        },
        "navigation_shift": {"tempo_5": {"pad": [16, 4], "does": "tempo", "value": 5}},
        "sequencer_settings": {"rate_4": {"value": 1.0, "pad": [11, 1]}},
        "fx": {"window": {"value": [[1, 2], [3, -4]]}},
    }
    text = userfile.to_toml(overlay)
    assert text.startswith("# BleakLoop's user buttons")
    assert tomllib.loads(text) == overlay


def test_prune_drops_empty_tables():
    assert userfile.prune({"global": {}, "functions": {"x": {"outcomes": {}}}, "system": {"a": "b"}}) == {
        "system": {"a": "b"}
    }


def test_an_added_tempo_button_steps_by_its_value_and_lights(shipped):
    from BleakLoop.core import session
    from BleakLoop.core.leds import GREEN, Light
    from BleakLoop.core.model import PadPress, SetTempo
    from BleakLoop.core.modes import State
    from tests.support import SNAP

    buttons.reload(buttons.PATH, FIXTURES / "new_tempo.toml")
    shift = State(shift=True)
    _, actions = session.handle(shift, PadPress(1, 2, True), SNAP)
    assert actions[0] == SetTempo(SNAP.tempo + 5)
    assert session.render(shift, SNAP)[(1, 2)] == Light(GREEN)


def test_check_buttons_takes_a_user_file():
    from tools import check_buttons

    assert check_buttons.main(["--user", str(FIXTURES / "moved_pad.toml")]) == 0
    assert check_buttons.main(["--user", str(FIXTURES / "clash.toml")]) == 1
    assert check_buttons.main(["--user", str(FIXTURES / "missing.toml")]) == 1
