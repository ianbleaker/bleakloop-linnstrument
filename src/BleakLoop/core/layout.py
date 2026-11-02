"""Surface geometry: pad <-> device row and column roles (architecture section 5)."""

from dataclasses import dataclass

from . import buttons

ROWS = 8
COLUMNS = 17  # column 0 is the device's hardware buttons

# The control column, the same in every mode. Linnstrument Mode reads it through the device's
# left split, which always starts at the leftmost pad column, so it must stay leftmost.
GLOBAL_COLUMN = 1

GRID_COLUMNS = range(2, 15)
SCENE_COLUMN = 15
NAV_COLUMN = 16

WINDOW_TRACKS = 13
WINDOW_SCENES = 6

# Session and Mixer Mode grid rows below the clip slots or faders.
MUTE_ROW = 7
SELECT_ROW = 8

# FX Mode: one horizontal fader per pad row.
FX_FADER_COLUMNS = range(2, 11)

# Session split view: an 8-track window, then one horizontal fader per pad row.
SPLIT_TRACKS = 8
SPLIT_FADER_COLUMNS = range(10, 15)

# Sequencer Mode: steps in columns 3-10, note pads or settings in 11-14.
SEQ_STEP_COLUMNS = range(3, 11)
SEQ_NOTE_COLUMNS = range(11, 15)

# bars, in Fixed Length's cycle order
FIXED_LENGTHS = (1, 2, 4, 8)

# Buttons: (column, pad), from buttons.toml. The fixed regions above come first, because the
# registry checks no button sits on them.
PLAY_STOP = buttons.pos("global.play_stop")
RECORD = buttons.pos("global.record")
CAPTURE = buttons.pos("global.capture")
QUANTIZE = buttons.pos("global.quantize")
METRONOME = buttons.pos("global.metronome")
LAUNCH_QUANTIZATION = buttons.pos("global.launch_quantization")
FIXED_LENGTH = buttons.pos("global.fixed_length")
UNDO = buttons.pos("global.undo")
MODE_PAD = buttons.pos("global.mode")
SCENE_PAGE = buttons.pos("global.scene_page")  # Linnstrument Mode
SHIFT = buttons.pos("global.shift")
SESSION = buttons.pos("nav.session")
MIXER = buttons.pos("nav.mixer")
FX = buttons.pos("nav.fx")
FADER_SOURCE = buttons.pos("nav.fader_source")
# Unlit and unused until Chord is built.
RESERVED = (buttons.pos("nav.reserved"),)
SEQ = buttons.pos("nav.seq")
DELETE = buttons.pos("nav.delete")
COPY = buttons.pos("nav.copy")
DEVICE_CLIP = buttons.pos("nav.device_clip")
UNMUTE_ALL = buttons.pos("view.unmute_all")
STOP = buttons.pos("view.stop")

# FX Mode: slot N is FX_SLOTS[N - 1].
FX_SLOTS = tuple(buttons.group("fx.slots"))
# FX Mode: scene N in the window's snapshot is FX_SCENE_SLOTS[N - 1].
FX_SCENE_SLOTS = tuple(buttons.group("fx.scene_slots"))
# Morph length in bars.
FX_LENGTHS = buttons.group("fx.bars")

# Shift + column 16, in every mode but Linnstrument Mode: (track step, scene step).
WINDOW_MOVES = buttons.group("nav.window")
# Shift + column 16: BPM step.
TEMPO_STEPS = buttons.group("nav.tempo")

# Settings view: step length in beats per rate pad.
SEQ_RATES = buttons.group("seq.rates")
SEQ_TRIPLET = buttons.pos("seq.triplet")
# Settings view: page N is SEQ_PAGES[N].
SEQ_PAGES = tuple(buttons.group("seq.pages"))
SEQ_DOUBLE = buttons.pos("seq.double")
SEQ_HALVE = buttons.pos("seq.halve")
SEQ_FOLLOW = buttons.pos("seq.follow")
SEQ_UP = buttons.pos("seq.up")
SEQ_DOWN = buttons.pos("seq.down")
SEQ_VIEW = buttons.pos("seq.view")

# Device/Clip + column 16: track step, device step.
DEVICE_CLIP_TRACK_STEPS = buttons.group("device_clip.tracks")
DEVICE_CLIP_DEVICE_STEPS = buttons.group("device_clip.devices")

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
