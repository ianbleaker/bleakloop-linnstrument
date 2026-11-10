"""Every function a button can run, and what each one needs to work. Data only: no imports.

A button names its function with `does` in buttons.toml, and any function may sit on any pad of
any section. A function whose requirement isn't met is dark and does nothing there; the button
editor shows why, from [system] unavailable_<requirement> in buttons.toml.
"""

# Each requirement: the modes (modes.Mode member names) that meet it.
MET_IN = {
    "leaves_mode": frozenset({"SESSION", "SEQUENCER"}),
    "edits_surface": frozenset({"SESSION", "SEQUENCER"}),
    "clip_grid": frozenset({"SESSION"}),
    "came_from": frozenset({"LINNSTRUMENT"}),
    "scene_page": frozenset({"LINNSTRUMENT", "SEQUENCER"}),
    "sequencer": frozenset({"SEQUENCER"}),
}

# Each function's requirement, or None: it works everywhere.
REQUIREMENTS = {
    # Song-level: they read only the Set.
    "play_stop": None,
    "metronome": None,
    "undo": None,
    "redo": None,
    "quantize": None,
    "launch_quantization": None,
    "tempo": None,
    "fixed_length": None,
    "stop_all": None,
    "record": None,
    "capture": None,
    "capture_midi": None,
    "record_clip": None,
    "stop_track": None,
    "unmute_all": None,
    "unsolo_all": None,
    "unarm_all": None,
    "shift": None,
    "tracks": None,
    "devices": None,
    "device_clip": None,
    "window": None,
    # Mode switches: Linnstrument Mode is left by Back.
    "session": "leaves_mode",
    "mixer": "leaves_mode",
    "fx": "leaves_mode",
    "seq": "leaves_mode",
    "linnstrument_mode": "leaves_mode",
    # Holds and switches over the surface Linnstrument Mode gives the player.
    "copy": "edits_surface",
    "delete": "edits_surface",
    "fader_source": "edits_surface",
    # The clip grid and FX Mode's and the split views' snapshot panel.
    "stop": "clip_grid",
    "slots": "clip_grid",
    "banks": "clip_grid",
    "scene_slots": "clip_grid",
    "bars": "clip_grid",
    "reserved": "clip_grid",  # unlit and unused until Chord is built
    "back": "came_from",
    "scene_page": "scene_page",
    "close_scenes": "scene_page",
    # Sequencer Mode's own.
    "double": "sequencer",
    "halve": "sequencer",
    "follow": "sequencer",
    "up": "sequencer",
    "down": "sequencer",
    "view": "sequencer",
    "rates": "sequencer",
    "triplet": "sequencer",
    "pages": "sequencer",
}

# Each function's per-button options, by name: (default, the editor's label, its hover note or
# None). A button sets them in buttons.toml with options = { <name> = true or false }.
OPTIONS = {
    "tracks": {
        "arm": (True, "Arm the track", "Sequencer Mode always moves the arm to the selected track"),
        "rack": (True, "Give its first rack the blue hand", None),
    },
}

# Messages with no button behind them: [functions.<name>] holds their wording, but no button
# can name them with does.
MESSAGE_ONLY = frozenset({"scenes"})


def met_in(name, mode):
    # Whether a function works in a mode, by its modes.Mode member name.
    requirement = REQUIREMENTS[name]
    return requirement is None or mode in MET_IN[requirement]


def requirement_met(name, state):
    return met_in(name, state.mode.name)


def runs_in(name, modes):
    # Whether a function works in any of the modes, by name.
    return any(met_in(name, mode) for mode in modes)
