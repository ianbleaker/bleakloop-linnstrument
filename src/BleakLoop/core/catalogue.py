"""What each function a button can run is, and which modes it runs in. Data only: no imports.

A button names its function with `does` in buttons.toml. Placing one in a section whose modes
it can't run in is a load error, except through a fallback section (see buttons.FALLBACK),
where it's simply dark in that mode.
"""

SESSION = "session"  # Session, Mixer and FX Mode, split views included
LINNSTRUMENT = "linnstrument"
SEQUENCER = "sequencer"
ANY = frozenset({SESSION, LINNSTRUMENT, SEQUENCER})
SESSION_AND_SEQUENCER = frozenset({SESSION, SEQUENCER})

MODES = {
    # Song-level: they read only the Set, so they run in every mode.
    "play_stop": ANY,
    "metronome": ANY,
    "undo": ANY,
    "redo": ANY,
    "quantize": ANY,
    "launch_quantization": ANY,
    "tempo": ANY,
    "fixed_length": ANY,
    "stop_all": ANY,
    "record": ANY,
    "capture": ANY,
    "capture_midi": ANY,
    "record_clip": ANY,
    "stop_track": ANY,
    "unmute_all": ANY,
    "unsolo_all": ANY,
    "unarm_all": ANY,
    "shift": ANY,
    # The session ring and the faders, which Linnstrument Mode doesn't show.
    "window": SESSION_AND_SEQUENCER,
    "fader_source": SESSION_AND_SEQUENCER,
    # Mode switches and holds, each mode with its own handler.
    "session": SESSION_AND_SEQUENCER,
    "mixer": SESSION_AND_SEQUENCER,
    "fx": SESSION_AND_SEQUENCER,
    "seq": SESSION_AND_SEQUENCER,
    "copy": SESSION_AND_SEQUENCER,
    "delete": SESSION_AND_SEQUENCER,
    "stop": frozenset({SESSION}),
    "linnstrument_mode": SESSION_AND_SEQUENCER,
    "back": frozenset({LINNSTRUMENT}),
    "scene_page": frozenset({LINNSTRUMENT, SEQUENCER}),
    "close_scenes": frozenset({LINNSTRUMENT, SEQUENCER}),
    "device_clip": SESSION_AND_SEQUENCER,
    "tracks": SESSION_AND_SEQUENCER,
    "devices": SESSION_AND_SEQUENCER,
    # Sequencer Mode's own.
    "double": frozenset({SEQUENCER}),
    "halve": frozenset({SEQUENCER}),
    "follow": frozenset({SEQUENCER}),
    "up": frozenset({SEQUENCER}),
    "down": frozenset({SEQUENCER}),
    "view": frozenset({SEQUENCER}),
    "rates": frozenset({SEQUENCER}),
    "triplet": frozenset({SEQUENCER}),
    "pages": frozenset({SEQUENCER}),
    # FX Mode and the split views' snapshot panel.
    "slots": frozenset({SESSION}),
    "scene_slots": frozenset({SESSION}),
    "bars": frozenset({SESSION}),
    # Unlit and unused until Chord is built.
    "reserved": frozenset({SESSION}),
}
