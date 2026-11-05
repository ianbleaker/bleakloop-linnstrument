"""buttons.toml and the code agree: a moved button works, and every message is used and defined."""

import ast
from dataclasses import replace
from pathlib import Path

import pytest

from BleakLoop.core import buttons, layout, session
from BleakLoop.core.leds import OFF, WHITE, Light
from BleakLoop.core.model import PadPress, ShowMessage, Undo
from BleakLoop.core.modes import State
from tests.support import SNAP

SRC = Path(__file__).parents[1] / "src" / "BleakLoop"

# Calls whose function is picked at run time, by the expression that picks it.
OWNERS = {
    "_owner(scene)": {"slots", "scene_slots"},
    "_owner(event.scene)": {"slots", "scene_slots"},
    "owner": {"slots", "scene_slots"},
    "_split_owner(state)": {"session", "mixer"},
    "_direction(step)": {"up", "down"},
    "function": {"rates", "triplet"},
}


def test_a_moved_button_works_and_lights_on_its_new_pad(tmp_path, monkeypatch):
    # Undo takes Fixed Length's pad, and Fixed Length leaves the Global column.
    text = buttons.PATH.read_text(encoding="utf-8")
    text = text.replace("[global.fixed_length]\npad = [1, 5]\n", "")
    text = text.replace("[global.undo]\npad = [1, 6]", "[global.undo]\npad = [1, 5]")
    path = tmp_path / "buttons.toml"
    path.write_text(text, encoding="utf-8")
    monkeypatch.setattr(layout, "GLOBAL", buttons.load(path).section("global"))
    snapshot = replace(SNAP, can_undo=True)
    pressed = session.handle(State(), PadPress(1, 5, True), snapshot)
    assert pressed == (State(), [Undo(), ShowMessage("Undo")])
    assert session.handle(State(), PadPress(1, 6, True), snapshot) == (State(), [])
    frame = session.render(State(), snapshot)
    assert frame[(1, 5)] == Light(WHITE)
    assert frame[(1, 6)] == Light(OFF)


@pytest.fixture
def shipped():
    # Puts the shipped layout back after a test reloads another file.
    yield
    buttons.reload(buttons.PATH)


def _moved_undo(tmp_path):
    text = buttons.PATH.read_text(encoding="utf-8")
    text = text.replace("[global.fixed_length]\npad = [1, 5]\n", "")
    text = text.replace("[global.undo]\npad = [1, 6]", "[global.undo]\npad = [1, 5]")
    path = tmp_path / "buttons.toml"
    path.write_text(text, encoding="utf-8")
    return path


def test_a_reload_moves_a_button_everywhere_it_is_held(tmp_path, shipped):
    buttons.reload(_moved_undo(tmp_path))
    snapshot = replace(SNAP, can_undo=True)
    pressed = session.handle(State(), PadPress(1, 5, True), snapshot)
    assert pressed == (State(), [Undo(), ShowMessage("Undo")])
    frame = session.render(State(), snapshot)
    assert frame[(1, 5)] == Light(WHITE)
    assert frame[(1, 6)] == Light(OFF)
    # Sequencer Mode's Global column falls back to the same object, so it moves too.
    assert layout.SEQUENCER_GLOBAL.at((1, 5)) == ("undo", "undo", (1, 5), None)
    assert layout.SEQUENCER_GLOBAL.at((1, 6)) is None


def test_a_failed_reload_keeps_the_current_layout(tmp_path, shipped):
    text = buttons.PATH.read_text(encoding="utf-8")
    path = tmp_path / "buttons.toml"
    path.write_text(text.replace("[global.undo]\npad = [1, 6]", "[global.undo]\npad = [1, 5]"))
    with pytest.raises(ValueError, match="taken by"):
        buttons.reload(path)
    assert layout.GLOBAL.undo == (1, 6)
    assert layout.GLOBAL.at((1, 5))[1] == "fixed_length"
    assert isinstance(layout.FX.slots, tuple) and layout.FX.slots[8] == (12, 1)


def _keys(node):
    # A message key argument: a literal, either branch of a conditional, or None.
    if isinstance(node, ast.Constant):
        return {node.value}
    if isinstance(node, ast.IfExp):
        return _keys(node.body) | _keys(node.orelse)
    raise AssertionError(f"unreadable message key: {ast.unparse(node)}")


def _used():
    messages, system = set(), set()
    for path in SRC.rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
                continue
            if not (isinstance(node.func.value, ast.Name) and node.func.value.id == "buttons"):
                continue
            kind, args = node.func.attr, node.args
            if kind == "system":
                system |= _keys(args[0])
                continue
            if kind not in ("say", "refuse"):
                continue
            first = args[0]
            owners = {first.value} if isinstance(first, ast.Constant) else OWNERS[ast.unparse(first)]
            keys = _keys(args[1]) if len(args) > 1 else {None}
            table = "refusals" if kind == "refuse" else "outcomes"
            for owner in owners:
                for key in keys:
                    messages.add((owner, "message" if key is None else table, key))
    return messages, system


def _defined():
    messages = set()
    for name in buttons._get().functions:
        entry = buttons.function(name)
        if "message" in entry:
            messages.add((name, "message", None))
        for table in ("outcomes", "refusals"):
            messages |= {(name, table, key) for key in entry.get(table, {})}
    return messages, set(buttons.systems())


def test_every_message_is_used_and_defined():
    used, used_system = _used()
    defined, defined_system = _defined()
    assert sorted(used - defined, key=str) == []
    assert sorted(defined - used, key=str) == []
    assert used_system == defined_system
