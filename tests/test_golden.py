"""Golden master: every pad's press and release, and every frame, in every mode and hold.

Pins today's behaviour while dispatch moves onto the function catalogue. At the default
layout, any diff is a behaviour change. Regenerate only on purpose:
GOLDEN_UPDATE=1 uvx --python 3.11 pytest@8.3.3 tests/test_golden.py
"""

import os
from dataclasses import fields, replace
from pathlib import Path

from BleakLoop.core import engine
from BleakLoop.core.model import PadPress
from tools.docs.manual import scenes
from tools.docs.manual.scenes import SCENES, Layer

PATH = Path(__file__).parent / "golden" / "dispatch.txt"

BASES = {
    "session": SCENES[Layer.SESSION],
    "split": SCENES[Layer.SPLIT],
    "split-snapshots": SCENES[Layer.SPLIT_SNAPSHOTS],
    "mixer": SCENES[Layer.MIXER],
    "mixer-split": SCENES[Layer.MIXER_SPLIT],
    "fx": SCENES[Layer.FX],
    "fx-no-bars": (replace(SCENES[Layer.FX][0], fx_length=None), SCENES[Layer.FX][1]),
    "linnstrument": scenes.LINNSTRUMENT,
    "scene-page": scenes.LINNSTRUMENT_SCENES,
    "sequencer": SCENES[Layer.SEQUENCER],
    "sequencer-settings": SCENES[Layer.SEQUENCER_SETTINGS],
    "sequencer-drums": SCENES[Layer.SEQUENCER_DRUMS],
}

HOLDS = {
    "none": {},
    "shift": {"shift": True},
    "copy": {"copy": True},
    "delete": {"delete": True},
    "stop": {"stop": True},
    "seq": {"seq_held": True},
    "device-clip": {"device_clip": True},
}


def _diff(before, after):
    changed = [
        f"{f.name}={getattr(after, f.name)!r}"
        for f in fields(before)
        if getattr(before, f.name) != getattr(after, f.name)
    ]
    return " ".join(changed)


def lines():
    out = []
    for base, (state, snapshot) in BASES.items():
        for hold, flags in HOLDS.items():
            held = replace(state, **flags)
            name = f"{base}/{hold}"
            frame = engine.render(held, snapshot)
            out.append(f"{name} frame " + " ".join(f"{k}:{v!r}" for k, v in sorted(frame.items())))
            for column in range(1, 17):
                for pad in range(1, 9):
                    for pressed in (True, False):
                        after, actions = engine.handle(held, PadPress(column, pad, pressed), snapshot)
                        if after == held and not actions:
                            continue
                        event = f"{column},{pad}{'+' if pressed else '-'}"
                        out.append(f"{name} {event} {_diff(held, after)} | {actions!r}")
    return "\n".join(out) + "\n"


def test_dispatch_matches_the_golden_master():
    text = lines()
    if os.environ.get("GOLDEN_UPDATE"):
        PATH.write_text(text, encoding="utf-8")
    assert text == PATH.read_text(encoding="utf-8")
