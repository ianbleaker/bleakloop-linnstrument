"""Surface geometry: pad <-> device row and column roles (spec section 2)."""

ROWS = 8
COLUMNS = 17  # column 0 is the device's hardware buttons

GRID_COLUMNS = range(2, 15)

# (column, pad)
METRONOME = (1, 5)
PLAY_STOP = (1, 6)
MODE_PAD = (1, 8)

# Columns that form the Note Mode control split (S-5).
NOTE_CONTROL_COLUMNS = (1,)


def device_row(pad):
    if not 1 <= pad <= ROWS:
        raise ValueError(f"pad out of range: {pad}")
    return ROWS - pad


def pad_of(device_row):
    if not 0 <= device_row < ROWS:
        raise ValueError(f"device row out of range: {device_row}")
    return ROWS - device_row
