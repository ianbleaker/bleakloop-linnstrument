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
from .core.model import PadPress, YAxis
from .core.modes import Mode, State

logger = logging.getLogger(__name__)

Y_AXIS_CC_BASE = 64  # Y-axis CC = 64 + column
NRPN_REPLY_CCS = (99, 98, 6, 38, 101, 100)


class Elements(ElementsBase):
    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        # Pad presses: note = column, channel = device row.
        for row in range(layout.ROWS):
            for column in range(layout.COLUMNS):
                self.add_button(
                    column, f"Pad {row} {column}", channel=row, msg_type=MIDI_NOTE_TYPE
                )
        # Y-axis values in Mixer Mode: CC 64 + column on the row's channel. Every
        # column is claimed so stray Y reports outside the faders don't reach Live's tracks.
        for row in range(layout.ROWS):
            for column in range(layout.COLUMNS):
                self.add_button(
                    Y_AXIS_CC_BASE + column, f"Y {row} {column}", channel=row, msg_type=MIDI_CC_TYPE
                )
        # Linnstrument Mode column 1: every note on every channel. The control channel is chosen
        # from the right split after load, and elements must exist before it.
        for channel in range(16):
            for note in range(128):
                self.add_button(
                    note, f"Control {channel} {note}", channel=channel, msg_type=MIDI_NOTE_TYPE
                )
        # Device replies to NRPN 299 queries: listened during the setup and in Linnstrument Mode.
        for number in NRPN_REPLY_CCS:
            self.add_button(number, f"Nrpn {number}", channel=0, msg_type=MIDI_CC_TYPE)


class Specification(ControlSurfaceSpecification):
    elements_type = Elements
    num_tracks = layout.WINDOW_TRACKS
    num_scenes = layout.WINDOW_SCENES
    link_session_ring_to_track_selection = False


class BleakLoop(ControlSurface):
    def __init__(self, *a, **k):
        self._state = State()
        self._driver = device.LedDriver()
        self._listeners = []
        self._reader = device.NrpnReader()
        self._saved_split = {}  # the first reply per NRPN: the player's settings
        self._reads = {}  # the latest reply per NRPN
        self._set_numbers = []  # NRPNs BleakLoop set, in setup order
        self._setup = None  # NRPNs still to send, one per tick
        self._loading = 0  # setup ticks sent: the loading rainbow's position
        self._computed = False
        self._control_channel = None  # 0-based, chosen at load
        self._note_map = None  # column 1 note -> pad, None while refused
        self._refusal = None
        self._right_split_unread = False
        self._sent = {}  # BleakLoop's last left split Octave/Transpose
        self._poll = []  # Linnstrument Mode query steps still to send
        self._pending_sets = []  # (number, value) sets from the last re-check
        self._poll_due = 0
        self._poll_wait = False
        self._started = False
        self._timer = None
        self._phase = None
        self._ring = None  # the last session highlight sent
        self._pending_clip = None  # the clip slot to show in the Detail view
        self._pending_fresh = False
        start = time.monotonic()
        super().__init__(*a, specification=Specification, **k)
        logger.info("BleakLoop elements built in %d ms", (time.monotonic() - start) * 1000)

    @staticmethod
    def _should_include_element_in_background(_):
        # Elements intercept MIDI only while listened to; listeners are per mode.
        return False

    # Lifecycle

    def update_display(self):
        super().update_display()
        if self._started:
            self._check_pending_clip()
            if self._state.mode is Mode.LINNSTRUMENT:
                self._poll_tick()
            self._refresh()
        elif self._setup is None:
            logger.info("BleakLoop loaded")
            self._listen_for_nrpn_replies()
            self.request_rebuild_midi_map()
            # Reads first, then the fixed sets: every read reply is in before the computed sets.
            # In User Firmware Mode: the note lights go dark for the loading rainbow, and leaving
            # it clears the rainbow.
            self._setup = (
                [device.user_firmware_mode(True)] + device.read_steps() + device.fixed_steps()
            )
            self._set_numbers = [number for number, _ in device.FIXED_SETTINGS]
            self._setup_step()
        elif self._setup:
            # One step per tick: the device drops a block from the middle of a burst (#18).
            self._setup_step()
        elif not self._computed:
            self._compute_settings()
        else:
            # One tick after the last NRPN: the device drops what follows it at once.
            self._started = True
            self.enter_mode(Mode.SESSION)
            if self._refusal is not None:
                self.show_message(self._refusal)
            # The display tick alone would land tempo blinks up to 100 ms late.
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
        # Hand the device back for playing, with the player's own split.
        self._send(
            device.y_axis(False)
            + device.user_firmware_mode(False)
            + self._driver.release_column_1()
        )
        # Paced: in one burst with the hand-back the device dropped the last 18 messages.
        for step in device.split_restore(self._saved_split, self._set_numbers):
            time.sleep(values.RESTORE_GAP_MS / 1000)
            self._send(step)
        self._remove_listeners()
        # After the hand-back: if this raises, the device is already playable.
        self._c_instance.set_session_highlight(-1, -1, -1, -1, False)
        super().disconnect()

    def _compute_settings(self):
        settings, channel, self._note_map, self._refusal = device.computed_settings(self._reads)
        self._control_channel = channel
        self._right_split_unread = self._refusal == device.REFUSE_RIGHT_SPLIT
        self._sent = {
            device.NRPN_OCTAVE: dict(settings)[device.NRPN_OCTAVE],
            device.NRPN_TRANSPOSE_PITCH: device.TRANSPOSE_ZERO,
            device.NRPN_TRANSPOSE_LIGHTS: device.TRANSPOSE_ZERO,
        }
        self._set_numbers += [number for number, _ in settings]
        logger.info("BleakLoop control channel %d", channel + 1)
        self._setup = device.computed_steps(settings)
        self._computed = True
        self._setup_step()

    def _setup_step(self):
        # Entering Session redraws every pad over the rainbow.
        self._send(self._setup.pop(0) + device.loading_column(self._loading))
        self._loading += 1

    def _poll_tick(self):
        # Linnstrument Mode re-check of Row Offset and the left split's Octave/Transpose, one step
        # per tick. Sets go out before the next poll starts.
        now_ms = time.monotonic() * 1000
        if self._pending_sets:
            number, value = self._pending_sets.pop(0)
            self._send(device.nrpn(number, value))
            # A set gets no reply: without this the next re-check sees the same mismatch.
            self._reads[number] = value
        elif self._poll:
            self._send(self._poll.pop(0))
            self._poll_wait = not self._poll
        elif self._poll_wait:
            # One tick after the last query: its replies are in.
            self._poll_wait = False
            self._realign()
            self._poll_due = now_ms + values.POLL_MS
        elif now_ms >= self._poll_due:
            self._poll = device.poll_steps(device.poll_numbers(self._reads))

    def _realign(self):
        was_refused = self._note_map is None
        note_map, refusal, settings, player_changed = device.realign(self._reads, self._sent)
        self._pending_sets = settings
        self._sent = {number: self._reads.get(number) for number in self._sent} | dict(settings)
        if self._right_split_unread:
            # No channel is known to be free: the controls stay off for the session.
            return
        self._note_map = note_map
        if player_changed:
            self.show_message(device.OCTAVE_RESET)
        if refusal is not None and refusal != self._refusal:
            self.show_message(refusal)
        elif refusal is None and was_refused:
            self.show_message(device.CONTROLS_ON)
        self._refusal = refusal

    def _on_blink_timer(self):
        try:
            if self._state.glides or self._state.lifts:
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
        self._poll, self._pending_sets, self._poll_wait = [], [], False
        if mode is Mode.LINNSTRUMENT:
            self._poll_due = 0  # re-check at once
        if mode is Mode.SESSION:
            self._send(device.user_firmware_mode(True))
        else:
            self._send(device.y_axis(False) + device.user_firmware_mode(False))
        self._listen_for(mode)
        self._update_ring(force=True)
        self._driver.reset()
        self._refresh()

    def set_mixer(self, on):
        # One burst, no driver reset; _handle's refresh sends only the changed pads.
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
            # All 128 notes, so column 1 never plays Live's tracks whatever Row Offset sends.
            channel = self._control_channel
            for note in range(128):
                element = getattr(self.elements, f"control_{channel}_{note}")
                self._add_listener(element, lambda v, n=note: self._on_control_note(n, v))
            self._listen_for_nrpn_replies()
        self.request_rebuild_midi_map()

    def _listen_for_nrpn_replies(self):
        for number in NRPN_REPLY_CCS:
            element = getattr(self.elements, f"nrpn_{number}")
            self._add_listener(element, lambda v, n=number: self._on_nrpn_reply(n, v))

    def _add_listener(self, element, fn):
        element.add_value_listener(fn)
        self._listeners.append((element, fn))

    def _remove_listeners(self):
        listeners, self._listeners = self._listeners, []
        for element, fn in listeners:
            element.remove_value_listener(fn)

    # Input

    def _on_nrpn_reply(self, number, value):
        reply = self._reader.feed(number, value)
        if reply is not None:
            parameter, setting = reply
            self._reads[parameter] = setting
            self._saved_split.setdefault(parameter, setting)

    def _on_pad(self, column, row, value):
        self._handle(PadPress(column, layout.pad_of(row), value > 0))

    def _on_y_axis(self, column, row, value):
        if column in layout.GRID_COLUMNS:
            self._handle(YAxis(column, layout.pad_of(row), value))

    def _on_control_note(self, note, value):
        if self._note_map is None:
            if value > 0:
                self.show_message(self._refusal)
            return
        pad = self._note_map.get(note)
        if pad is None:
            # Row Offset changed since the last re-check: drop the press and re-check now.
            self._poll_due = 0
            return
        self._handle(PadPress(1, pad, value > 0))

    def _handle(self, event):
        state, actions = engine.handle(self._state, event, self._snapshot())
        # Store first: EnterMode renders, and must render the new mode.
        self._state = state
        follow_ups = [live_actions.apply(action, self.song, self) for action in actions]
        # Follow-up events (Capture) go to the core once; theirs are dropped, so this
        # never recurses.
        for follow_up in follow_ups:
            if follow_up is not None:
                state, more = engine.handle(self._state, follow_up, self._snapshot())
                self._state = state
                for action in more:
                    live_actions.apply(action, self.song, self)
        self._update_ring()
        self._refresh()

    # Detail view

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
            selected=self._state.mode is Mode.LINNSTRUMENT,
        )

    def _update_ring(self, force=False):
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
