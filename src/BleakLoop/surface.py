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
from .core.model import ControlCC, PadPress
from .core.modes import Mode, State

logger = logging.getLogger(__name__)

CONTROL_CCS = range(1, 9)


class Elements(ElementsBase):
    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        # Pad presses: note = column, channel = device row (S-2).
        for row in range(layout.ROWS):
            for column in range(layout.COLUMNS):
                self.add_button(
                    column, f"Pad {row} {column}", channel=row, msg_type=MIDI_NOTE_TYPE
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
        self._setup_sent = False
        self._started = False
        self._timer = None
        self._phase = None
        super().__init__(*a, specification=Specification, **k)

    @staticmethod
    def _should_include_element_in_background(_):
        # Elements intercept MIDI only while listened to; listeners are per mode.
        return False

    # Lifecycle

    def update_display(self):
        super().update_display()
        if self._started:
            self._refresh()
        elif not self._setup_sent:
            self._setup_sent = True
            logger.info("BleakLoop loaded")
            self._send(device.user_firmware_mode(False) + device.split_setup())  # S-5
        else:
            # One tick after the split burst: the device drops what follows it at once.
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
        # S-6: hand the device back for playing.
        self._send(
            device.y_axis(False)
            + device.user_firmware_mode(False)
            + self._driver.release_column_1()
        )
        self._remove_listeners()
        super().disconnect()

    def _on_blink_timer(self):
        try:
            key = phase_key(self._clock(self._snapshot()))
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
        self._driver.reset()  # S-94
        self._refresh()

    def _listen_for(self, mode):
        self._remove_listeners()
        if mode is Mode.SESSION:
            for row in range(layout.ROWS):
                for column in range(layout.COLUMNS):
                    element = getattr(self.elements, f"pad_{row}_{column}")
                    self._add_listener(
                        element, lambda v, c=column, r=row: self._on_pad(c, r, v)
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

    def _on_control(self, number, value):
        self._handle(ControlCC(number, value))

    def _handle(self, event):
        state, actions = engine.handle(self._state, event, self._snapshot())
        # Store first: EnterMode renders, and must render the new mode.
        self._state = state
        for action in actions:
            live_actions.apply(action, self.song, self)
        self._refresh()

    # Output

    def _snapshot(self):
        return live_state.read(self.song, Live.Application.get_application())

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
