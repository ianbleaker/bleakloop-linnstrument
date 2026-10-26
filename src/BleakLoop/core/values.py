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
