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

# Buttons, from buttons.toml: one namespace per section, each button's (column, pad) by name
# and each group as {(column, pad): value}. The fixed regions above come first, because the
# registry checks no button sits on them.
GLOBAL = buttons.section("global")
GLOBAL_SHIFT = buttons.section("global-shift")
LINNSTRUMENT = buttons.section("linnstrument")
LINNSTRUMENT_SHIFT = buttons.section("linnstrument-shift")
LINNSTRUMENT_SCENES = buttons.section("linnstrument-scenes")
SEQUENCER_GLOBAL = buttons.section("sequencer-global")
SEQUENCER_GLOBAL_SHIFT = buttons.section("sequencer-global-shift")
NAVIGATION = buttons.section("navigation")
NAVIGATION_SHIFT = buttons.section("navigation-shift")
SEQUENCER_NAV = buttons.section("sequencer-nav")
SEQUENCER_NAV_SHIFT = buttons.section("sequencer-nav-shift")
VIEW = buttons.section("view")
VIEW_SHIFT = buttons.section("view-shift")
DEVICE_CLIP = buttons.section("device-clip")
SEQUENCER_GRID = buttons.section("sequencer-grid")
SEQUENCER_SETTINGS = buttons.section("sequencer-settings")
FX = buttons.section("fx")
# Read by index: slot N is FX.slots[N - 1], window scene N is FX.scene_slots[N - 1] and page
# N is SEQUENCER_SETTINGS.pages[N].
FX.slots = tuple(FX.slots)
FX.scene_slots = tuple(FX.scene_slots)
SEQUENCER_SETTINGS.pages = tuple(SEQUENCER_SETTINGS.pages)

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
