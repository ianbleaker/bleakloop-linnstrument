# BleakLoop architecture

How BleakLoop implements `docs/spec.md`. This is the outline. Sections are marked **confirmed** (agreed with the user) or **proposed** (awaiting review), and the spike (section 9) settles what is marked **(spike)**.

## 1. Constraints

- Runs on Python 3.11, Live's embedded runtime. The folder `src/BleakLoop/` is the control-surface name and is never renamed.
- Built on an `ableton.v3` `ControlSurface`. `ableton.v3` is undocumented and ships only as `.pyc`, so BleakLoop uses as little of it as possible and only its widely used parts.
- Clean room: behaviour comes from the spec only.

## 2. Approach: hybrid, the spike decides (confirmed)

BleakLoop has three layers. Each may only import from the layers below it.

| Layer | Contents | Imports Live or `ableton`? | Tested by |
| --- | --- | --- | --- |
| Plumbing | `ControlSurface` subclass, MIDI elements, MIDI map and pass-through, Live listeners, session ring highlight, timer tick | Yes | Live restart and Log.txt |
| Adapters | Read Live state into plain snapshots; carry out core actions on Live objects | Yes (thin, no decisions) | Live restart |
| Core | All behaviour: modes, modifiers, Shift layer, grid, copy rules, mixer maths, colours, blinking | **No.** Pure Python | pytest, outside Live |

The plumbing starts on v3: its elements, MIDI map handling and lifecycle. v3's behaviour components (Session, Mixer, Transport, Clipboard, Modes and the v3 modifier handling) are **not** used. Their defaults differ from the spec in exactly the places that matter (S-21–S-26, S-43, S-101–S-103, S-112), and they can't be tested outside Live.

The spike's first two checks decide whether the plumbing stays on v3. Check 1 is whether v3 elements can be released cleanly in Note Mode, so that playing MIDI passes through. Check 2 is whether our three-CC LED output fits on its elements. If either fights us, the plumbing drops to Live's own MIDI-map calls under a minimal v3 `ControlSurface`. The core and adapters don't change.

## 3. The core's shape (confirmed)

The core is a state machine plus a renderer, with no side effects of its own.

- **Input:** `handle(state, event, snapshot) -> (state, actions)`.
  - `event` is a pad press or release, a Y-axis value, a Note Mode CC, or a tick.
  - `snapshot` is a plain, read-only view of the Live state the decision needs.
  - `actions` are plain values such as `FireSlot(track, scene, legato, record_length)`, `Undo()`, `SetVolume(track, value)` or `ShowMessage(text)`. The adapters carry them out.
- **Output:** `render(state, snapshot, clock) -> Frame`. A frame is the colour of every pad the current mode owns: the 8 × 16 surface in Session and Mixer Mode, column 1 in Note Mode. `clock` gives the tempo-blink and fast-blink phase.
- **Sending:** the LED driver compares each frame with the last frame sent and sends only the pads that differ, all in one pass. This gives S-93 (blinking pads switch together). Clearing the remembered frame on a mode switch gives S-94.
- **Shift layer:** S-101 and S-102 become simple. While Shift is held, `handle` looks up the Shift table and `render` draws the Shift layer. There's no per-element modifier wiring.

Snapshots are read fresh on each tick and each event. This is polling, chosen for simplicity: 91 clip slots with several properties each, plus 13 tracks, 7 scenes and transport state, a few times a second. **(spike)** Measure the cost. Move to listener-driven dirty flags only if it shows. (confirmed)

## 4. Module layout (confirmed)

The core starts coarse and a module is split when it grows.

```
src/BleakLoop/
  __init__.py          create_instance
  surface.py           plumbing: ControlSurface subclass, elements, MIDI routing per mode, tick
  device.py            plumbing: NRPN and LED message building (pure functions), send helpers
  live_state.py        adapter: Live -> Snapshot
  live_actions.py      adapter: Action -> Live calls
  core/
    layout.py          geometry: pad <-> device row, column roles, 13 x 7 window, window movement and clamping (S-47, S-58, S-65)
    model.py           Snapshot, Action and Frame types (plain dataclasses)
    modes.py           Session / Mixer / Note, Note Mode pages, modifiers (S-7–S-16, S-100–S-108, S-112)
    session.py         clip slots, copy and delete rules, bottom row, columns 1, 15, 16, Shift layer table (S-18–S-69)
    mixer.py           coarse steps, bands, smoothing (S-70–S-75)
    note_mode.py       column 1 CC handling (S-76–S-86)
    leds.py            device colours, track colour matching, tempo and fast blink (S-87–S-91)
    values.py          every value in the register below, by name
    engine.py          handle() and render(), composing the modules above
tests/                 pytest, core only
```

`__init__.py` imports nothing from `ableton` or `Live` at module level; `create_instance` imports `surface` inside the function. This keeps `BleakLoop.core` importable by pytest outside Live. Tests run on Python 3.11 (`uvx --python 3.11 pytest`) to match Live's runtime.

## 5. Plumbing (proposed)

- **Elements in User Firmware Mode:**
  - Pad presses: notes 0–16 on channels 1–8 (S-2).
  - Y-axis values: CC 66–78 (columns 2–14) on channels 1–8 (S-4), claimed only in Mixer Mode.
- **Elements in Note Mode:** CC 1–8 on the control split's channel only (S-5).
- **Routing per mode.** In Note Mode, only the eight control CCs are claimed. Everything else, including whatever the v3 background normally holds, is released so it reaches Live's tracks. This is the largest risk in the design. **(spike, check 1)**
- **LED output.** One "light pad" call sends CC 20, 21 and 22 (S-3). The LED driver in section 3 is the only caller. v3's per-element send cache isn't relied on.
- **Device mode.** NRPN 245 is sent on entering Session and Note Mode (S-1). Nothing is sent on unload (S-6).
- **Tick.** Driven by Live's regular display callback. Each tick reads a snapshot, renders a frame and sends the differences. A tempo-blink flip needs no special handling as long as the tick is fast enough. **(spike, check 3)** Measure the callback rate.
- **Session ring.** Live's session highlight is set from the core's window state (S-10).

## 6. Adapters: Live-specific mechanisms (proposed)

| Behaviour | Mechanism |
| --- | --- |
| Fixed Length (S-30) | `ClipSlot.fire(record_length=beats)`, with beats = N × numerator × 4 / denominator |
| Detail view focus (S-32) | Listen for the target slot gaining a clip, then show it once |
| Auto Note Mode (S-31) | The core decides from the snapshot (track type, slot state, record and overdub flags) and emits a mode-switch action |
| Launch quantization memory (S-51) | Core state, not Live |
| Status bar messages (S-17) | `ShowMessage` action |

## 7. Requirement map (proposed)

Each S-ID belongs to one layer. Behaviour decisions are core (the module ranges in section 4). Device messages (section 3, the NRPN parts of S-8 and S-13) and the session ring (S-10) are plumbing. Live-specific mechanisms (S-17, S-30, S-32) are adapters, with the decision in the core. Spec section 9 has no code. The plan docs track progress per S-ID.

## 8. Values

Every tuned number lives here with its reason and status. Code reads them from `core/values.py` by name and never repeats them as literals. Device protocol numbers (NRPN 245, CC 11/20/21/22, colour values) are part of the device interface and are documented in spec section 3.

| Value | Used by | Source | Status |
| --- | --- | --- | --- |
| Note Mode control split main channel | S-5 | Player's device setting, a named constant edited by the player | Choose default in spike |
| Fast blink: about 200 ms on, 200 ms off | S-91 | Tuned | Verify on device |
| Light refresh: Live's display callback rate | S-92 | Mechanism | Measure in spike |
| Live volume control position for 0 dB: about 0.85 | S-71, S-72 | Live behaviour | Verify in Live |
| Fader smoothing: max step about 1.8 % of range per update | S-72 | Tuned | Verify on device |
| Fader smoothing: ignore changes under about 0.3 % of range | S-72 | Tuned | Verify on device |
| Fader smoothing: keep moving for up to 3 refresh ticks across a pad gap, slowing | S-72 | Tuned | Verify on device |
| Track colour reference RGB per device colour | S-89 | Tuned by eye | To be tuned on device |

Removed, to be re-added only if the device shows a need:

| Value | Was used by | Reason removed |
| --- | --- | --- |
| Full resend 0.2 s after entering Session Mode | S-8 | Contradicts sending only changed pads; delivery is trusted until proven otherwise. |
| 1.5 s control-switch lockout after entering Session Mode | S-12 | No known cause. |
| Detail-view focus retried over 1.5 s | S-32 | Replace with reacting to the clip appearing. |
| Relaunch timer to end Fixed Length recordings | S-30 | Live's `ClipSlot.fire(record_length=…)` records a fixed length natively. |

## 9. Spike

A throwaway control surface, on a branch and never merged, that answers these questions on the real device. Each result is written back into this document or the spec.

1. **Note Mode pass-through.** With v3 elements released, do playing notes, Y-axis and pressure on every channel reach a track, while column 1's CCs on the control channel reach BleakLoop and nowhere else?
2. **LED output on v3 elements.** Can three-CC pad lighting sit cleanly on v3 elements? Which value gives a dark pad (S-88)? Do LEDs set by CC 20–22 show in Note Mode on the CC Faders split (S-86)?
3. **Tick rate.** How often does Live call the display callback? Is it fast enough for tempo blinks at high tempos (S-92)? If not, look in the unofficial API docs for a faster timer.
4. **Fixed Length.** Does `fire(record_length=…)` record correctly from a stopped transport (S-29)? What happens with launch quantization set to None?
5. **Unload.** What does the device show after Live quits while in User Firmware Mode (S-6)?
6. **Snapshot cost.** How long does a realistic full snapshot (91 slots, 13 tracks, 7 scenes, transport) take to read?
7. **Mixer feel.** Are Y-axis values noisy enough to need smoothing (S-72)? Is about 0.85 really 0 dB (S-71)?
8. **LED throughput.** When every tempo-blinking pad flips on one tick (up to about 90 pads × 3 CCs in one burst), does the device show them all at once, with no ripple or dropped pads? This tests S-93 and the decision to drop S-8's resend.
