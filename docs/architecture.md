# BleakLoop architecture

How BleakLoop implements `docs/spec.md`. This is the outline. Sections are marked **confirmed** (agreed with the user) or **proposed** (awaiting review). Section 9 records what the device spike and later device checks found.

## 1. Constraints

- Runs on Python 3.11, Live's embedded runtime. The folder `src/BleakLoop/` is the control-surface name and is never renamed.
- Built on an `ableton.v3` `ControlSurface`. `ableton.v3` is undocumented and ships only as `.pyc`, so BleakLoop uses as little of it as possible and only its widely used parts.
- Clean room: behaviour comes from the spec only.

## 2. Approach: hybrid (confirmed, spike passed)

BleakLoop has three layers. Each may only import from the layers below it.

| Layer | Contents | Imports Live or `ableton`? | Tested by |
| --- | --- | --- | --- |
| Plumbing | `ControlSurface` subclass, MIDI elements, MIDI map and pass-through, Live listeners, session ring highlight, timer tick | Yes | Live restart and Log.txt |
| Adapters | Read Live state into plain snapshots; carry out core actions on Live objects | Yes (thin, no decisions) | Live restart |
| Core | All behaviour: modes, modifiers, Shift layer, grid, copy rules, mixer maths, colours, blinking | **No.** Pure Python | pytest, outside Live |

The plumbing starts on v3: its elements, MIDI map handling and lifecycle. v3's behaviour components (Session, Mixer, Transport, Clipboard, Modes and the v3 modifier handling) are **not** used. Their defaults differ from the spec in exactly the places that matter (S-21–S-26, S-43, S-101–S-103, S-112), and they can't be tested outside Live.

The spike confirmed the plumbing can stay on v3. With v3's background layer excluded and no listeners attached, v3 elements pass the player's MIDI (notes, MPE, Y, pressure) through to tracks untouched. LED output doesn't use v3 elements at all: the LED driver sends raw MIDI through the control surface, which works.

## 3. The core's shape (confirmed)

The core is a state machine plus a renderer, with no side effects of its own.

- **Input:** `handle(state, event, snapshot) -> (state, actions)`.
  - `event` is a pad press or release, a Y-axis value, a Note Mode CC, or a tick.
  - `snapshot` is a plain, read-only view of the Live state the decision needs.
  - `actions` are plain values such as `FireSlot(track, scene, legato, record_length)`, `Undo()`, `SetVolume(track, value)` or `ShowMessage(text)`. The adapters carry them out.
- **Output:** `render(state, snapshot, clock) -> Frame`. A frame is the colour of every pad the current mode owns: the 8 × 16 surface in Session and Mixer Mode, column 1 in Note Mode. `clock` gives the tempo-blink and fast-blink phase.
- **Sending:** the LED driver compares each frame with the last frame sent and sends only the pads that differ, all in one pass. This gives S-93 (blinking pads switch together). Clearing the remembered frame on a mode switch gives S-94.
- **Shift layer:** S-101 and S-102 become simple. While Shift is held, `handle` looks up the Shift table and `render` draws the Shift layer. There's no per-element modifier wiring.

Snapshots are read fresh on each tick and each event. This is polling, chosen for simplicity: 91 clip slots with several properties each, plus 13 tracks, 7 scenes and transport state, a few times a second. The spike measured a full snapshot at about 0.5 ms (3 ms at worst), so polling stays. (confirmed)

## 4. Module layout (confirmed)

The core starts coarse and a module is split when it grows.

```
src/BleakLoop/
  __init__.py          create_instance
  surface.py           plumbing: ControlSurface subclass, elements, MIDI routing per mode, tick
  device.py            pure: NRPN, split setup and LED message building, LED driver (S-93)
  live_state.py        adapter: Live -> Snapshot
  live_actions.py      adapter: Action -> Live calls
  core/
    layout.py          geometry: pad <-> device row, column roles, 13 x 7 window, window movement and clamping (S-47, S-58, S-65)
    model.py           Snapshot, Action and Frame types (plain dataclasses)
    modes.py           Session / Mixer / Note, Note Mode pages, modifiers (S-7–S-16, S-100–S-108, S-112)
    controls.py        shared Session and Note Mode behaviour: undo, metronome, Play/Stop, record, Fixed Length and scene lights
    session.py         clip slots, copy and delete rules, bottom row, columns 1, 15, 16, Shift layer table (S-18–S-69)
    mixer.py           Mixer toggle, coarse steps, bands, smoothing (S-70–S-75)
    note_mode.py       column 1 controls page and scene page (S-76–S-86, S-106–S-108)
    leds.py            device colours, track colour matching, tempo and fast blink (S-87–S-91)
    values.py          every value in the register below, by name
    engine.py          handle() and render(), composing the modules above
tests/                 pytest, core only
```

`__init__.py` imports nothing from `ableton` or `Live` at module level; `create_instance` imports `surface` inside the function. This keeps `BleakLoop.core` importable by pytest outside Live. Tests run on Python 3.11 (`uvx --python 3.11 pytest`) to match Live's runtime.

## 5. Plumbing (confirmed)

- **Elements in User Firmware Mode:**
  - Pad presses: notes 0–16 on channels 1–8 (S-2).
  - Y-axis values: CC 64 + column on channels 1–8 (S-4), claimed only in Mixer Mode. Columns 2–14 (CC 66–78) become fader input; the other columns are claimed and dropped, because Y reporting is per row and their reports would otherwise reach Live's tracks.
- **Elements in Note Mode:** CC 1–8 on the control split's channel only (S-5), as plain CC buttons, never encoders. Encoders send CC 1–8 = 0 back to the device on every Note Mode entry, which resets its stored toggle values, and Live appears to drop a mapped CC that repeats the encoder's last value. Together that lost every other press (#7).
- **Routing per mode.** An element only intercepts MIDI while it has a listener, and v3's background layer listens to every element by default. So BleakLoop excludes every element from the background (`_should_include_element_in_background` returns False) and attaches listeners per mode. In Note Mode, only the eight control CCs are listened; everything else reaches Live's tracks. Confirmed by the spike.
- **LED output.** One "light pad" call sends CC 20, 21 and 22 (S-3). The LED driver in section 3 is the only caller. v3's per-element send cache isn't relied on.
- **All device output is sent unoptimised** (`_send_midi(..., optimized=False)`). Inside input callbacks Live buffers "optimized" messages and keeps only the last one per status byte and CC number. That collapses LED triples and NRPN sequences to a single message. This cost the spike several runs; it is a hard rule.
- **Device setup and mode.** On load, BleakLoop leaves User Firmware Mode, configures the control split (S-5, values in section 8), then enters Session Mode. NRPN 245 is sent on entering Session and Note Mode (S-1). On unload, it turns Y-axis reporting off, leaves User Firmware Mode and returns column 1's lights to value 0 (S-6). The device confirms every User Firmware Mode change on channel 9 about 20 ms later (S-99). Drawing doesn't need to wait for it.
- **Tick.** Two clocks. Live's display callback (a steady 100 ms) reads a snapshot, renders a frame and sends the differences. A `Live.Base.Timer` at 10 ms (measured: about 12 ms on average, 32 ms at worst) checks the blink phases and triggers an extra render when one flips, so tempo blinks land within about one timer period of the beat (S-92). Sending MIDI and reading Live state from its callback was confirmed in #3. The timer reads only the transport to check the phases; the full snapshot is read only when a frame is drawn (#4).
- **Mixer toggle (S-70).** `SetMixer(on)` sends the Y-axis CCs (S-4) and re-listens, with the Y elements only when on, in one burst with the repaint that follows. There's no LED driver reset: nothing else has touched the device's lights, so the diff is accurate and S-94 holds, and the burst stays smaller.
- **Fader glide (S-72).** `engine.tick(state, now_ms)` runs from the 10 ms timer while any glide or pending continuation exists; it also expires continuation windows and times each press, since events carry no time. During a continued slide the glide moves at the measured pad pace (section 8). It needs no snapshot and moves each volume toward its target by an amount scaled by the elapsed time. The surface redraws only when a fader's lit height changes, since the fader shows only 8 heights.
- **Follow-up events.** `live_actions.apply` may return an event, which `_handle` feeds to the core once after the action loop. The follow-up's own actions are applied, but any events they return are dropped, so this never recurses. Used by Capture (S-47): after `song.capture_and_insert_scene()` the adapter returns `SceneSelected` with the index of `song.view.selected_scene`, and the core scrolls the window the minimum distance. Confirmed on device (#10).
- **Detail-view focus (S-32) is polled on the display tick.** Live refuses changes made inside a listener callback, and polling needs no listener lifecycle. The surface holds one pending clip slot, and a new `ShowClip` replaces it. On each tick:
  - If the slot has a clip, the surface shows it and clears the pending slot.
  - On any tick after the first, if the slot has no clip and is neither triggered nor recording, the recording was cancelled. The pending slot is cleared, so a clip that lands there later doesn't take the view.
  - If reading the slot raises (its track or scene was deleted), the error is logged and the pending slot is cleared.

  `highlighted_clip_slot` is never set, because that would change the selected track and, with auto-arm, which track is armed.
- **Session ring.** `c_instance.set_session_highlight(track, scene, 13, 7, False)` draws it from the core's window state whenever the window changes and on every Session entry (S-10, S-15); `(-1, -1, -1, -1, False)` removes it on Note entry and on unload. Confirmed on device (#4). Live picks the ring's colour (green on the test machine), not BleakLoop.

## 6. Adapters: Live-specific mechanisms (proposed)

| Behaviour | Mechanism |
| --- | --- |
| Fixed Length (S-30) | `ClipSlot.fire(record_length=beats)`, with beats = N × numerator × 4 / denominator. Passed only for an empty slot on an armed track, the only case where Live starts a new recording (`fire` raises if the slot owns a clip). |
| Detail view focus (S-32) | Poll the pending slot on the display tick; set `song.view.detail_clip` and show `Detail/Clip` (section 5) |
| Auto Note Mode (S-31) | The core decides from the snapshot (track type, arm, slot state and Session Record) and emits a mode-switch action |
| Launch quantization memory (S-51) | Core state, not Live |
| Status bar messages (S-17) | `ShowMessage` action |
| Clip copy (S-22, S-23) | `ClipSlot.duplicate_clip_to`. It raises on a MIDI/audio mismatch and on group slots, so the core refuses both first, using the track's `has_midi_input` and `is_foldable`. |
| Scene copy (S-66, S-67) | Every track in `song.tracks` except group tracks, including folded group members. `live_state` reads "scene has a clip" across them only while Copy is held, when the window can't move. |
| Quantize (S-48) | `clip.quantize(Live.Song.RecordingQuantization.rec_q_sixtenth, 1.0)`. Three candidates (highlighted slot's clip, `song.view.detail_clip`, the selected track's `playing_slot_index` clip), resolved by one helper, `live_state.candidate_clip`, used by both the snapshot and the action. |
| Record pad (S-54, S-55) | Session View: toggle `song.session_record`. Arrangement View: clear `song.back_to_arranger` if set, then toggle `song.record_mode`. |
| Track volume (S-71, S-72) | Read and set `track.mixer_device.volume.value`, clamped to the parameter's `min`/`max`. A glide for a track index that no longer exists is skipped. |
| Fader gesture undo (S-72) | `song.begin_undo_step()` on the first coarse press and `song.end_undo_step()` once no touch, continuation window or glide is left, so one gesture is one undo step. The core tracks the open step (`State.undo_open`); leaving Mixer Mode and unload close it. |
| Record Clip (S-78) | `live_state` reads the selected track (`song.view.selected_track`, only if it's in `song.visible_tracks`) and every scene of its slots, plus `song.view.selected_scene`, only in Note Mode. The core searches from the highlighted scene down, wrapping. When no slot is empty, `song.create_scene(-1)` runs before `FireSlot`: actions resolve their slot when applied, so the new scene exists by then. |
| Capture MIDI (S-79) | `song.capture_midi()` with no argument, only when `song.can_capture_midi` is true; otherwise the core posts "Nothing to capture". |

## 7. Requirement map (proposed)

Each S-ID belongs to one layer. Behaviour decisions are core (the module ranges in section 4). Device messages (section 3, the NRPN parts of S-8 and S-13) and the session ring (S-10) are plumbing. Live-specific mechanisms (S-17, S-30, S-32) are adapters, with the decision in the core. Spec section 9 has no code. The plan docs track progress per S-ID.

## 8. Values

Every tuned number lives here with its reason and status. Code reads them from `core/values.py` by name and never repeats them as literals. Device protocol numbers (NRPN 245, CC 11/20/21/22, colour values) are part of the device interface and are documented in spec section 3.

| Value | Used by | Source | Status |
| --- | --- | --- | --- |
| Control split channel | S-5 | Named constant edited by the player | Default channel 1, confirmed |
| Control split setup NRPNs: 200 = 1 (split on), 202 = 2 (split point: left split is column 1), 0 = 0 (one channel), 1 = channel, 35 = 2 (CC Faders), 40–47 = 1–8 (faders send CC 1–8) | S-5 | Device protocol | Confirmed on device |
| Off colour value: 7 | S-88 | Device protocol | Confirmed; 0 also dark |
| Fast blink: about 200 ms on, 200 ms off | S-91 | Tuned | Verify on device |
| Light refresh: Live's display callback, about 100 ms | S-92 | Mechanism | Measured |
| Blink clock: `Live.Base.Timer` every 10 ms | S-90–S-92 | Mechanism | Confirmed |
| `VOLUME_ZERO_DB = 0.85`: Live volume control position for 0 dB (1.0 = +6 dB) | S-71, S-72 | Live behaviour | Confirmed |
| `VOLUME_MAX = 1.0`: top of Live's volume range (+6 dB), where fine setting stops | S-72 | Live behaviour | Confirmed |
| `GLIDE_STEP = 0.018`: fader glide, at most 1.8 % of range per 10 ms, scaled by elapsed time | S-72 | Tuned | Tune on device |
| `GLIDE_DEAD_BAND = 0.003`: Y reports moving the target less than 0.3 % of range are ignored, and a glide this close snaps to its target | S-72 | Tuned | Tune on device |
| `CONTINUE_MS = 600`: a press next to a pad released within this time continues the slide (device gaps measured 160–460 ms) | S-72 | Tuned | Tune on device |
| Slide pace: during a continued slide the glide moves one step per press-to-press period of the last pad crossed, never faster than `GLIDE_STEP` | S-72 | Derived | Tune on device |
| Track colour reference RGB per device colour | S-89 | Tuned by eye | Nominal values; tuning is #9 |

Removed, to be re-added only if the device shows a need:

| Value | Was used by | Reason removed |
| --- | --- | --- |
| Full resend 0.2 s after entering Session Mode | S-8 | Contradicts sending only changed pads; delivery is trusted until proven otherwise. |
| 1.5 s control-switch lockout after entering Session Mode | S-12 | No known cause. |
| Detail-view focus retried over 1.5 s | S-32 | Replaced by polling the pending slot on the display tick (section 5). |
| Relaunch timer to end Fixed Length recordings | S-30 | Live's `ClipSlot.fire(record_length=…)` records a fixed length natively, including from a stopped transport and with quantization None (spike). |
| "Start Play first" refusal | S-29 | Not needed: Fixed Length works from a stopped transport (spike). |

## 9. Device check results

### Spike

Run on branch `spike/device-checks` (never merged) against a LinnStrument 128 and Live 12.4.7.

| Check | Result |
| --- | --- |
| 1. Note Mode pass-through | Pass. Notes, MPE, Y and pressure reach tracks; column 1 CCs reach BleakLoop on channel 1. |
| 2. LED output | Pass with raw sends, once sent unoptimised (section 5). Off is value 7; 0 is also dark. BleakLoop's colours show in the Note Mode control split (S-86). |
| 3. Tick rate | Display callback: about 100 ms, steady. `Live.Base.Timer` at 10 ms: about 12 ms average, 32 ms worst. Song-time listener: about 13 ms while playing. |
| 4. Fixed Length | Pass: exactly one bar from a stopped transport, while playing, and with quantization None. |
| 5. Unload | Before the change, the device went blank and unplayable. Now hands the device back (S-6): playable, the split stays, and column 1 returns to the device's own colours. |
| 6. Snapshot cost | About 0.5 ms average, 3 ms worst. Polling stays. |
| 7. Mixer feel | Jumpy without smoothing: a slide gives only 4–10 Y reports, 10–30 steps apart, and every touch first reports 64. Smoothing needed; ignore the first report. 0.85 = 0 dB confirmed. Superseded by the #5 event log below: Y is dense and relative, and pads don't overlap. |
| 8. LED throughput | A full-grid flip leaves Live in under 1 ms but ripples visibly on the device, which applies changes one at a time (S-93 reworded). |

Also found:

- **Pad orientation** matches S-2 for both presses and lights: channel 1 and CC 21 = 0 are the nearest row.
- **Control split pads are toggles** (S-5, S-76): each press sends one CC, alternating 127 and 0, and a release sends nothing (firmware 2.3.4, `ls_faders.ino`; confirmed on device in #7). The spike's "127 on press, 0 on release" was a misreading.
- **Column 0 is the hardware panel.** BleakLoop ignores it (S-11 removed, S-113).
- **The split setup can be sent in one go.** Pacing (one NRPN per tick) was a workaround for the optimised-send fault and isn't needed: a burst changed the split point at once.

### #4 device checks

Run on a LinnStrument 128 and Live 12 against Session Mode play and navigate (#4). Every mechanism below passed and is safe for later plans to build on.

| Mechanism | Result |
| --- | --- |
| Session ring: `c_instance.set_session_highlight` | Pass. Draws, follows window moves and is removed by `(-1, -1, -1, -1, False)`, including on unload. v3 draws no ring of its own. |
| Status bar: v3 `ControlSurface.show_message` | Pass. Messages show as written, including the en dash. |
| Legato clip launch: `ClipSlot.fire(force_legato=True)` | Pass. Undocumented in the LOM, but accepted. |
| Legato scene launch: `Scene.fire(force_legato=...)` | Pass. |
| Launch quantization: `song.clip_trigger_quantization = Live.Song.Quantization.values[n]`, read back with `int(...)` | Pass. Names in `session.QUANTIZATION_NAMES` match Live's dropdown. |
| Track and scene stops: `Track.stop_all_clips()`, `Song.stop_all_clips()` | Pass. Both stop at the next launch quantization mark, like Live's own stop buttons. Kept on purpose. |
| Exclusive arm: disarm the others in `song.tracks`, then set `track.arm` | Pass, including with auto-arm on (the selected track can stay red, S-43). Group tracks are only selected. |
| Track list: `song.visible_tracks` | Pass. Folded group members are skipped, and unfolding shifts the columns. |
| Track colours: nearest nominal reference | Pass, roughly. Tuning is #9. |
| Polling cost with a full 13 × 7 snapshot | No lag or blink drift. The 10 ms blink timer reads only the transport (`live_state.read_transport`); the full snapshot is read only when a frame is drawn. |

Also found:

- **Precautions, not observed failures:** `live_state` reads `arm` and `implicit_arm` only when `can_be_armed` is true, because Live is expected to raise on arm state for unarmable tracks such as groups. `ArmExclusive` compares tracks with `!=`, not `is`, because `song.tracks` and `song.visible_tracks` may return different wrappers for one track. Both passed with a folded group in the Set. Neither was tried without the guard.
- **Read the log before restarting Live.** `Log.txt` keeps earlier sessions, but the clean-room filter starts at the latest `BleakLoop loaded` marker, so a restart hides the previous session's tracebacks from it. That includes unload, which only runs when Live quits.
- **Designing device checks:**
  - **Legato** only shows with two clips that sound clearly different, quantization set to None, and the switch made mid-clip. With the defaults it looks like a normal launch.
  - **Describe the expected result, not its appearance:** Live draws the ring, and its colour isn't BleakLoop's.
  - **Ask once per check with the full list:** one restart, reported as a numbered list, worked well.

### #10 device checks

Run on a LinnStrument 128 and Live 12 against Session Mode recording, Copy and Delete (#10). Every mechanism below passed, and the filtered log showed no tracebacks.

| Mechanism | Result |
| --- | --- |
| Fixed Length in 3/4: `ClipSlot.fire(record_length=6.0)` | Pass. The clip is exactly 2 bars, and playback continues. |
| `ClipSlot.fire(force_legato=True, record_length=…)` in one call | Pass. No error, and the same result. |
| Detail-view focus by polling | Pass. The new clip shows once recording starts, not before. A recording cancelled before it starts doesn't steal the view later. |
| Auto Note Mode | Pass. MIDI tracks switch to Note Mode; audio tracks stay in Session Mode. |
| Capture: `song.capture_and_insert_scene()`, then `song.view.selected_scene` | Pass. `selected_scene` is updated when the call returns; the window and ring scroll to it. |
| Quantize: `clip.quantize(rec_q_sixtenth, 1.0)` | Pass. With nothing highlighted during a recording, the recording clip is found as a candidate. |
| Clip copy: `ClipSlot.duplicate_clip_to` | Pass, MIDI to MIDI. MIDI to audio is refused with the message. |
| Scene copy across `song.tracks` | Pass. It includes clips inside a folded group. |
| Clip and scene delete: `ClipSlot.delete_clip()`, `song.delete_scene()` | Pass. After a scene delete with the window at the bottom, the window moves up one. |
| Record pad: `song.session_record`, `song.back_to_arranger`, `song.record_mode` | Pass. In Arrangement View, one press clears Back to Arrangement and starts Arrangement Record. |
| Copy and Delete hold, hints, refusals and S-112 inert pads | Pass. Fixed Length survives a Note Mode round trip. |

Also found:

- **The Session View record light counts MIDI Arrangement Overdub** (S-54). Live's Arrangement Overdub is often left on, and then the pad blinks all the time. This is kept on purpose.
- **Group slots:** Live reports a group track's slot as having no clip. So a group slot can't be a copy source, and it stays dark when its members hold clips. Both are follow-ups.
- **Lime (value 10) looks yellow on the device** (the Capture pad). Noted for #9.

### #5 device checks

Run on a LinnStrument 128 and Live 12.4.7 against Mixer Mode (#5). The first run failed the fader feel. An event log of raw pad and Y input then showed the device behaves differently from the spike's reading, and the fader was redesigned around it. The second run passed, with some jitter left (follow-up). The filtered log showed no tracebacks in either run, including from the 10 ms timer setting volumes.

| Mechanism | Result |
| --- | --- |
| Mixer toggle: Y-axis CCs and the repaint in one burst, no LED driver reset | Pass. No missing or stale pads after a toggle. |
| Pad 5 light, Shift layer in Mixer, Note Mode round trip | Pass. |
| Coarse press: `mixer_device.volume.value = step` | Pass. Pad 1 lands at or near 0 dB; resting-finger roll moves it slightly, accepted. |
| Gesture undo: `song.begin_undo_step()` / `end_undo_step()` | Pass. One Undo reverts a whole multi-pad slide, gaps included. |
| Relative Y, continuation across pad gaps, pad-paced glide | Pass, a little jittery. Continuous, with no jumps on pad entry. |
| Setting volume from the `Live.Base.Timer` callback | Pass. No "Changes cannot be triggered by notifications". |

Device facts from the event log (one slow-slide session):

- **A slide never overlaps pads.** The old pad's release comes first, then 160–460 ms of silence, then the next pad's press.
- **Y is relative to the touch point.** Every press reports 64 first, after the note-on. Y swings to 127 or 0 over about half a pad and then stays there until the release (170–650 ms of saturation).
- **Y is dense:** a report every 10–20 ms, 1–3 units apart. That isn't the spike's 4–10 reports per slide.
- **A still finger rolls.** Y went from 64 to about 85 within 100 ms of a press, and drifted further over seconds.

### #6 device checks

Run on a LinnStrument 128 and Live 12 against Note Mode column 1 (#6). Every mechanism below passed, and the filtered log showed no tracebacks.

| Mechanism | Result |
| --- | --- |
| Record Clip: search from `song.view.selected_scene`, `ClipSlot.fire(record_length=…)`, Detail view | Pass. Records into the next empty slot, Fixed Length applies, and Note Mode stays on. |
| Record Clip, new scene: `song.create_scene(-1)` then `FireSlot` | Pass. The scene is added at the end and recording starts in it. |
| Record Clip refusals | Pass: master, group track and unarmed audio track. |
| Capture MIDI: `song.can_capture_midi`, `song.capture_midi()` | Pass. The no-argument call works: a clip with the played notes appears. |
| Pad 6: `Track.stop_all_clips()` in Session View, transport in Arrangement View | Pass, including "No selected track" with master selected. |
| Scene page: `Scene.fire()` from the Session window | Pass. Lights as S-68, a dark pad does nothing, and pad 8 returns without launching. |
| Controls page lights | Pass. Lime (pad 3) looks yellow, and green (pad 6) looks lime, as noted in #10 for #9. |
| Round trip and pass-through | Pass. Note Mode always starts on the controls page, and the instrument keeps playing. |
| Capture MIDI with nothing to capture | Pass. A second press with nothing new played posts "Nothing to capture". |

Also found:

- **Pad 4 was assigned CC 8, the same as pad 1.** Pressing pad 4 then sent Undo's CC. The firmware also links fader rows that share a CC, so sliding on pad 1 moved pad 4 (`ls_faders.ino`). Fixing the assignment on the device with Live closed worked, but it was CC 8 again after Live started. `device.split_setup()` sends NRPN 44 = 5 for that row, and the firmware applies NRPNs 40–47 to rows 0–7 in that order, so the cause is still open (follow-up).
