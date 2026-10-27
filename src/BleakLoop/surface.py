"""Plumbing: the ControlSurface, its elements, per-mode MIDI routing and the tick."""

import logging
import time
from dataclasses import replace

import Live
from ableton.v3.control_surface import (
    MIDI_CC_TYPE,
    MIDI_NOTE_TYPE,
    ControlSurface,
    ControlSurfaceSpecification,
    ElementsBase,
    ScriptForwarding,
)

from . import device, live_actions, live_state
from .core import engine, faders, fx, layout, sequencer, session, values
from .core.leds import Clock, phase_key
from .core.model import PadPress, ScenesChanged, SequencerView, SlideMoved, YAxis
from .core.modes import Mode, State

logger = logging.getLogger(__name__)

Y_AXIS_CC_BASE = 64  # Y-axis CC = 64 + column
X_LSB_CC_BASE = 32  # X: MSB on CC column, LSB on CC 32 + column
CC_SLIDE_TRANSFER = 119  # value = the column a finger slid from
NRPN_REPLY_CCS = (99, 98, 6, 38, 101, 100)
# X for device row 0, column 6 is CC 6 / 38 on channel 1: the NRPN reply elements carry it.
X_ON_NRPN = (0, 6)


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
        # X values and slide transfers, listened while faders show.
        for row in range(layout.ROWS):
            for column in range(1, layout.COLUMNS):
                if (row, column) == X_ON_NRPN:
                    continue
                self.add_button(column, f"X {row} {column}", channel=row, msg_type=MIDI_CC_TYPE)
                self.add_button(
                    X_LSB_CC_BASE + column, f"Xl {row} {column}", channel=row, msg_type=MIDI_CC_TYPE
                )
            self.add_button(CC_SLIDE_TRANSFER, f"Slide {row}", channel=row, msg_type=MIDI_CC_TYPE)
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
        self._slides = device.SlideDecoder()
        self._x_rows = None  # the X and slide rows last sent; None after User Firmware Mode on
        self._x_listened = False
        self._x_reports = 0  # in the current fader gesture
        self._longest_x_ms = 0.0
        self._saved_split = {}  # the first reply per NRPN: the player's settings
        self._reads = {}  # the latest reply per NRPN
        self._set_numbers = []  # NRPNs BleakLoop set, in setup order
        self._setup = None  # NRPNs still to send, one per tick
        self._loading = 0  # setup ticks sent: the loading rainbow's position
        self._computed = False
        self._control_channel = None  # 0-based, chosen at load, moved off a right split clash
        self._rescan = False  # the next poll reads every right split channel
        self._clash = False  # the right split uses every channel: controls off
        self._note_map = None  # column 1 note -> pad, None while refused
        self._refusal = None
        self._right_split_unread = False
        self._sent = {}  # BleakLoop's last left split Octave/Transpose
        self._poll = []  # Linnstrument Mode query steps still to send
        self._polled = []  # the numbers the current poll queries
        self._repolling = False  # the map is stale until the repeat poll: drop presses
        self._pending_sets = []  # (number, value) sets from the last re-check
        self._poll_due = 0
        self._poll_wait = False
        self._started = False
        self._timer = None
        self._phase = None
        self._longest_tick_ms = 0.0  # of the running morph
        self._fx_text = None  # the stored FX snapshots as last read
        self._fx_scenes_text = None  # the stored scene snapshots as last read
        self._scenes = []  # song.scenes at the last display tick
        self._faders_text = None  # the stored Mapped FX bindings as last read
        self._ring = None  # the last session highlight sent
        self._pending_clip = None  # the clip slot to show in the Detail view
        self._pending_fresh = False
        self._selected_device = None  # the selected track's selected device, last tick
        self._seq_view = SequencerView()  # Sequencer Mode's last read target
        self._seq_notes = None  # the note count last logged
        self._longest_seq_tick_ms = 0.0
        self._translated = {}  # (row, column) -> the audition note a note pad is translated to
        self._forwarding = None  # the pad elements' own script forwarding
        self._held_note_pads = set()  # (row, column) of note pads held now
        start = time.monotonic()
        super().__init__(*a, specification=Specification, **k)
        logger.info("BleakLoop elements built in %d ms", (time.monotonic() - start) * 1000)

    @staticmethod
    def _should_include_element_in_background(_):
        # Elements intercept MIDI only while listened to; listeners are per mode.
        return False

    @property
    def core_state(self):
        # For the adapters: the faders resolve their parameters from the source in it.
        return self._state

    # Lifecycle

    def update_display(self):
        super().update_display()
        if self._started:
            self._check_pending_clip()
            self._load_fx()
            self._load_fx_scenes()
            self._follow_scenes()
            self._load_faders()
            self._follow_selected_device()
            if self._state.mode is Mode.LINNSTRUMENT:
                self._poll_tick()
            if self._state.mode is Mode.SEQUENCER:
                self._seq_sync()
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
            self._load_fx()
            self._load_fx_scenes()
            self._scenes = list(self.song.scenes)
            self._load_faders()
            self.enter_mode(Mode.SESSION)
            if self._refusal is not None:
                self.show_message(self._refusal)
            # The display tick alone would land tempo blinks up to 100 ms late.
            self._timer = Live.Base.Timer(
                callback=self._on_blink_timer, interval=values.BLINK_TIMER_MS, repeat=True
            )
            self._timer.start()

    def _follow_selected_device(self):
        # Device FX follows the blue hand, which other control surfaces may move. A click on
        # a device in Live moves it here, so the faders follow what was clicked. Only on a
        # change: a device another controller picked stays until the next click.
        try:
            device = self.song.view.selected_track.view.selected_device
        except Exception:
            logger.exception("FADERS: reading the selected device failed")
            return
        if device == self._selected_device:
            return
        self._selected_device = device
        if device is not None:
            self.song.appointed_device = device

    def _load_fx(self):
        # At load, and on every display tick: Live's Undo and Redo change the stored text
        # (each set_data is an Undo entry), so the slots follow it from wherever it came.
        text = live_state.read_fx_store(self.song)
        if text == self._fx_text:
            return
        self._fx_text = text
        slots = fx.parse(text)
        # A valid store round-trips; one with every slot cleared is valid too.
        if text and fx.dump(slots) != text:
            logger.warning("FX: stored snapshots unreadable, starting empty")
        self._state = replace(self._state, fx_slots=slots)

    def _load_fx_scenes(self):
        # As _load_fx, for the scene snapshots.
        text = live_state.read_fx_scenes_store(self.song)
        if text == self._fx_scenes_text:
            return
        self._fx_scenes_text = text
        scenes = fx.parse_scenes(text)
        if text and fx.dump_scenes(scenes) != text:
            logger.warning("FX: stored scene snapshots unreadable, starting empty")
        self._state = replace(self._state, fx_scenes=scenes)

    def _follow_scenes(self):
        # After _load_fx_scenes, so a remap works on the loaded store. Scenes compare equal
        # across reads, so a moved, deleted or inserted scene shows against the last tick's.
        scenes = list(self.song.scenes)
        if scenes == self._scenes:
            return
        old, self._scenes = self._scenes, scenes
        tracks = list(self.song.tracks)

        def duplicate(i):
            # Live's Duplicate: the scene above's clips, and at least one.
            clips = [track.clip_slots[i].has_clip for track in tracks]
            return any(clips) and clips == [track.clip_slots[i - 1].has_clip for track in tracks]

        origins = fx.scene_origins(old, scenes, duplicate)
        if origins is None:
            # A different Set: it keeps its own store.
            return
        logger.info("FX: scenes changed, %d -> %d", len(old), len(scenes))
        self._handle(ScenesChanged(*origins))

    def _load_faders(self):
        # As _load_fx: Undo and Redo of a bind or unbind change the stored text.
        text = live_state.read_fader_store(self.song)
        if text == self._faders_text:
            return
        self._faders_text = text
        bindings = faders.parse(text)
        if text and faders.dump(bindings) != text:
            logger.warning("FADERS: stored bindings unreadable, starting empty")
        self._state = replace(self._state, fader_bindings=bindings)

    def disconnect(self):
        if self._timer is not None:
            self._timer.stop()
            self._timer = None
        if self._state.undo_open:
            self.song.end_undo_step()
        if self._state.fx_undo_open:
            self.song.end_undo_step()
        if self._state.fader_undo_open:
            self.song.end_undo_step()
        if self._state.seq_undo_open:
            self.song.end_undo_step()
        self._restore_seq_arms()
        # Hand the device back for playing, with the player's own split.
        self._send(
            device.y_axis(False)
            + device.x_rows(())
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

    def _restore_seq_arms(self):
        # Unloaded in Sequencer Mode, or in Linnstrument Mode entered from it: the arms go
        # back as leaving the mode would put them. After this fails, the hand-back still runs.
        if self._state.seq_saved_arms is None:
            return
        try:
            arms = live_state.read_arms(self.song)
            for action in engine.seq_unload_arms(self._state, arms):
                live_actions.apply(action, self.song, self)
        except Exception:
            logger.exception("SEQ: restoring the arms on unload failed")

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
        # Linnstrument Mode re-check of Row Offset, the left split's Octave/Transpose and the
        # right split's channels, one step per tick. Sets go out before the next poll starts.
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
            if device.poll_missed(self._reads, self._polled, self._control_channel, self._rescan):
                # Don't build a map from stale reads: drop presses and poll again at once.
                self._poll_due, self._repolling = 0, True
                return
            # Before the re-check: a clash brings the next poll forward.
            self._poll_due = now_ms + values.POLL_MS
            self._realign()
        elif now_ms >= self._poll_due:
            self._polled = device.poll_numbers(self._reads, self._control_channel, self._rescan)
            self._poll = device.poll_steps(self._polled)

    def _realign(self):
        self._repolling = False
        was_refused = self._note_map is None
        note_map, refusal, settings, player_changed = device.realign(self._reads, self._sent)
        self._pending_sets = settings
        self._sent = {number: self._reads.get(number) for number in self._sent} | dict(settings)
        if self._right_split_unread:
            # No channel is known to be free: the controls stay off for the session.
            return
        self._recheck_channel()
        if self._clash:
            note_map, refusal = None, device.REFUSE_CHANNELS
        self._note_map = note_map
        if player_changed:
            self.show_message(device.OCTAVE_RESET)
        if refusal is not None and refusal != self._refusal:
            self.show_message(refusal)
        elif refusal is None and was_refused:
            self.show_message(device.CONTROLS_ON)
        self._refusal = refusal

    def _recheck_channel(self):
        # The right split took the control channel: rescan every channel, then move to the
        # highest free one. With none free the controls go off, and the rescans go on until
        # one frees up. The right split is never changed mid-session.
        clash = device.channel_clash(self._reads, self._control_channel)
        if not self._rescan:
            if clash:
                self._rescan, self._poll_due = True, 0
            return
        moved = False
        if clash:
            channel = device.free_channel(device.right_split_channels(self._reads))
            if channel is not None:
                self._pending_sets.append((device.NRPN_LEFT_MAIN_CHANNEL, channel + 1))
                self._control_channel, clash, moved = channel, False, True
                self.show_message(device.CONTROLS_MOVED.format(channel + 1))
        self._rescan = clash
        if moved or clash != self._clash:
            self._clash = clash
            self._listen_for(Mode.LINNSTRUMENT)

    def _on_blink_timer(self):
        start = time.monotonic()
        try:
            if self._state.glides or self._state.lifts:
                state, actions, redraw = engine.tick(self._state, time.monotonic() * 1000)
                self._state = state
                for action in actions:
                    live_actions.apply(action, self.song, self)
                if redraw:
                    self._refresh()
            transport = live_state.read_transport(self.song, Live.Application.get_application())
            if self._state.morph is not None:
                self._morph_tick(transport)
            key = phase_key(self._clock(transport))
            if self._state.mode is Mode.SEQUENCER:
                key += (self._playhead(),)
            if key != self._phase:
                self._phase = key
                self._refresh()
        except Exception:
            logger.exception("blink timer failed")
        if self._state.mode is Mode.SEQUENCER:
            tick_ms = (time.monotonic() - start) * 1000
            self._longest_seq_tick_ms = max(self._longest_seq_tick_ms, tick_ms)

    def _playhead(self):
        # Only the play position: notes are read when a frame is drawn.
        playing, position = live_state.read_position(self.song)
        return engine.seq_phase(self._state, SequencerView(is_playing=playing, position=position))

    def _seq_sync(self):
        # The arm follows Live's selected track: a click in Live sends no event.
        state, actions = engine.seq_sync(self._state, self._snapshot())
        self._state = state
        for action in actions:
            live_actions.apply(action, self.song, self)
        self._retranslate()

    def _morph_tick(self, transport):
        start = time.monotonic()
        macro_values = live_state.read_macro_values(self.song, self._state.morph)
        state, actions, redraw = engine.fx_tick(self._state, transport, macro_values)
        self._state = state
        for action in actions:
            live_actions.apply(action, self.song, self)
        if redraw:
            self._refresh()
        self._longest_tick_ms = max(self._longest_tick_ms, (time.monotonic() - start) * 1000)
        if state.morph is None:
            logger.info("FX: morph landed, longest tick %.1f ms", self._longest_tick_ms)
            self._longest_tick_ms = 0.0

    # Modes

    def enter_mode(self, mode):
        self._poll, self._pending_sets, self._poll_wait = [], [], False
        if mode is Mode.LINNSTRUMENT:
            self._poll_due = 0  # re-check at once
        if mode is not Mode.SEQUENCER and self._longest_seq_tick_ms:
            logger.info("SEQ: longest tick %.1f ms", self._longest_seq_tick_ms)
            self._longest_seq_tick_ms = 0.0
        if mode is Mode.SEQUENCER:
            self._seq_notes = None
        if mode is Mode.SESSION:
            self._send(device.user_firmware_mode(True))
            # The device turns X and slide mode off on entering User Firmware Mode.
            self._x_rows = None
        elif mode is Mode.SEQUENCER:
            # Y and X off too: Mixer Mode's Y and the faders' X may be on, and nothing claims
            # them here. CC 64 is sustain on the armed track, CC 1-16 mod wheel, volume, pan.
            self._send(
                device.user_firmware_mode(True) + device.y_axis(False) + device.x_rows(())
            )
            self._x_rows = ()
            self._slides.reset()
        else:
            self._send(device.y_axis(False) + device.x_rows(()) + device.user_firmware_mode(False))
            self._x_rows = ()
        self._listen_for(mode)
        self._sync_x_rows()
        self._update_ring(force=True)
        self._driver.reset()
        self._refresh()
        self._retranslate()

    def _retranslate(self):
        # Sequencer Mode's note pads play the armed track through note translation, and still
        # reach the script. A held pad keeps its translation until its release, which retranslates
        # it: its Note Off must leave as the note its Note On did. Linnstrument Mode doesn't listen
        # to the pads, so their releases never arrive, and a translation left there would move
        # the player's notes.
        if self._state.mode is Mode.LINNSTRUMENT:
            self._held_note_pads.clear()
        sequencing = self._state.mode is Mode.SEQUENCER
        # A row holding a step isn't translated: a slide onto its note pads mustn't sound.
        held_rows = set(engine.x_rows(self._state)) if sequencing else set()
        changed = False
        for row in range(layout.ROWS):
            for column in layout.SEQ_NOTE_COLUMNS:
                note = None
                if sequencing and row not in held_rows:
                    pad = layout.pad_of(row)
                    note = sequencer.pad_note(self._state, self._seq_view, column, pad)
                if (row, column) in self._held_note_pads:
                    continue
                if self._translated.get((row, column)) == note:
                    continue
                element = getattr(self.elements, f"pad_{row}_{column}")
                if self._forwarding is None:
                    self._forwarding = element.script_forwarding
                if note is None:
                    element.script_forwarding = self._forwarding
                    element.use_default_message()
                else:
                    element.script_forwarding = ScriptForwarding.non_consuming
                    element.set_channel(values.AUDITION_CHANNEL)
                    element.set_identifier(note)
                self._translated[(row, column)] = note
                changed = True
        if changed:
            self.request_rebuild_midi_map()

    def set_mixer(self, on):
        # One burst, no driver reset; _handle's refresh sends only the changed pads.
        self._send(device.y_axis(on))
        self._listen_for(Mode.SESSION)
        self._sync_x_rows()

    def _sync_x_rows(self):
        # X and slide mode only on the rows that want them, sent only on a change.
        mode = self._state.mode
        if mode is Mode.LINNSTRUMENT:
            return
        rows = engine.x_rows(self._state)
        if rows == self._x_rows:
            return
        self._send(device.x_rows(rows))
        self._x_rows = rows
        if mode is Mode.SESSION:
            # A Sequencer hold keeps its transfer state: its slide continues on the new row set.
            self._slides.reset()
        if self._wants_x(mode) != self._x_listened:
            self._listen_for(mode)

    def _wants_x(self, mode):
        # Sequencer Mode claims X and transfers on every row, so none reach the armed track.
        return mode is Mode.SEQUENCER or bool(engine.x_rows(self._state))

    def _listen_for(self, mode):
        self._remove_listeners()
        self._x_listened = False
        if mode in (Mode.SESSION, Mode.SEQUENCER):
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
            if self._wants_x(mode):
                self._listen_for_x()
        else:
            # All 128 notes, so column 1 never plays Live's tracks whatever Row Offset sends.
            # None while the right split uses the control channel: its notes are the player's.
            channel = self._control_channel
            if not self._clash:
                for note in range(128):
                    element = getattr(self.elements, f"control_{channel}_{note}")
                    self._add_listener(element, lambda v, n=note: self._on_control_note(n, v))
            self._listen_for_nrpn_replies()
        self.request_rebuild_midi_map()

    def _listen_for_x(self):
        self._x_listened = True
        for row in range(layout.ROWS):
            for column in range(1, layout.COLUMNS):
                if (row, column) == X_ON_NRPN:
                    msb, lsb = self.elements.nrpn_6, self.elements.nrpn_38
                else:
                    msb = getattr(self.elements, f"x_{row}_{column}")
                    lsb = getattr(self.elements, f"xl_{row}_{column}")
                self._add_listener(msb, lambda v, c=column, r=row: self._on_x(c, r, v))
                self._add_listener(
                    lsb, lambda v, c=column, r=row: self._slides.x_lsb(r, c, v)
                )
            element = getattr(self.elements, f"slide_{row}")
            self._add_listener(element, lambda v, r=row: self._on_slide_transfer(r, v))

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
        if column in layout.SEQ_NOTE_COLUMNS:
            if value:
                self._held_note_pads.add((row, column))
            else:
                self._held_note_pads.discard((row, column))
        event = self._slides.pad(row, column, value)
        if isinstance(event, SlideMoved):
            self._handle(event, engine.slide)
        elif event is not None:
            self._handle(event)

    def _on_slide_transfer(self, row, value):
        self._slides.transfer(row, value)

    def _on_x(self, column, row, value):
        # At the firmware's scan rate: no snapshot, and a refresh only on redraw.
        start = time.monotonic()
        event = self._slides.x_msb(row, column, value)
        state, actions, redraw = engine.x_axis(self._state, event)
        self._state = state
        for action in actions:
            live_actions.apply(action, self.song, self)
        if redraw:
            self._refresh()
        if self._state.fader_touches:
            self._x_reports += 1
            self._longest_x_ms = max(self._longest_x_ms, (time.monotonic() - start) * 1000)

    def _log_fader_gesture(self):
        # Once the last touch ends: the gesture's X load, for the device check.
        if self._x_reports and not self._state.fader_touches:
            logger.info(
                "FADERS: %d reports, longest %.1f ms", self._x_reports, self._longest_x_ms
            )
            self._x_reports, self._longest_x_ms = 0, 0.0

    def _on_y_axis(self, column, row, value):
        # 50-100 reports a second per finger: no snapshot or refresh, since only the 10 ms
        # tick moves a volume.
        if column in layout.GRID_COLUMNS:
            self._state = engine.y_axis(self._state, YAxis(column, layout.pad_of(row), value))

    def _on_control_note(self, note, value):
        if self._note_map is None:
            if value > 0:
                self.show_message(self._refusal)
            return
        if self._repolling and value > 0:
            # Row Offset changed type: drop the press until the repeat poll. A release goes
            # through, on the note its press was mapped from.
            return
        pad = self._note_map.get(note)
        if pad is None:
            # Row Offset changed since the last re-check: drop the press and re-check now.
            self._poll_due = 0
            return
        self._handle(PadPress(1, pad, value > 0))

    def _handle(self, event, entry=engine.handle):
        state, actions = entry(self._state, event, self._snapshot())
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
        self._sync_x_rows()
        self._log_fader_gesture()
        self._update_ring()
        self._refresh()
        self._retranslate()

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
        mode = self._state.mode
        return live_state.read(
            self.song,
            Live.Application.get_application(),
            self._state.window,
            scene_clips=self._state.copy,
            selected=mode is not Mode.SESSION,
            faders=self._state if faders.visible(self._state) else None,
            width=session.window_tracks(self._state),
            sequencer=self._read_sequencer() if mode is Mode.SEQUENCER else None,
            seq_entry=self._state.seq_held,
        )

    def _read_sequencer(self):
        # Timed, and logged once per entry and whenever the note count changes.
        start = time.monotonic()
        self._seq_view = live_state.read_sequencer(self.song)
        count = len(self._seq_view.notes)
        if count != self._seq_notes:
            self._seq_notes = count
            ms = (time.monotonic() - start) * 1000
            logger.info("SEQ: read %d notes in %.1f ms", count, ms)
        return self._seq_view

    def _update_ring(self, force=False):
        # In every mode: Live's ring shows which scenes the pads, and FX Mode's column 13, show.
        window = self._state.window
        width = session.window_tracks(self._state)
        want = (window.track, window.scene, width, layout.WINDOW_SCENES)
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
