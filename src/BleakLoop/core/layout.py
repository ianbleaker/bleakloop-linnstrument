"""Surface geometry: pad <-> device row and column roles (architecture section 5)."""

from dataclasses import dataclass

ROWS = 8
COLUMNS = 17  # column 0 is the device's hardware buttons

GRID_COLUMNS = range(2, 15)
SCENE_COLUMN = 16

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
COPY = (15, 1)
DELETE = (15, 2)
SESSION = (15, 3)
MIXER = (15, 4)
FX = (15, 5)
# Unlit and unused until Drum (15/6), Chord (15/7) and Sequencer (15/8) are designed.
RESERVED = ((15, 6), (15, 7), (15, 8))
UNMUTE_ALL = (16, 7)
STOP = (16, 8)

# FX Mode: slot N is FX_SLOTS[N - 1].
FX_SLOTS = tuple((12, pad) for pad in range(1, 9)) + tuple((13, pad) for pad in range(1, 9))
# Column 14: morph length in bars.
FX_LENGTHS = {(14, 1): 1, (14, 2): 2, (14, 3): 4, (14, 4): 8, (14, 5): 16}

# bars, in Fixed Length's cycle order
FIXED_LENGTHS = (1, 2, 4, 8)

# Shift + column 15 pads 1-4: (track step, scene step).
WINDOW_MOVES = {(15, 1): (0, -1), (15, 2): (0, 1), (15, 3): (-1, 0), (15, 4): (1, 0)}

# Shift + column 15 pads 7 and 8: BPM step.
TEMPO_STEPS = {(15, 7): 1, (15, 8): -1}


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


def move_window(window, track_step, scene_step, track_count, scene_count):
    # Never past the first track or scene, and stop once the last is in view.
    def clamp(offset, count, size):
        return min(max(offset, 0), max(0, count - size))

    return Window(
        clamp(window.track + track_step, track_count, WINDOW_TRACKS),
        clamp(window.scene + scene_step, scene_count, WINDOW_SCENES),
    )


def scroll_to_scene(window, scene, track_count, scene_count):
    # Scroll the minimum distance to keep the scene in view, then clamp as a window move does.
    offset = window.scene
    if scene < offset:
        offset = scene
    elif scene >= offset + WINDOW_SCENES:
        offset = scene - WINDOW_SCENES + 1
    return move_window(Window(window.track, offset), 0, 0, track_count, scene_count)
