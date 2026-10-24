import pytest

from BleakLoop.core.leds import (
    BLUE,
    GREEN,
    OFF,
    ORANGE,
    RED,
    WHITE,
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


@pytest.mark.parametrize(
    "rgb, colour", [(0xFF0000, RED), (0xFFFFFF, WHITE), (0xFF8000, ORANGE), (0x0000FF, BLUE)]
)
def test_track_colour_exact(rgb, colour):
    assert track_colour(rgb) == colour


def test_track_colour_nearest():
    assert track_colour(0xEEEEEE) == WHITE


def test_track_colour_tie_goes_to_earlier_entry():
    # 0xFF4000 is 64 from both red and orange.
    assert track_colour(0xFF4000) == RED
