"""Surface geometry: pad <-> device row and column roles (architecture section 5)."""

from dataclasses import dataclass

ROWS = 8
COLUMNS = 17  # column 0 is the device's hardware buttons

GRID_COLUMNS = range(2, 15)
SCENE_COLUMN = 16

WINDOW_TRACKS = 13
WINDOW_SCENES = 7

# (column, pad)
UNDO = (1, 1)
COPY = (1, 2)
RECORD_CLIP = COPY  # pad 2's Note Mode function
CAPTURE = (1, 3)
QUANTIZE = CAPTURE  # pad 3's Shift function
DELETE = (1, 4)
SCENE_PAGE = DELETE  # pad 4's Note Mode function
METRONOME = (1, 5)
LAUNCH_QUANTIZATION = METRONOME  # pad 5's Shift function
PLAY_STOP = (1, 6)
RECORD = (1, 7)
MODE_PAD = (1, 8)
STOP_ALL = (15, 5)
MIXER = STOP_ALL  # the same pad: Mixer is its normal-layer function
SHIFT = (16, 8)

# bars
FIXED_LENGTH_PADS = {(15, 1): 1, (15, 2): 2, (15, 3): 4, (15, 4): 8}

# Shift + column 15 pads 1-4: (track step, scene step).
WINDOW_MOVES = {(15, 1): (0, -1), (15, 2): (0, 1), (15, 3): (-1, 0), (15, 4): (1, 0)}

TRACK_CONTROL_PADS = {(15, 6): "MUTE", (15, 7): "SOLO", (15, 8): "ARM"}

# Shift + column 15 pads 7 and 8: BPM step.
TEMPO_STEPS = {(15, 7): 1, (15, 8): -1}

NOTE_CONTROL_COLUMNS = (1,)


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
