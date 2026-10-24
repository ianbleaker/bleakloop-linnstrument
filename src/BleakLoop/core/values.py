"""Tuned values, by name. Each names its row in docs/architecture.md section 8."""

# Control split channel (0 = MIDI channel 1).
CONTROL_CHANNEL = 0

# Control split setup NRPNs: split point, left split is column 1.
SPLIT_POINT = 2

# Fast blink: about 200 ms on, 200 ms off.
FAST_BLINK_MS = 200

# Blink clock: Live.Base.Timer every 10 ms.
BLINK_TIMER_MS = 10

# Track colour reference RGB per device colour, in S-87 order: (colour value, (r, g, b)).
TRACK_COLOUR_REFERENCES = (
    (1, (255, 0, 0)),  # red
    (2, (255, 255, 0)),  # yellow
    (3, (0, 255, 0)),  # green
    (4, (0, 255, 255)),  # cyan
    (5, (0, 0, 255)),  # blue
    (6, (255, 0, 255)),  # magenta
    (8, (255, 255, 255)),  # white
    (9, (255, 128, 0)),  # orange
    (10, (128, 255, 0)),  # lime
    (11, (255, 128, 192)),  # pink
)

# Tempo limits for Shift + column 15 pads 7 and 8 (S-62).
TEMPO_MIN = 20
TEMPO_MAX = 999
