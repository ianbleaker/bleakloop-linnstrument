import pytest

from BleakLoop.core import leds
from BleakLoop.core.leds import (
    BLUE,
    CYAN,
    GREEN,
    LIME,
    MAGENTA,
    OFF,
    ORANGE,
    PINK,
    RED,
    WHITE,
    YELLOW,
    Blink,
    Clock,
    Light,
    fast_on,
    phase_key,
    resolve,
    tempo_on,
    track_colour,
)


@pytest.mark.parametrize(
    "beats, on", [(0.0, True), (0.49, True), (0.5, False), (0.99, False), (1.0, True)]
)
def test_tempo_on(beats, on):
    assert tempo_on(beats) is on


@pytest.mark.parametrize("now_ms, on", [(0, True), (200, False), (400, True)])
def test_fast_on(now_ms, on):
    assert bool(fast_on(now_ms)) is on


LIT = Clock(beats=0.0, now_ms=0)
DARK = Clock(beats=0.5, now_ms=200)


@pytest.mark.parametrize("clock", [LIT, DARK])
def test_steady_ignores_phase(clock):
    assert resolve(Light(GREEN), clock) == GREEN


def test_tempo_blink():
    light = Light(GREEN, Blink.TEMPO)
    assert resolve(light, LIT) == GREEN
    assert resolve(light, Clock(beats=0.5, now_ms=0)) == OFF


def test_fast_blink():
    light = Light(GREEN, Blink.FAST)
    assert resolve(light, LIT) == GREEN
    assert resolve(light, Clock(beats=0.0, now_ms=200)) == OFF


def test_phase_key():
    assert phase_key(LIT) == (True, True)
    assert phase_key(DARK) == (False, False)


# Live 12's track colour palette, row by row, and the device colour each was tuned to (S-89).
PALETTE = [
    # Row 1
    (0xFF94A6, PINK),
    (0xFFA529, ORANGE),
    (0xCC9927, ORANGE),
    (0xF7F47C, YELLOW),
    (0xBFFB00, LIME),
    (0x1AFF2F, GREEN),
    (0x25FFA8, CYAN),
    (0x5CFFE8, CYAN),
    (0x8BC5FF, BLUE),
    (0x5480E4, BLUE),
    (0x92A7FF, BLUE),
    (0xD86CE4, MAGENTA),
    (0xE553A0, PINK),
    (0xFFFFFF, WHITE),
    # Row 2
    (0xFF3636, RED),
    (0xF66C03, ORANGE),
    (0x99724B, ORANGE),
    (0xFFF034, YELLOW),
    (0x87FF67, GREEN),
    (0x3DC300, GREEN),
    (0x00BFAF, CYAN),
    (0x19E9FF, CYAN),
    (0x10A4EE, BLUE),
    (0x007DC0, BLUE),
    (0x886CE4, MAGENTA),
    (0xB677C6, MAGENTA),
    (0xFF39D4, MAGENTA),
    (0xD0D0D0, WHITE),
    # Row 3
    (0xE2675A, RED),
    (0xFFA374, ORANGE),
    (0xD3AD71, ORANGE),
    (0xEDFFAE, LIME),
    (0xD2E498, LIME),
    (0xBAD074, LIME),
    (0x9BC48D, GREEN),
    (0xD4FDE1, WHITE),
    (0xCDF1F8, WHITE),
    (0xB9C1E3, WHITE),
    (0xCDBBE4, WHITE),
    (0xAE98E5, MAGENTA),
    (0xE5DCE1, WHITE),
    (0xA9A9A9, WHITE),
    # Row 4
    (0xC6928B, PINK),
    (0xB78256, ORANGE),
    (0x99836A, ORANGE),
    (0xBFBA69, LIME),
    (0xA6BE00, LIME),
    (0x7DB04D, GREEN),
    (0x88C2BA, CYAN),
    (0x9BB3C4, WHITE),
    (0x85A5C2, BLUE),
    (0x8393CC, BLUE),
    (0xA595B5, WHITE),
    (0xBF9FBE, WHITE),
    (0xBC7196, PINK),
    (0x7B7B7B, WHITE),
    # Row 5
    (0xAF3333, RED),
    (0xA95131, RED),
    (0x724F41, RED),
    (0xDBC300, YELLOW),
    (0x85961F, LIME),
    (0x539F31, GREEN),
    (0x0A9C8E, CYAN),
    (0x236384, BLUE),
    (0x1A2F96, BLUE),
    (0x2F52A2, BLUE),
    (0x624BAD, MAGENTA),
    (0xA34BAD, MAGENTA),
    (0xCC2E6E, RED),
    (0x3C3C3C, WHITE),
]


@pytest.mark.parametrize("rgb, colour", PALETTE)
def test_track_colour_palette(rgb, colour):
    assert track_colour(rgb) == colour


def test_track_colour_tie_goes_to_earlier_entry(monkeypatch):
    monkeypatch.setattr(
        leds, "TRACK_COLOUR_REFERENCES", ((RED, (255, 0, 0)), (ORANGE, (255, 128, 0)))
    )
    # 0xFF4000 is 64 from both.
    assert track_colour(0xFF4000) == RED
