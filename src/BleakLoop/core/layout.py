"""Surface geometry: pad <-> device row and column roles (architecture section 5)."""

from dataclasses import dataclass

ROWS = 8
COLUMNS = 17  # column 0 is the device's hardware buttons

GRID_COLUMNS = range(2, 15)
SCENE_COLUMN = 15
NAV_COLUMN = 16

WINDOW_TRACKS = 13
WINDOW_SCENES = 6

# Session and Mixer Mode grid rows below the clip slots or faders.
MUTE_ROW = 7
SELECT_ROW = 8

# (column, pad)
PLAY_STOP = (1, 1)
RECORD = (1, 2)
CAPTURE = (1, 3)
QUANTIZE = CAPTURE  # pad 3's Shift function
METRONOME = (1, 4)
LAUNCH_QUANTIZATION = METRONOME  # pad 4's Shift function
FIXED_LENGTH = (1, 5)
UNDO = (1, 6)
MODE_PAD = (1, 7)
SCENE_PAGE = MODE_PAD  # pad 7's Shift function in Linnstrument Mode
SHIFT = (1, 8)
COPY = (NAV_COLUMN, 1)
DELETE = (NAV_COLUMN, 2)
SESSION = (NAV_COLUMN, 3)
MIXER = (NAV_COLUMN, 4)
FX = (NAV_COLUMN, 5)
# Unlit and unused until Chord (16/6) is built.
RESERVED = ((NAV_COLUMN, 6),)
SEQ = (NAV_COLUMN, 7)
DEV = (NAV_COLUMN, 8)
UNMUTE_ALL = (SCENE_COLUMN, 7)
STOP = (SCENE_COLUMN, 8)

# FX Mode: slot N is FX_SLOTS[N - 1].
FX_SLOTS = tuple((12, pad) for pad in range(1, 9)) + tuple((13, pad) for pad in range(1, 9))
# Column 14: morph length in bars.
FX_LENGTHS = {(14, 1): 1, (14, 2): 2, (14, 3): 4, (14, 4): 8, (14, 5): 16}
# FX Mode: one horizontal fader per pad row.
FX_FADER_COLUMNS = range(2, 12)

# Session split view: an 8-track window, then one horizontal fader per pad row.
SPLIT_TRACKS = 8
SPLIT_FADER_COLUMNS = range(10, 15)

# bars, in Fixed Length's cycle order
FIXED_LENGTHS = (1, 2, 4, 8)

# Shift + column 16 pads 1-4: (track step, scene step).
WINDOW_MOVES = {
    (NAV_COLUMN, 1): (0, -1),
    (NAV_COLUMN, 2): (0, 1),
    (NAV_COLUMN, 3): (-1, 0),
    (NAV_COLUMN, 4): (1, 0),
}

# Shift + column 16 pads 7 and 8: BPM step.
TEMPO_STEPS = {(NAV_COLUMN, 7): 1, (NAV_COLUMN, 8): -1}

# Sequencer Mode: steps in columns 3-10, note pads or settings in 11-14.
SEQ_STEP_COLUMNS = range(3, 11)
SEQ_NOTE_COLUMNS = range(11, 15)
# Settings view: step length in beats per rate pad.
SEQ_RATES = {(11, 1): 1.0, (11, 2): 0.5, (11, 3): 0.25, (11, 4): 0.125}
SEQ_TRIPLET = (11, 5)
# Settings view: page N is SEQ_PAGES[N], column 12 then column 13.
SEQ_PAGES = tuple((12, pad) for pad in range(1, 9)) + tuple((13, pad) for pad in range(1, 9))
SEQ_DOUBLE = (SCENE_COLUMN, 1)
SEQ_HALVE = (SCENE_COLUMN, 2)
SEQ_FOLLOW = (SCENE_COLUMN, 4)
# Up and Down sit above the view switch, in reach in both views.
SEQ_UP = (SCENE_COLUMN, 6)
SEQ_DOWN = (SCENE_COLUMN, 7)
SEQ_VIEW = (SCENE_COLUMN, 8)

# Sequencer Mode, Shift + column 16 pads 3 and 4: MIDI track step.
TRACK_STEPS = {(NAV_COLUMN, 3): -1, (NAV_COLUMN, 4): 1}

# Dev + column 16 pads 1-5: track step, device step, fader source.
DEV_TRACK_STEPS = {(NAV_COLUMN, 1): -1, (NAV_COLUMN, 2): 1}
DEV_DEVICE_STEPS = {(NAV_COLUMN, 3): -1, (NAV_COLUMN, 4): 1}
DEV_SOURCE = (NAV_COLUMN, 5)


def device_row(pad):
    if not 1 <= pad <= ROWS:
        raise ValueError(f"pad out of range: {pad}")
    return ROWS - pad


def pad_of(device_row):
    if not 0 <= device_row < ROWS:
        raise ValueError(f"device row out of range: {device_row}")
    return ROWS - device_row


@dataclass(frozen=True)
class Window:
    track: int = 0
    scene: int = 0


def move_window(window, track_step, scene_step, track_count, scene_count, width=WINDOW_TRACKS):
    # Never past the first track or scene, and stop once the last is in view.
    def clamp(offset, count, size):
        return min(max(offset, 0), max(0, count - size))

    return Window(
        clamp(window.track + track_step, track_count, width),
        clamp(window.scene + scene_step, scene_count, WINDOW_SCENES),
    )


def scroll_to_scene(window, scene, track_count, scene_count, width=WINDOW_TRACKS):
    # Scroll the minimum distance to keep the scene in view, then clamp as a window move does.
    offset = window.scene
    if scene < offset:
        offset = scene
    elif scene >= offset + WINDOW_SCENES:
        offset = scene - WINDOW_SCENES + 1
    return move_window(Window(window.track, offset), 0, 0, track_count, scene_count, width)
