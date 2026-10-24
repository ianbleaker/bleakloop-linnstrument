"""Tuned values, by name. Each names its row in docs/architecture.md section 8."""

# Control split channel (0 = MIDI channel 1).
CONTROL_CHANNEL = 0

# Control split setup NRPNs: split point, left split is column 1.
SPLIT_POINT = 2

# Fast blink: about 200 ms on, 200 ms off.
FAST_BLINK_MS = 200

# Blink clock: Live.Base.Timer every 10 ms.
BLINK_TIMER_MS = 10
