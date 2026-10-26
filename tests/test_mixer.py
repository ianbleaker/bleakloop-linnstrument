from dataclasses import replace

import pytest

from BleakLoop.core import engine, layout, mixer, session
from BleakLoop.core.leds import LIME, OFF, RED, WHITE, Blink, Light
from BleakLoop.core.model import (
    BeginUndoStep,
    EndUndoStep,
    EnterMode,
    PadPress,
    SetMixer,
    SetVolume,
    ShowMessage,
    Snapshot,
    StopAllClips,
    TrackView,
    YAxis,
)
from BleakLoop.core.modes import ClipSource, Glide, Lift, Mode, State, Touch
from BleakLoop.core.values import (
    CONTINUE_MS,
    GLIDE_DEAD_BAND,
    GLIDE_STEP,
    VOLUME_MAX,
)

STEP = mixer.step(8)  # one pad of travel


def test_steps():
    assert mixer.step(1) == 0.85
    assert mixer.step(8) == 0.10625


@pytest.mark.parametrize("anchor", [0.2, 0.5, 0.85])
def test_y_moves_one_step_per_pad_of_travel(anchor):
    assert mixer.y_to_volume(anchor, 64) == anchor
    assert mixer.y_to_volume(anchor, 127) == pytest.approx(anchor + STEP)
    assert mixer.y_to_volume(anchor, 1) == pytest.approx(anchor - STEP)


def test_y_is_clamped_to_live_range():
    assert mixer.y_to_volume(0.95, 127) == VOLUME_MAX
    assert mixer.y_to_volume(0.05, 0) == 0.0


@pytest.mark.parametrize(
    "volume, pad", [(0.0, 8), (0.85, 1), (0.5, 4), (1.0, 1), (mixer.step(8), 8)]
)
def test_lit_pad(volume, pad):
    assert mixer.lit_pad(volume) == pad


def test_lit_pad_tie_goes_to_the_smaller_pad():
    # Exactly halfway between pads 3 and 4 in floating point.
    middle = (mixer.step(3) + mixer.step(4)) / 2
    assert abs(middle - mixer.step(3)) == abs(middle - mixer.step(4))
    assert mixer.lit_pad(middle) == 3


# Toggle and reset


def snapshot(track_count=20):
    tracks = tuple(
        TrackView(index=i, name=f"T{i + 1}", colour=0xFF0000) for i in range(min(track_count, 13))
    )
    return Snapshot(
        is_playing=False,
        song_beats=0.0,
        tempo=120.0,
        metronome=False,
        session_view=True,
        track_count=track_count,
        scene_count=10,
        tracks=tracks,
    )


SNAP = snapshot()
MIXER = State(mixer=True)


def press(column, pad, pressed=True):
    return PadPress(column, pad, pressed)


def handle(state, event, snap=SNAP):
    return session.handle(state, event, snap)


def test_toggle_on():
    state, actions = handle(State(), press(*layout.MIXER))
    assert state.mixer
    assert actions == [SetMixer(True), ShowMessage("Mixer Mode ON")]


def test_toggle_on_drops_copy_source():
    state, _ = mixer.toggle(State(copy_source=ClipSource(1, 2, True)))
    assert state.copy_source is None


def test_toggle_off():
    state, actions = handle(MIXER, press(*layout.MIXER))
    assert not state.mixer
    assert actions == [SetMixer(False), ShowMessage("Mixer Mode OFF")]


def test_toggle_off_resets_fader_state_and_closes_undo():
    state = replace(
        MIXER,
        touches=(Touch(2, 0, 3, 0.5),),
        lifts=(Lift(3, 1, 4),),
        glides=(Glide(0, 0.5, 0.6),),
        glide_ms=5.0,
        undo_open=True,
    )
    state, actions = handle(state, press(*layout.MIXER))
    assert (state.touches, state.lifts, state.glides) == ((), (), ())
    assert (state.glide_ms, state.undo_open) == (None, False)
    assert actions == [EndUndoStep(), SetMixer(False), ShowMessage("Mixer Mode OFF")]


def test_shift_play_stop_in_mixer_stops_all():
    state, actions = handle(replace(MIXER, shift=True), press(*layout.PLAY_STOP))
    assert state.mixer
    assert actions == [StopAllClips(), ShowMessage("Stop all clips")]


@pytest.mark.parametrize("held", [{"copy": True}, {"delete": True}])
def test_mixer_pad_with_copy_or_delete_held_does_not_toggle(held):
    state, actions = handle(State(**held), press(*layout.MIXER))
    assert not state.mixer
    assert actions == []


def test_mode_pad_from_mixer_closes_undo_then_enters_linnstrument():
    state, actions = handle(replace(MIXER, undo_open=True), press(*layout.MODE_PAD))
    assert actions == [EndUndoStep(), EnterMode(Mode.LINNSTRUMENT)]
    assert state.mode is Mode.LINNSTRUMENT
    assert not state.mixer
    assert not state.undo_open


# Press and release


def touched(state=MIXER, column=2, pad=3):
    state, _ = handle(state, press(column, pad))
    return state


def lifted(column=2, pad=3, target=None):
    # A coarse press then its release, with the glide target optionally moved first.
    state = touched(column=column, pad=pad)
    if target is not None:
        state = replace(state, glides=(Glide(column - 2, target, target),))
    state, _ = handle(state, press(column, pad, pressed=False))
    return state


@pytest.mark.parametrize("pad", [1, 8])
def test_coarse_press(pad):
    state, actions = handle(MIXER, press(4, pad))
    assert actions == [BeginUndoStep(), SetVolume(2, mixer.step(pad))]
    assert state.touches == (Touch(4, 2, pad, mixer.step(pad)),)
    assert state.glides == (Glide(2, mixer.step(pad), mixer.step(pad)),)
    assert state.undo_open


def test_coarse_press_replaces_a_running_glide():
    state = replace(MIXER, glides=(Glide(0, 0.2, 0.3),), undo_open=True)
    state, actions = handle(state, press(2, 1))
    assert actions == [SetVolume(0, 0.85)]
    assert state.glides == (Glide(0, 0.85, 0.85),)


def test_begin_undo_step_once_across_columns():
    state, first = handle(MIXER, press(2, 3))
    state, second = handle(state, press(5, 6))
    assert first == [BeginUndoStep(), SetVolume(0, mixer.step(3))]
    assert second == [SetVolume(3, mixer.step(6))]


def test_release_leaves_a_lift_and_keeps_the_gesture_open():
    state = lifted(pad=3)
    assert state.touches == ()
    assert state.lifts == (Lift(2, 0, 3),)
    assert state.glides == (Glide(0, mixer.step(3), mixer.step(3)),)
    assert state.undo_open


@pytest.mark.parametrize("pad", [2, 4])
def test_adjacent_press_after_release_continues(pad):
    state = lifted(pad=3, target=0.6)
    state, actions = handle(state, press(2, pad))
    assert actions == []
    assert state.touches == (Touch(2, 0, pad, 0.6),)
    assert state.lifts == ()
    assert state.glides == (Glide(0, 0.6, 0.6),)


def test_non_adjacent_press_after_release_is_coarse():
    state = lifted(pad=3)
    state, actions = handle(state, press(2, 6))
    assert actions == [SetVolume(0, mixer.step(6))]  # the undo step is still open
    assert state.touches == (Touch(2, 0, 6, mixer.step(6)),)
    assert state.lifts == ()


def test_same_pad_press_after_release_is_coarse():
    state, actions = handle(lifted(pad=3, target=0.6), press(2, 3))
    assert actions == [SetVolume(0, mixer.step(3))]


def test_lift_in_another_column_does_not_continue():
    state, actions = handle(lifted(column=2, pad=3), press(3, 4))
    assert actions == [SetVolume(1, mixer.step(4))]
    assert state.lifts == (Lift(2, 0, 3),)


def test_second_press_in_a_held_column_moves_the_touch():
    state = replace(touched(pad=3), glides=(Glide(0, 0.6, 0.62),))
    state, actions = handle(state, press(2, 5))
    assert actions == []
    assert state.touches == (Touch(2, 0, 5, 0.62),)
    # The first pad's release is now ignored.
    assert handle(state, press(2, 3, pressed=False)) == (state, [])


def test_release_of_a_pad_not_touched_does_nothing():
    state = touched(pad=3)
    assert handle(state, press(2, 5, pressed=False)) == (state, [])
    assert handle(MIXER, press(2, 5, pressed=False)) == (MIXER, [])


def test_shift_press_is_inert():
    state = replace(MIXER, shift=True)
    assert handle(state, press(2, 3)) == (state, [])


def test_shift_press_does_not_continue():
    state = replace(lifted(pad=3), shift=True)
    assert handle(state, press(2, 2)) == (state, [])


def test_release_under_shift_still_ends_the_touch():
    state = replace(touched(pad=3), shift=True)
    state, _ = handle(state, press(2, 3, pressed=False))
    assert state.touches == ()


def test_no_track_column_is_inert():
    snap = snapshot(track_count=3)
    assert handle(MIXER, press(6, 3), snap) == (MIXER, [])


def test_pad_8_is_part_of_the_fader():
    _, actions = handle(MIXER, press(2, 8))
    assert actions == [BeginUndoStep(), SetVolume(0, mixer.step(8))]


# Y reports


def y(column, pad, value):
    return YAxis(column, pad, value)


def target(state):
    return state.glides[0].target


def test_first_report_is_a_no_op():
    state = touched(pad=3)
    assert handle(state, y(2, 3, 64)) == (state, [])


def test_report_moves_the_target_from_the_anchor():
    state, actions = handle(touched(pad=3), y(2, 3, 66))
    assert actions == []
    assert target(state) == mixer.y_to_volume(mixer.step(3), 66)


def test_continued_touch_moves_from_its_anchor():
    state, _ = handle(lifted(pad=3, target=0.6), press(2, 2))
    state, _ = handle(state, y(2, 2, 67))
    assert target(state) == mixer.y_to_volume(0.6, 67)


def test_report_never_sets_volume():
    _, actions = handle(touched(pad=3), y(2, 3, 120))
    assert actions == []


def test_report_ignored_with_mixer_off():
    state = replace(touched(pad=3), mixer=False)
    assert handle(state, y(2, 3, 120)) == (state, [])


def test_report_ignored_under_shift():
    state = replace(touched(pad=3), shift=True)
    assert handle(state, y(2, 3, 120)) == (state, [])


def test_report_ignored_without_a_touch():
    assert handle(MIXER, y(2, 3, 120)) == (MIXER, [])
    state = lifted(pad=3)
    assert handle(state, y(2, 3, 120)) == (state, [])


def test_report_from_another_row_is_ignored():
    state = touched(pad=3)
    assert handle(state, y(2, 4, 120)) == (state, [])


def test_report_within_the_glide_dead_band_is_ignored():
    state, _ = handle(touched(pad=3), y(2, 3, 100))
    nudge = handle(state, y(2, 3, 101))
    assert abs(mixer.y_to_volume(mixer.step(3), 101) - target(state)) <= GLIDE_DEAD_BAND
    assert nudge == (state, [])


def test_report_drives_the_touch_track_after_a_window_move():
    state = touched(pad=3)
    moved = replace(SNAP, tracks=tuple(replace(t, index=t.index + 5) for t in SNAP.tracks))
    state, _ = session.handle(state, y(2, 3, 120), moved)
    assert state.glides[0].track == 0


# Glide tick


def gliding(current, target, glide_ms=None, **k):
    return replace(MIXER, glides=(Glide(0, current, target),), glide_ms=glide_ms, **k)


def test_first_step_is_capped_at_one_timer_period():
    state, actions, _ = mixer.tick(gliding(0.2, 0.6), now_ms=1000.0)
    assert actions == [SetVolume(0, pytest.approx(0.2 + GLIDE_STEP))]
    assert state.glide_ms == 1000.0


def test_step_scales_with_elapsed_time():
    state, actions, _ = mixer.tick(gliding(0.6, 0.2, glide_ms=1000.0), now_ms=1030.0)
    assert actions == [SetVolume(0, pytest.approx(0.6 - GLIDE_STEP * 3))]


def test_snaps_within_the_dead_band():
    goal = 0.2 + GLIDE_STEP + GLIDE_DEAD_BAND / 2
    state, actions, _ = mixer.tick(gliding(0.2, goal), now_ms=0.0)
    assert actions == [SetVolume(0, goal)]
    assert state.glide_ms is None


def test_settled_glide_under_a_touch_emits_nothing():
    state, actions, redraw = mixer.tick(touched(pad=3), now_ms=0.0)
    assert (actions, redraw) == ([], False)
    assert state.glide_ms is None


def test_engine_tick_with_nothing_running_does_nothing():
    assert engine.tick(MIXER, now_ms=0.0) == (MIXER, [], False)


def test_redraw_only_when_lit_height_changes():
    start = mixer.step(4) + 0.01
    _, _, redraw = mixer.tick(gliding(start, 0.9), now_ms=0.0)
    assert not redraw
    edge = (mixer.step(3) + mixer.step(4)) / 2 - 0.005
    _, _, redraw = mixer.tick(gliding(edge, 0.9), now_ms=0.0)
    assert redraw


def test_lift_expires_after_the_window_then_closes_undo_once():
    state = lifted(pad=3)
    state, actions, _ = engine.tick(state, 1000.0)
    assert state.lifts == (Lift(2, 0, 3, expires_ms=1000.0 + CONTINUE_MS),)
    assert actions == []
    state, actions, _ = engine.tick(state, 1000.0 + CONTINUE_MS - 1)
    assert state.lifts and actions == []
    state, actions, _ = engine.tick(state, 1000.0 + CONTINUE_MS)
    assert state.lifts == ()
    assert state.glides == ()
    assert actions == [EndUndoStep()]
    assert engine.tick(state, 2000.0) == (state, [], False)


def test_press_after_the_window_is_coarse():
    state = lifted(pad=3, target=0.6)
    state, _, _ = engine.tick(state, 0.0)
    state, _, _ = engine.tick(state, CONTINUE_MS)
    state, actions = handle(state, press(2, 2))
    assert actions == [BeginUndoStep(), SetVolume(0, mixer.step(2))]


def test_glide_after_the_window_finishes_then_closes_undo():
    state = lifted(pad=3)
    state = replace(state, glides=(Glide(0, 0.5, 0.7),))
    ends, now = [], 0.0
    while state.glides or state.lifts:
        state, actions, _ = engine.tick(state, now)
        ends += [a for a in actions if a == EndUndoStep()]
        now += 10.0
    assert ends == [EndUndoStep()]
    assert now > CONTINUE_MS


def test_tick_stamps_press_and_lift_times():
    state = touched(pad=3)
    state, _, _ = engine.tick(state, 500.0)
    assert state.touches[0].pressed_ms == 500.0
    state, _ = handle(state, press(2, 3, pressed=False))
    assert state.lifts == (Lift(2, 0, 3, 500.0),)


def test_coarse_glide_uses_the_normal_speed():
    state, _, _ = engine.tick(touched(pad=3), 0.0)
    assert state.glides[0].pace is None


def test_continued_slide_glides_at_the_pad_pace():
    state = touched(pad=3)
    state, _, _ = engine.tick(state, 0.0)
    state, _ = handle(state, press(2, 3, pressed=False))
    state, _ = handle(state, press(2, 2))
    assert state.touches[0].previous_ms == 0.0
    state, _ = handle(state, y(2, 2, 127))
    state, actions, _ = engine.tick(state, 800.0)
    assert state.glides[0].pace == pytest.approx(STEP / 800)
    assert actions == [SetVolume(0, pytest.approx(mixer.step(3) + STEP / 80))]
    state, actions, _ = engine.tick(state, 830.0)
    assert actions == [SetVolume(0, pytest.approx(mixer.step(3) + STEP * 4 / 80))]


def test_pad_pace_is_never_faster_than_the_normal_glide():
    state = touched(pad=3)
    state, _, _ = engine.tick(state, 0.0)
    state, _ = handle(state, press(2, 3, pressed=False))
    state, _ = handle(state, press(2, 2))
    state, _, _ = engine.tick(state, 20.0)
    assert state.glides[0].pace == GLIDE_STEP / 10


def test_coarse_press_resets_the_pace():
    state = replace(MIXER, glides=(Glide(0, 0.5, 0.5, pace=0.0001),), undo_open=True)
    state, _ = handle(state, press(2, 6))
    assert state.glides == (Glide(0, mixer.step(6), mixer.step(6)),)


def test_slide_across_pads_moves_monotonically():
    # Replays the device's slide shape: each pad starts at Y 64 and climbs to 127, then a
    # release, a silent gap and the next pad's press.
    now = [0.0]
    volumes = []

    def run(state, ms):
        for _ in range(int(ms // 10)):
            state, actions, _ = engine.tick(state, now[0])
            volumes.extend(a.value for a in actions if isinstance(a, SetVolume))
            now[0] += 10.0
        return state

    state, actions = handle(MIXER, press(2, 6))
    volumes.extend(a.value for a in actions if isinstance(a, SetVolume))
    for pad in (6, 5, 4, 3):
        if pad != 6:
            state, actions = handle(state, press(2, pad))
            assert actions == []
        for value in range(64, 128, 3):
            state, _ = handle(state, y(2, pad, value))
            state = run(state, 20)
        state, _ = handle(state, y(2, pad, 127))
        state, _ = handle(state, press(2, pad, pressed=False))
        state = run(state, 300)  # the gap between pads
    assert volumes == sorted(volumes)
    assert max(b - a for a, b in zip(volumes, volumes[1:])) <= GLIDE_STEP + 1e-9
    assert volumes[-1] == pytest.approx(mixer.step(6) + 4 * STEP)


# Render


def with_volume(snap, column, volume):
    i = column - 2
    tracks = list(snap.tracks)
    tracks[i] = replace(tracks[i], volume=volume)
    return replace(snap, tracks=tuple(tracks))


@pytest.mark.parametrize("volume, top", [(0.0, 8), (0.5, 4), (0.85, 1), (1.0, 1)])
def test_fader_height(volume, top):
    frame = session.render(MIXER, with_volume(SNAP, 3, volume))
    for pad in range(1, 9):
        assert frame[(3, pad)] == (Light(RED) if pad >= top else Light(OFF))


def test_no_track_column_is_off():
    frame = session.render(MIXER, snapshot(track_count=3))
    assert all(frame[(6, pad)] == Light(OFF) for pad in range(1, 9))


def test_faders_dark_under_shift():
    frame = session.render(replace(MIXER, shift=True), with_volume(SNAP, 3, 0.85))
    assert all(frame[(c, p)] == Light(OFF) for c in layout.GRID_COLUMNS for p in range(1, 9))
    assert frame[layout.PLAY_STOP] == Light(RED)


@pytest.mark.parametrize("state, blink", [(State(), Blink.STEADY), (MIXER, Blink.FAST)])
def test_mixer_pad_light(state, blink):
    assert session.render(state, SNAP)[layout.MIXER] == Light(WHITE, blink)


def test_mixer_off_draws_the_grid():
    frame = session.render(State(), with_volume(SNAP, 2, 0.85))
    assert all(frame[(2, pad)] == Light(OFF) for pad in range(1, 8))
    assert frame[(2, 8)] == Light(LIME)  # the track switch, Arm mode
