"""Mixer Mode: the toggle, coarse steps, relative fine control and glide smoothing."""

from dataclasses import replace

from . import layout
from .model import BeginUndoStep, EndUndoStep, SetMixer, SetVolume, ShowMessage
from .modes import Glide, Lift, Touch
from .values import (
    BLINK_TIMER_MS,
    CONTINUE_MS,
    GLIDE_DEAD_BAND,
    GLIDE_STEP,
    VOLUME_MAX,
    VOLUME_ZERO_DB,
)

# Device Y: every press reports the centre first, and the full swing either way covers
# about half a pad.
Y_CENTRE = 64
Y_PAD_TRAVEL = 63


def step(pad):
    # Pad 1 is 0 dB, down to 1/8 of the 0 dB position at pad 8.
    return VOLUME_ZERO_DB * (layout.ROWS + 1 - pad) / layout.ROWS


def y_to_volume(anchor, value):
    # Y moves the volume from the touch's anchor, one step per pad of travel.
    volume = anchor + (value - Y_CENTRE) / Y_PAD_TRAVEL * step(layout.ROWS)
    return min(max(volume, 0.0), VOLUME_MAX)


def lit_pad(volume):
    # The pad whose step is nearest; a tie goes to the smaller pad number.
    return min(range(1, layout.ROWS + 1), key=lambda pad: abs(step(pad) - volume))


def reset(state):
    # Leaving Mixer: drop fine-control state and close an open undo step.
    state = replace(state, touches=(), lifts=(), glides=(), glide_ms=None)
    if not state.undo_open:
        return state, []
    return replace(state, undo_open=False), [EndUndoStep()]


def toggle(state):
    if not state.mixer:
        state = replace(state, mixer=True, copy_source=None)
        return state, [SetMixer(True), ShowMessage("Mixer Mode ON")]
    state, actions = reset(state)
    return replace(state, mixer=False), actions + [SetMixer(False), ShowMessage("Mixer Mode OFF")]


def press(state, event, snapshot):
    touch = _find(state.touches, event.column)
    if not event.pressed:
        # Releases count under Shift too, so no touch latches.
        if touch is None or event.pad != touch.pad:
            return state, []
        state = _put_touch(state, event.column, None)
        state = _put_lift(state, Lift(event.column, touch.track, touch.pad, touch.pressed_ms))
        return _settle(state)
    if state.shift:
        return state, []
    # The device ends a touch between pads, so a press next to a pad just released
    # carries the gesture on from where it was.
    lift = _find(state.lifts, event.column)
    previous = touch or lift
    if previous is not None and (touch is not None or abs(lift.pad - event.pad) == 1):
        glide = _glide(state, previous.track)
        if glide is not None:
            state = _put_lift(state, None, column=event.column)
            touch = Touch(
                event.column,
                previous.track,
                event.pad,
                glide.target,
                previous_ms=previous.pressed_ms,
            )
            return _put_touch(state, event.column, touch), []
    track = _track(event.column, snapshot)
    if track is None:
        return state, []
    # The coarse press sets the step at once.
    volume = step(event.pad)
    state = _put_lift(state, None, column=event.column)
    state = _put_touch(state, event.column, Touch(event.column, track.index, event.pad, volume))
    state = _put_glide(state, Glide(track.index, volume, volume))
    actions = [SetVolume(track.index, volume)]
    if not state.undo_open:
        state = replace(state, undo_open=True)
        actions.insert(0, BeginUndoStep())
    return state, actions


def y_axis(state, event):
    # A Y report moves the touch's glide target; only the tick moves the volume.
    touch = _find(state.touches, event.column)
    if not state.mixer or state.shift or touch is None or event.pad != touch.pad:
        return state
    glide = _glide(state, touch.track)
    target = y_to_volume(touch.anchor, event.value)
    if glide is None or abs(target - glide.target) <= GLIDE_DEAD_BAND:
        return state
    return _put_glide(state, replace(glide, target=target))


def tick(state, now_ms):
    # On the 10 ms timer, each glide moves toward its target at a speed set by the
    # elapsed time, so timer jitter doesn't change it. Returns whether a lit height changed.
    state = _stamp_presses(state, now_ms)
    elapsed = BLINK_TIMER_MS if state.glide_ms is None else now_ms - state.glide_ms
    glides, actions, redraw = [], [], False
    for glide in state.glides:
        if glide.current != glide.target:
            if glide.pace is None:
                limit = GLIDE_STEP * elapsed / 10
            else:
                limit = glide.pace * elapsed
            distance = glide.target - glide.current
            if abs(distance) - limit <= GLIDE_DEAD_BAND:
                current = glide.target
            else:
                current = glide.current + (limit if distance > 0 else -limit)
            redraw = redraw or lit_pad(current) != lit_pad(glide.current)
            actions.append(SetVolume(glide.track, current))
            glide = replace(glide, current=current)
        glides.append(glide)
    moving = any(g.current != g.target for g in glides)
    lifts = tuple(
        replace(lift, expires_ms=now_ms + CONTINUE_MS) if lift.expires_ms is None else lift
        for lift in state.lifts
        if lift.expires_ms is None or now_ms < lift.expires_ms
    )
    state = replace(
        state, glides=tuple(glides), lifts=lifts, glide_ms=now_ms if moving else None
    )
    state, more = _settle(state)
    return state, actions + more, redraw


def _stamp_presses(state, now_ms):
    # A continued slide's glide moves one step per pad at the pace the finger crossed the
    # last one, so it keeps moving while Y is saturated and through the gap between pads.
    touches = []
    for touch in state.touches:
        if touch.pressed_ms is None:
            touch = replace(touch, pressed_ms=now_ms)
            glide = _glide(state, touch.track)
            if touch.previous_ms is not None and glide is not None:
                period = max(now_ms - touch.previous_ms, BLINK_TIMER_MS)
                pace = min(GLIDE_STEP / 10, step(layout.ROWS) / period)
                state = _put_glide(state, replace(glide, pace=pace))
        touches.append(touch)
    return replace(state, touches=tuple(touches))


def _settle(state):
    # Once no finger is down or about to land, finished glides go; when nothing is left,
    # the gesture's undo step closes.
    if state.touches or state.lifts:
        return state, []
    state = replace(state, glides=tuple(g for g in state.glides if g.current != g.target))
    if state.glides or not state.undo_open:
        return state, []
    return replace(state, undo_open=False), [EndUndoStep()]


def _track(column, snapshot):
    i = column - layout.GRID_COLUMNS[0]
    return snapshot.tracks[i] if i < len(snapshot.tracks) else None


def _find(items, column):
    return next((item for item in items if item.column == column), None)


def _put_touch(state, column, touch):
    touches = tuple(t for t in state.touches if t.column != column)
    return replace(state, touches=touches if touch is None else touches + (touch,))


def _put_lift(state, lift, column=None):
    # Replaces the column's lift, or removes the given column's when lift is None.
    column = lift.column if lift is not None else column
    lifts = tuple(item for item in state.lifts if item.column != column)
    return replace(state, lifts=lifts if lift is None else lifts + (lift,))


def _glide(state, track):
    return next((g for g in state.glides if g.track == track), None)


def _put_glide(state, glide):
    glides = tuple(g for g in state.glides if g.track != glide.track)
    return replace(state, glides=glides + (glide,))
