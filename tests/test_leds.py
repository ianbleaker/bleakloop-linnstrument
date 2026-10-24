import pytest

from BleakLoop.core.leds import (
    GREEN,
    OFF,
    Blink,
    Clock,
    Light,
    fast_on,
    phase_key,
    resolve,
    tempo_on,
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
