"""Plumbing: the ControlSurface, its elements, per-mode MIDI routing and the tick."""

import logging
import time

import Live
from ableton.v3.control_surface import (
    MIDI_CC_TYPE,
    MIDI_NOTE_TYPE,
    ControlSurface,
    ControlSurfaceSpecification,
    ElementsBase,
)

from . import device, live_actions, live_state
from .core import engine, layout, values
from .core.leds import Clock, phase_key
from .core.model import ControlCC, PadPress, YAxis
from .core.modes import Mode, State

logger = logging.getLogger(__name__)

CONTROL_CCS = range(1, 9)
Y_AXIS_CC_BASE = 64  # Y-axis CC = 64 + column (S-4)


class Elements(ElementsBase):
    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        # Pad presses: note = column, channel = device row (S-2).
        for row in range(layout.ROWS):
            for column in range(layout.COLUMNS):
                self.add_button(
                    column, f"Pad {row} {column}", channel=row, msg_type=MIDI_NOTE_TYPE
                )
        # Y-axis values in Mixer Mode: CC 64 + column on the row's channel (S-4). Every
        # column is claimed so stray Y reports outside the faders don't reach Live's tracks.
        for row in range(layout.ROWS):
            for column in range(layout.COLUMNS):
                self.add_button(
                    Y_AXIS_CC_BASE + column, f"Y {row} {column}", channel=row, msg_type=MIDI_CC_TYPE
                )
        # Note Mode control split: CC 1-8 on the control channel (S-5). Plain CC buttons:
        # encoders reset the device's toggles to 0 and Live drops their repeated values.
        for number in CONTROL_CCS:
            self.add_button(
                number, f"Control {number}", channel=values.CONTROL_CHANNEL, msg_type=MIDI_CC_TYPE
            )


class Specification(ControlSurfaceSpecification):
    elements_type = Elements
    num_tracks = 13
    num_scenes = 7
    link_session_ring_to_track_selection = False


class BleakLoop(ControlSurface):
    def __init__(self, *a, **k):
        self._state = State()
        self._driver = device.LedDriver()
        self._listeners = []
        self._setup = None  # NRPNs still to send, one per tick (S-5)
        self._started = False
        self._timer = None
        self._phase = None
        self._ring = None  # the last session highlight sent
        self._pending_clip = None  # the clip slot to show in the Detail view (S-32)
        self._pending_fresh = False
        super().__init__(*a, specification=Specification, **k)

    @staticmethod
    def _should_include_element_in_background(_):
        # Elements intercept MIDI only while listened to; listeners are per mode.
        return False

    # Lifecycle

    def update_display(self):
        super().update_display()
        if self._started:
            self._check_pending_clip()
            self._refresh()
        elif self._setup is None:
            logger.info("BleakLoop loaded")
            self._setup = [device.user_firmware_mode(False)] + device.split_setup()  # S-5
            self._send(self._setup.pop(0))
        elif self._setup:
            # One NRPN per tick: the device drops a block from the middle of a burst (#18).
            self._send(self._setup.pop(0))
        else:
            # One tick after the last NRPN: the device drops what follows it at once.
            self._started = True
            self.enter_mode(Mode.SESSION)  # S-7
            # S-92: the display tick alone would land tempo blinks up to 100 ms late.
            self._timer = Live.Base.Timer(
                callback=self._on_blink_timer, interval=values.BLINK_TIMER_MS, repeat=True
            )
            self._timer.start()

    def disconnect(self):
        if self._timer is not None:
            self._timer.stop()
            self._timer = None
        if self._state.undo_open:
            self.song.end_undo_step()
        # S-6: hand the device back for playing.
        self._send(
            device.y_axis(False)
            + device.user_firmware_mode(False)
            + self._driver.release_column_1()
        )
        self._remove_listeners()
        # After the hand-back: if this raises, the device is already playable.
        self._c_instance.set_session_highlight(-1, -1, -1, -1, False)  # S-10
        super().disconnect()

    def _on_blink_timer(self):
        try:
            if self._state.glides or self._state.lifts:
                # S-72: the fader glide; a full redraw only when a lit height changes.
                state, actions, redraw = engine.tick(self._state, time.monotonic() * 1000)
                self._state = state
                for action in actions:
                    live_actions.apply(action, self.song, self)
                if redraw:
                    self._refresh()
            transport = live_state.read_transport(self.song, Live.Application.get_application())
            key = phase_key(self._clock(transport))
            if key != self._phase:
                self._phase = key
                self._refresh()
        except Exception:
            logger.exception("blink timer failed")

    # Modes

    def enter_mode(self, mode):
        if mode is Mode.SESSION:
            self._send(device.user_firmware_mode(True))  # S-8, S-15
        else:
            self._send(device.y_axis(False) + device.user_firmware_mode(False))  # S-13, S-14
        self._listen_for(mode)
        self._update_ring(force=True)  # S-10, S-15
        self._driver.reset()  # S-94
        self._refresh()

    def set_mixer(self, on):
        # S-70: one burst, no driver reset; _handle's refresh sends only the changed pads.
        self._send(device.y_axis(on))
        self._listen_for(Mode.SESSION)

    def _listen_for(self, mode):
        self._remove_listeners()
        if mode is Mode.SESSION:
            for row in range(layout.ROWS):
                for column in range(layout.COLUMNS):
                    element = getattr(self.elements, f"pad_{row}_{column}")
                    self._add_listener(
                        element, lambda v, c=column, r=row: self._on_pad(c, r, v)
                    )
            if self._state.mixer:
                for row in range(layout.ROWS):
                    for column in range(layout.COLUMNS):
                        element = getattr(self.elements, f"y_{row}_{column}")
                        self._add_listener(
                            element, lambda v, c=column, r=row: self._on_y_axis(c, r, v)
                        )
        else:
            for number in CONTROL_CCS:
                element = getattr(self.elements, f"control_{number}")
                self._add_listener(element, lambda v, n=number: self._on_control(n, v))
        self.request_rebuild_midi_map()

    def _add_listener(self, element, fn):
        element.add_value_listener(fn)
        self._listeners.append((element, fn))

    def _remove_listeners(self):
        listeners, self._listeners = self._listeners, []
        for element, fn in listeners:
            element.remove_value_listener(fn)

    # Input

    def _on_pad(self, column, row, value):
        self._handle(PadPress(column, layout.pad_of(row), value > 0))

    def _on_y_axis(self, column, row, value):
        # Only the fader columns use Y; the rest are claimed and dropped.
        if column in layout.GRID_COLUMNS:
            self._handle(YAxis(column, layout.pad_of(row), value))

    def _on_control(self, number, value):
        self._handle(ControlCC(number, value))

    def _handle(self, event):
        state, actions = engine.handle(self._state, event, self._snapshot())
        # Store first: EnterMode renders, and must render the new mode.
        self._state = state
        follow_ups = [live_actions.apply(action, self.song, self) for action in actions]
        # Follow-up events (Capture, S-47) go to the core once; theirs are dropped, so this
        # never recurses.
        for follow_up in follow_ups:
            if follow_up is not None:
                state, more = engine.handle(self._state, follow_up, self._snapshot())
                self._state = state
                for action in more:
                    live_actions.apply(action, self.song, self)
        self._update_ring()
        self._refresh()

    # Detail view (S-32)

    def show_clip_when_ready(self, slot):
        # Polled on the display tick: Live refuses changes made inside a listener callback.
        self._pending_clip = slot
        self._pending_fresh = True

    def _check_pending_clip(self):
        slot = self._pending_clip
        if slot is None:
            return
        try:
            if slot.has_clip:
                self.song.view.detail_clip = slot.clip
                Live.Application.get_application().view.show_view("Detail/Clip")
                self._pending_clip = None
            elif not self._pending_fresh and not slot.is_triggered and not slot.is_recording:
                # The recording was cancelled: a clip landing here later mustn't take the view.
                self._pending_clip = None
            self._pending_fresh = False
        except Exception:
            # The slot's track or scene was deleted.
            logger.exception("Detail view focus failed")
            self._pending_clip = None

    # Output

    def _snapshot(self):
        return live_state.read(
            self.song,
            Live.Application.get_application(),
            self._state.window,
            scene_clips=self._state.copy,
            selected=self._state.mode is Mode.NOTE,
        )

    def _update_ring(self, force=False):
        # S-10: the ring follows the window in Session Mode and is gone in Note Mode.
        if self._state.mode is Mode.SESSION:
            window = self._state.window
            want = (window.track, window.scene, layout.WINDOW_TRACKS, layout.WINDOW_SCENES)
        else:
            want = (-1, -1, -1, -1)
        if force or want != self._ring:
            self._c_instance.set_session_highlight(*want, False)
            self._ring = want

    def _clock(self, snapshot):
        now_ms = time.monotonic() * 1000
        return Clock(beats=engine.blink_beats(snapshot, now_ms), now_ms=now_ms)

    def _refresh(self):
        snapshot = self._snapshot()
        frame = engine.render(self._state, snapshot)
        self._send(self._driver.update(frame, self._clock(snapshot)))

    def _send(self, messages):
        # Always unoptimised: optimised sends collapse LED triples and NRPNs.
        for message in messages:
            self._send_midi(message, optimized=False)
