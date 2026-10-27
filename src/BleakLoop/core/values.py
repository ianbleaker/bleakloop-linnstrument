"""Tuned values, by name. Each names its row in docs/architecture.md section 8."""

SPLIT_POINT = 2  # left split is column 1
RESTORE_GAP_MS = 20  # before each unload restore NRPN: the device drops the end of a burst
POLL_MS = 1000  # Linnstrument Mode re-check of Row Offset, left split Octave/Transpose, right split

FAST_BLINK_MS = 200
BLINK_TIMER_MS = 10

# Fitted on the device to Live 12's palette, so they don't look like the LED colours:
# white sits mid-palette so every grey lands on it.
TRACK_COLOUR_REFERENCES = (
    (1, (255, 86, 113)),  # red
    (2, (255, 253, 76)),  # yellow
    (3, (112, 252, 106)),  # green
    (4, (71, 255, 184)),  # cyan
    (5, (92, 139, 249)),  # blue
    (6, (184, 91, 219)),  # magenta
    (8, (207, 140, 175)),  # white
    (9, (238, 153, 105)),  # orange
    (10, (200, 240, 91)),  # lime
    (11, (225, 129, 158)),  # pink
)

TEMPO_MIN = 20
TEMPO_MAX = 999

VOLUME_ZERO_DB = 0.85
VOLUME_MAX = 1.0  # +6 dB

GLIDE_STEP = 0.018  # per 10 ms, scaled by elapsed time
GLIDE_DEAD_BAND = 0.003
CONTINUE_MS = 600

FX_DATA_KEY = "BleakLoop.fx"  # song.set_data key for the FX snapshots
FX_SCENES_DATA_KEY = "BleakLoop.fx.scenes"  # song.set_data key for the scene snapshots
FX_TOUCH_TOLERANCE = 0.005  # of a macro's range: further from the last write is a hand turn

# Firmware FXD_CALX_FULL_UNIT (4095 / 24): column c's centre is X_COLUMN_WIDTH * (c - 0.5).
X_COLUMN_WIDTH = 170.625
FADERS_DATA_KEY = "BleakLoop.faders"  # song.set_data key for the Mapped FX bindings

SEQ_BASE_NOTE = 48  # Sequencer note pads' bottom left: C2 in Live's naming (C3 = 60)
SEQ_DEFAULT_RATE = 0.25  # beats per step: 1/16
AUDITION_CHANNEL = 15  # 0-based: channel 16, outside User Firmware Mode's row channels 1-8
SLIDE_START = 0.25  # of a column: a held step's X travel that starts a slide
VELOCITY_PER_COLUMN = 16
NUDGE_PER_COLUMN = 0.125  # of a step
