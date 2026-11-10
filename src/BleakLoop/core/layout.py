"""Surface geometry: pad <-> device row and column roles (architecture section 5)."""

from dataclasses import dataclass

from . import buttons, views

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
FX_FADER_COLUMNS = range(2, 10)
# The FX snapshot slot count per bank: buttons.toml lists this many slots buttons, and as many
# banks buttons as FX_BANKS. A slot's global index is bank * FX_SLOTS + slot, both 0-based.
FX_SLOTS = 16
FX_BANKS = 8
FX_SNAPSHOTS = FX_SLOTS * FX_BANKS

# Session split view: an 8-track window, then one horizontal fader per pad row.
SPLIT_TRACKS = 8
SPLIT_FADER_COLUMNS = range(10, 15)

# Sequencer Mode: steps in columns 3-10, note pads or settings in 11-14.
SEQ_STEP_COLUMNS = range(3, 11)
SEQ_NOTE_COLUMNS = range(11, 15)

# bars, in Fixed Length's cycle order
FIXED_LENGTHS = (1, 2, 4, 8)

# Buttons, from buttons.toml: one namespace per section (core/views.py lists them), each
# button's (column, pad) by name and each group as {(column, pad): value} by its function.
_SECTIONS = {name: buttons.Section(name, {}, {}) for name in views.button_sections()}
SECTIONS = tuple(_SECTIONS.values())


def section(name):
    return _SECTIONS[name]


GLOBAL = _SECTIONS["global"]
GLOBAL_SHIFT = _SECTIONS["global-shift"]
LINNSTRUMENT = _SECTIONS["linnstrument"]
LINNSTRUMENT_SHIFT = _SECTIONS["linnstrument-shift"]
LINNSTRUMENT_SCENES = _SECTIONS["linnstrument-scenes"]
LINNSTRUMENT_DEVICE_CLIP = _SECTIONS["linnstrument-device-clip"]
SEQUENCER_GLOBAL = _SECTIONS["sequencer-global"]
SEQUENCER_GLOBAL_SHIFT = _SECTIONS["sequencer-global-shift"]
NAVIGATION = _SECTIONS["navigation"]
NAVIGATION_SHIFT = _SECTIONS["navigation-shift"]
SEQUENCER_NAV = _SECTIONS["sequencer-nav"]
SEQUENCER_NAV_SHIFT = _SECTIONS["sequencer-nav-shift"]
VIEW = _SECTIONS["view"]
VIEW_SHIFT = _SECTIONS["view-shift"]
DEVICE_CLIP = _SECTIONS["device-clip"]
SEQUENCER_GRID = _SECTIONS["sequencer-grid"]
SEQUENCER_SETTINGS = _SECTIONS["sequencer-settings"]
FX = _SECTIONS["fx"]


def refresh():
    # Fills every section from the current registry, in place: a reload reaches whatever holds
    # them. buttons.reload calls this again after a change.
    for section in SECTIONS:
        fresh = buttons.section(section._name)
        section._refill(fresh._own(), fresh._does)
    # Read by index: slot N is FX.slots[N - 1], window scene N is FX.scene_slots[N - 1] and
    # page N is SEQUENCER_SETTINGS.pages[N].
    FX.slots = tuple(FX.slots)
    FX.scene_slots = tuple(FX.scene_slots)
    SEQUENCER_SETTINGS.pages = tuple(SEQUENCER_SETTINGS.pages)


refresh()

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
