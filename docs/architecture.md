# BleakLoop architecture

How BleakLoop works today. This is a living document: any change to the structure, a device or Live mechanism, or a tuned value updates it in the same PR as the code.

## At a glance

```mermaid
flowchart LR
  linnstrument["LinnStrument"]
  subgraph Plumbing
    surface["surface"]
    device["device: LED driver"]
  end
  subgraph Core
    handle["handle"]
    render["render"]
  end
  subgraph Adapters
    live_state["live_state: reads"]
    live_actions["live_actions: writes"]
  end
  live["Live"]
  linnstrument -->|"pad, Y-axis, CC"| surface
  surface -->|"event"| handle
  live --> live_state
  live_state -->|"snapshot"| handle
  live_state -->|"snapshot"| render
  handle -->|"actions"| live_actions
  live_actions --> live
  render -->|"frame"| device
  device -->|"changed pads"| linnstrument
```

**Where to look:**

| To change… | Look in |
| --- | --- |
| `create_instance` | `__init__.py` |
| Plumbing: `ControlSurface` subclass, elements, MIDI routing per mode, tick | `surface.py` |
| NRPN, split setup and LED message building, LED driver | `device.py` |
| Reading Live into a `Snapshot` | `live_state.py` |
| Carrying out an `Action` as Live calls | `live_actions.py` |
| Geometry: pad <-> device row, column roles, 13 x 7 window, window movement and clamping | `core/layout.py` |
| Snapshot, Action and Frame types (plain dataclasses) | `core/model.py` |
| Session / Mixer / Linnstrument, Linnstrument Mode pages, modifiers | `core/modes.py` |
| Shared Session and Linnstrument Mode behaviour: undo, metronome, Play/Stop, record, Fixed Length and scene lights | `core/controls.py` |
| Clip slots, copy and delete rules, bottom row, columns 15, 16, Shift layer table | `core/session.py` |
| Column 1 in every mode: its controls, Shift, and Linnstrument Mode's scene page | `core/column_1.py` |
| Mixer toggle, coarse steps, bands, smoothing | `core/mixer.py` |
| Linnstrument Mode: column 1 only, handed to `column_1` | `core/linnstrument_mode.py` |
| Device colours, track colour matching, tempo and fast blink | `core/leds.py` |
| Tuned numbers: every value in section 8, by name | `core/values.py` |
| `handle()` and `render()`, composing the core modules | `core/engine.py` |
| The generated manual pad maps and architecture figures | `tools/docs/` |

Read sections 2–4 for structure, 5–7 for device and Live details, and 8 for numbers.

## 1. Constraints

- Runs on Python 3.11, Live's embedded runtime. The folder `src/BleakLoop/` is the control-surface name and is never renamed.
- Built on an `ableton.v3` `ControlSurface`. `ableton.v3` is undocumented and ships only as `.pyc`, so BleakLoop uses as little of it as possible and only its widely used parts.

## 2. Layers

BleakLoop has three layers. Each may only import from the layers below it.

```mermaid
flowchart TB
  plumbing["Plumbing: imports Live / ableton"]
  adapters["Adapters: imports Live / ableton"]
  core["Core: pure Python, tested by pytest"]
  plumbing --> adapters
  plumbing --> core
  adapters --> core
```

| Layer | Contents | Imports Live or `ableton`? | Tested by |
| --- | --- | --- | --- |
| Plumbing | `ControlSurface` subclass, MIDI elements, MIDI map and pass-through, session ring highlight, timer tick | Yes | Live restart and Log.txt |
| Adapters | Read Live state into plain snapshots; carry out core actions on Live objects | Yes (thin, no decisions) | Live restart |
| Core | All behaviour: modes, modifiers, Shift layer, grid, copy rules, mixer maths, colours, blinking | **No.** Pure Python | pytest, outside Live |

The plumbing uses v3's elements, MIDI map handling and lifecycle. v3's behaviour components (Session, Mixer, Transport, Clipboard, Modes and its modifier handling) are **not** used: their defaults differ from BleakLoop's copy, delete, arm and Shift behaviour, and they can't be tested outside Live. With v3's background layer excluded and no listeners attached, v3 elements pass the player's MIDI (notes, MPE, Y, pressure) through to tracks untouched. LED output doesn't use v3 elements: the LED driver sends raw MIDI through the control surface.

## 3. The core

The core is a state machine plus a renderer, with no side effects of its own.

- **Input:** `handle(state, event, snapshot) -> (state, actions)`.
  - `event` is a pad press or release, or a tick. A Y-axis value takes its own entry, `y_axis(state, event) -> state`.
  - `snapshot` is a plain, read-only view of the Live state the decision needs.
  - `actions` are plain values such as `FireSlot(track, scene, legato, record_length)`, `Undo()`, `SetVolume(track, value)` or `ShowMessage(text)`. The adapters carry them out.
- **Output:** `render(state, snapshot) -> Frame`. A frame is the colour of every pad the current mode owns: the 8 × 16 surface in Session and Mixer Mode, column 1 in Linnstrument Mode. A pad may blink; the LED driver resolves blinking pads with a `clock` that gives the tempo-blink and fast-blink phase.
- **Sending:** the LED driver compares each frame with the last frame sent and sends only the pads that differ, all in one pass, so blinking pads switch together. Clearing the remembered frame on a mode switch makes every pad correct after the switch.
- **Shift layer:** while Shift is held, `handle` looks up the Shift table and `render` draws the Shift layer. There's no per-element modifier wiring. Shift is column 1's pad 8 in every mode. Entering Session Mode keeps it held. Entering Linnstrument Mode clears it, because the firmware sends the release of a pad pressed in User Firmware Mode as a User Firmware note, which never reaches the control channel.

```mermaid
sequenceDiagram
  participant LinnStrument
  participant surface
  participant live_state
  participant engine
  participant live_actions
  participant Live
  LinnStrument->>surface: pad press
  surface->>live_state: read
  live_state-->>surface: snapshot
  surface->>engine: handle(state, event, snapshot)
  engine-->>surface: (state, actions)
  surface->>live_actions: apply(action)
  live_actions->>Live: Live calls
  opt follow-up
    live_actions-->>surface: follow-up event
    surface->>engine: handle(state, follow-up, snapshot), once
    engine-->>surface: (state, actions)
    surface->>live_actions: apply(action), events it returns are dropped
  end
  Note over surface: tick
  surface->>live_state: read
  live_state-->>surface: snapshot
  surface->>engine: render(state, snapshot)
  engine-->>surface: Frame
  Note over surface: LED driver compares the frame with the last one sent
  surface->>LinnStrument: only the pads that differ
```

Snapshots are read fresh on each tick and each event, except Mixer Mode Y reports (section 6, Fader glide). Polling is chosen for simplicity: 91 clip slots with several properties each, plus 13 tracks, 7 scenes and transport state, a few times a second. A full snapshot costs about 0.5 ms (3 ms at worst).

## 4. Module layout

The core starts coarse and a module is split when it grows.

```
src/BleakLoop/
  __init__.py          create_instance
  surface.py           plumbing: ControlSurface subclass, elements, MIDI routing per mode, tick
  device.py            pure: NRPN, split setup and LED message building, LED driver
  live_state.py        adapter: Live -> Snapshot
  live_actions.py      adapter: Action -> Live calls
  core/
    layout.py          geometry: pad <-> device row, column roles, 13 x 7 window, window movement and clamping
    model.py           Snapshot, Action and Frame types (plain dataclasses)
    modes.py           Session / Mixer / Linnstrument, Linnstrument Mode pages, modifiers
    controls.py        shared Session and Linnstrument Mode behaviour: undo, metronome, Play/Stop, record, Fixed Length and scene lights
    session.py         clip slots, copy and delete rules, bottom row, columns 15, 16, Shift layer table
    column_1.py        column 1 in every mode: its controls, Shift, and Linnstrument Mode's scene page
    mixer.py           Mixer toggle, coarse steps, bands, smoothing
    linnstrument_mode.py  Linnstrument Mode: column 1 only, handed to column_1
    leds.py            device colours, track colour matching, tempo and fast blink
    values.py          every value in section 8, by name
    engine.py          handle() and render(), composing the modules above
tests/                 pytest: the core, the docs generators and the layering
  test_manual.py       every lit pad in the manual's example Sets is labelled; generated docs are current
  test_architecture.py core imports only core; adapters import no plumbing
tools/
  docs/                generated docs (standard library only)
    __main__.py        writes every generated file below; --check
    markers.py         rewrites generated text between marker comments
    svg.py             shared SVG palette and drawing primitives
    manual/            the player's manual
      scenes.py        one example Set per manual layer
      pads.py          pad labels and callout items, by manual section; each map joins its sections
      draw.py          one SVG pad map per layer: labels over the example lights
      generate.py      docs/manual/*.svg and the callout lists in docs/manual.md
    architecture/      this document
      imports.py       the module import graph, from the real imports
      figures.py       the section 5 orientation and colour figures
      generate.py      docs/architecture/*.svg and the import graph in docs/architecture.md
```

The manual's pad maps and callout lists are generated from `core/layout.py` and `render()`, and this document's import graph and section 5 figures from the code. `PYTHONPATH=src python3 -m tools.docs` writes them all, and CI and the pre-commit hook fail when the committed output is stale.

`__init__.py` imports nothing from `ableton` or `Live` at module level; `create_instance` imports `surface` inside the function. This keeps `BleakLoop.core` importable by pytest outside Live. Tests run on Python 3.11 (`uvx --python 3.11 pytest`) to match Live's runtime.

The import graph below is generated from the real imports, and `tests/test_architecture.py` fails if `core/` imports anything outside `core/`.

<!-- generated:imports -->
```mermaid
flowchart TD
  subgraph Plumbing
    __init__["__init__"]
    device["device"]
    surface["surface"]
  end
  subgraph Adapters
    live_actions["live_actions"]
    live_state["live_state"]
  end
  subgraph Core
    core_column_1["column_1"]
    core_controls["controls"]
    core_engine["engine"]
    core_layout["layout"]
    core_leds["leds"]
    core_linnstrument_mode["linnstrument_mode"]
    core_mixer["mixer"]
    core_model["model"]
    core_modes["modes"]
    core_session["session"]
    core_values["values"]
  end
  subgraph External
    Live["Live"]
    ableton_v3["ableton.v3"]
  end
  __init__ -.->|lazy| surface
  core_column_1 --> core_controls
  core_column_1 --> core_layout
  core_column_1 --> core_leds
  core_column_1 --> core_mixer
  core_column_1 --> core_model
  core_column_1 --> core_modes
  core_controls --> core_leds
  core_controls --> core_model
  core_engine --> core_linnstrument_mode
  core_engine --> core_mixer
  core_engine --> core_modes
  core_engine --> core_session
  core_leds --> core_values
  core_linnstrument_mode --> core_column_1
  core_linnstrument_mode --> core_model
  core_mixer --> core_layout
  core_mixer --> core_model
  core_mixer --> core_modes
  core_mixer --> core_values
  core_model --> core_leds
  core_modes --> core_layout
  core_session --> core_column_1
  core_session --> core_controls
  core_session --> core_layout
  core_session --> core_leds
  core_session --> core_mixer
  core_session --> core_model
  core_session --> core_modes
  core_session --> core_values
  device --> core_layout
  device --> core_leds
  device --> core_values
  live_actions --> Live
  live_actions --> core_model
  live_actions --> live_state
  live_state --> core_layout
  live_state --> core_model
  surface --> Live
  surface --> ableton_v3
  surface --> core_engine
  surface --> core_layout
  surface --> core_leds
  surface --> core_model
  surface --> core_modes
  surface --> core_values
  surface --> device
  surface --> live_actions
  surface --> live_state
```
<!-- /generated:imports -->

## 5. Device interface

Sources (Roger Linn Design): [User Firmware Mode](https://github.com/rogerlinndesign/linnstrument-firmware/blob/master/user_firmware_mode.md), [MIDI input and colour values](https://github.com/rogerlinndesign/linnstrument-firmware/blob/master/midi.md), [Panel settings: CC Faders](https://www.rogerlinndesign.com/support/linnstrument-support-panel-settings), [Tips & tricks: one-column CC Faders split](https://www.rogerlinndesign.com/support/support-linnstrument-linnstrument-tips-tricks).

**Orientation.** Columns are counted from the player's left: column 0 is the device's own control switches, columns 1–16 the playing surface. Pads within a column run 1 (farthest row) to 8 (nearest). The device counts rows the other way, so device row = 8 − pad.

![Orientation](architecture/orientation.svg)

**Messages:**

- **User Firmware Mode:** NRPN 245 = 1 takes over the pads; 245 = 0 hands them back. Accepted on any channel. Every NRPN is CC 99 / 98 / 6 / 38 followed by the CC 101 / 100 = 127 reset. The device confirms each change as NRPN 245 on channel 9 about 20 ms later; BleakLoop doesn't listen for it.
- **Pad input** (User Firmware Mode): Note On for a press, Note Off (or Note On velocity 0) for a release. The channel is the device row (channel 1 = device row 0, the nearest) and the note number is the column. Column 0 reports like any pad and is ignored.
- **Lights:** CC 20 (column, from 0), CC 21 (device row, from 0), CC 22 (colour value).
- **Y-axis:** CC 11 = 1 on channels 1–8 turns reporting on per row, CC 11 = 0 off. Reports arrive as CC (64 + column) on the row's channel.
- **Control split** (Linnstrument Mode): set up on load as a one-column note split, column 1 only, in one-channel mode on the control channel (NRPNs in section 8). The setup runs in three phases:
  - **Reads:** Row Offset (227, 253, 263–270) and the right split's channels (100, 101, 102–117, 118), two NRPN 299 queries per step.
  - **Fixed sets:** split on at column 1, one channel, Send X/Y/Z off, no Played colour (a pressed pad would light red over BleakLoop's colour), LowRow off, no special mode, Transpose at 0.
  - **Computed sets:** the control channel and the Octave, worked out from the reads.

  Each set is preceded by a query in the same step, and on unload the player's value is written back for every number BleakLoop set. The control channel is the highest one the right split doesn't use (its main channel, plus its per-note channels or its eight per-row channels). The right split is left untouched, unless it uses all 16: then its highest per-note channel other than the main one is turned off, borrowed and restored on unload. If the right split can't be read, channel 16 is used and the controls stay off. The Octave is the one closest to 0 that keeps all eight column-1 notes in 0–127. In Linnstrument Mode, BleakLoop polls Row Offset and the left split's Octave/Transpose every `POLL_MS`, rebuilds the note map and puts its own Octave/Transpose back if the player changed them. A Row Offset change to custom or Guitar needs values the poll didn't read: column-1 presses are dropped (releases still go through) and the poll repeats at once. A Row Offset that repeats a note in column 1 turns the controls off, with a message, until it changes. The same poll reads the right split's MIDI mode, main channel, per-row lowest channel and the control channel's own per-note switch. If the right split now plays on the control channel, the next poll reads all 16 per-note switches and moves the control channel to the highest free one (NRPN 1), with a message. With none free the controls go off, with a message, and the control channel's notes are no longer listened, so they reach Live's tracks; the full poll goes on until a channel frees up. The right split is never changed mid-session. BleakLoop listens for all 128 notes on the control channel; everything else passes through to Live's tracks.

**Colour values** (CC 22): red 1, yellow 2, green 3, cyan 4, blue 5, magenta 6, off 7, white 8, orange 9, lime 10, pink 11. Value 0 ("as set in Note Lights") also shows dark, but means device default and is used only to hand column 1's lights back on unload. On the device, lime looks yellow and green looks lime.

![Colour values](architecture/colours.svg)

**Device behaviour BleakLoop depends on:**

- **NRPN changes are RAM only.** Flash is written only when the player commits a change on the panel (releasing Per-Split, Octave, Volume, Preset and the like), and each commit saves the whole config as it is in RAM. Checked on the device: an unload that doesn't restore leaves BleakLoop's split until a power cycle (E1). Panel buttons do nothing in User Firmware Mode (E2), but a commit in Linnstrument Mode saves BleakLoop's split to flash (E2′). BleakLoop never makes the device save.
- **NRPN 299 = N reads setting N.** The reply is a normal NRPN (CC 99 / 98 / 6 / 38, then 101 / 100 = 127) on the query's channel minus one, clamped to channel 1. BleakLoop queries on channel 1, so replies arrive there. NRPN 35 doesn't reply when its combination of special modes is unusual; that setting is then not restored.
- **The device applies light changes one at a time.** A full-grid flip leaves Live in under 1 ms but ripples visibly; BleakLoop never adds to it by spreading changes across refreshes.

> [!NOTE]
> **Bursts lose messages.** In a single burst of the split setup the device dropped a block of about 16–19 messages from the middle, so the split setup is paced one step per display tick: two queries, or one query and one NRPN (about 2.8 s at startup). Each step carries one column of the loading rainbow (24 light CCs). On unload, the restore appended to the 38-message hand-back burst lost its last 18 messages, so each restore NRPN is sent after a `RESTORE_GAP_MS` sleep.

- **Control split pads are notes.** Column 1 sends Note On for a press and Note Off for a release on the control channel. The note number follows "Note numbers in a playing split" below, with Transpose at 0 and BleakLoop's Octave.
- **Y is relative and dense.** Every press reports 64 first, after the note-on. Y swings to 127 or 0 over about half a pad and then stays saturated until the release. Reports arrive every 10–20 ms, 1–3 units apart.
- **A slide never overlaps pads.** The old pad's release comes first, then 160–460 ms of silence, then the next pad's press.
- **A still finger rolls.** Y drifts from 64 to about 85 within 100 ms of a press, and further over seconds.

**Note numbers in a playing split.** Outside User Firmware Mode, a pad sends its row note + (column − 1) + 12 × (Octave NRPN 36 − 5) + (Transpose Pitch NRPN 37 − 7) − (Transpose Lights NRPN 38 − 7). Rows count from the nearest, row 0. Notes above 127 aren't sent. The row note comes from the global Row Offset (NRPN 227). Source: `determineRowOffsetNote` in the [firmware](https://github.com/rogerlinndesign/linnstrument-firmware/blob/master/ls_handleTouches.ino). Note names below are Live's (C3 = 60).

| Row Offset (227) | Row note, row r | Measured, column 1, nearest pad first |
| --- | --- | --- |
| +3 to +7 (3–7) | 30 + r × offset | +3: F#0 A0 C1 D#1 F#1 A1 C2 D#2; +4: F#0 A#0 D1 F#1 A#1 D2 F#2 A#2; +5: F#0 B0 E1 A1 D2 G2 C3 F3; +6: F#0 C1 F#1 C2 F#2 C3 F#3 C4; +7: F#0 C#1 G#1 D#2 A#2 F3 C4 G4 |
| Zero (127) | 30 for every row | F#0 on every pad |
| No Overlap (0) | 30 + r × the split's width in columns; the right split's row note also drops by the left split's width | Split off (width 16): F#0 A#1 D3 F#4 A#5 D7 F#8, the farthest pad silent |
| Octave / custom (12) | Custom Row Offset (253) − 16 = offset: 30 + r × offset from 0 to +11, 18 + r × offset from +12, 65 + r × offset from −1 to −11, 18 − 7 × offset + r × offset from −12 | Octave = custom +12: F#-1 F#0 F#1 F#2 F#3 F#4 F#5 F#6; custom +7 = +7; custom +16: F#-1 A#0 D2 F#3 A#4 D6 F#7, the farthest pad silent; custom −3: F3 D3 B2 G#2 F2 D2 B1 G#1; custom −7: F3 A#2 D#2 G#1 C#1 F#0 B-1 E-1; custom −16: the nearest pad silent, then F#7 D6 A#4 F#3 D2 A#0 F#-1 |
| Guitar (13) | Guitar tuning (263–270), 263 the nearest row; set per row by the player | Default: F#0 B0 E1 A1 D2 G2 B2 E3 |

Custom Row Offset 33 is inverted guitar in the firmware: 65 − 5 × r, one lower on the nearest two rows. The panel doesn't offer it. Measured 2026-10-25 with Octave and Transpose at 0.

## 6. Plumbing

### Elements and routing

- **Elements in User Firmware Mode:**
  - Pad presses: notes 0–16 on channels 1–8.
  - Y-axis values: CC 64 + column on channels 1–8, claimed only in Mixer Mode. Columns 2–14 (CC 66–78) become fader input; the other columns are claimed and dropped, because Y reporting is per row and their reports would otherwise reach Live's tracks.

> [!IMPORTANT]
> **Elements in Linnstrument Mode:** notes 0–127 on every channel, 16 × 128 = 2048 note buttons. The control channel is chosen from the right split after load, and elements must be declared before it is known. Only the chosen channel's 128 are listened. All 128, not only the eight that column 1 sends, so column 1 never plays Live's tracks, even between a Row Offset change and the next poll. The build time is logged at load (`BleakLoop elements built in`).

- **NRPN replies:** CC 99, 98, 6, 38, 101 and 100 on channel 1, listened during the setup and in Linnstrument Mode, so the setup's queries and the Linnstrument Mode poll can be read. Their listeners are removed when Session Mode is entered. The cost: in Linnstrument Mode, any channel-1 RPN or NRPN the LinnStrument sends (for example, MPE configuration on a settings change) doesn't reach Live.
- **Routing per mode.** An element only intercepts MIDI while it has a listener, and v3's background layer listens to every element by default. So BleakLoop excludes every element from the background (`_should_include_element_in_background` returns False) and attaches listeners per mode. In Linnstrument Mode, only the control channel's 128 notes and the NRPN replies are listened; everything else reaches Live's tracks.
- **LED output.** One "light pad" call sends CC 20, 21 and 22. The LED driver (section 3) is the only caller. v3's per-element send cache isn't relied on.

> [!IMPORTANT]
> **All device output is sent unoptimised** (`_send_midi(..., optimized=False)`). Inside input callbacks Live buffers "optimized" messages and keeps only the last one per status byte and CC number, which collapses LED triples and NRPN sequences to a single message. This is a hard rule.

### Device lifecycle

- **Device setup and mode.** On load, BleakLoop enters User Firmware Mode, configures the control split in its three phases (paced, section 5), then enters Session Mode, showing a message if the controls are off. NRPN 245 is sent on entering Session and Linnstrument Mode. Each set step queries a setting and then sets it; the device answers in order, so the first reply is the player's own value. The computed sets are worked out only after the fixed sets have gone out, so every read reply has arrived. The setup runs in User Firmware Mode so the device shows a loading rainbow instead of its note lights: NRPNs are answered in either mode, and the device doesn't redraw its note lights over the User Firmware lights. Each step also paints one column (`device.loading_column`), sweeping columns 1–16 with the diagonal hues shifted by one per sweep, so the rainbow rolls. Entering Session Mode redraws every pad over it, and leaving User Firmware Mode clears it. On unload, it turns Y-axis reporting off, leaves User Firmware Mode and returns column 1's lights to value 0 in one burst. It then writes back each number BleakLoop set, in setup order, including a borrowed per-note channel. One NRPN goes out per `RESTORE_GAP_MS` sleep, so the device is playable with the player's own split. Row Offset and the rest of the right split are only read, never written. A setting that never replied keeps BleakLoop's value.

```mermaid
sequenceDiagram
  participant BleakLoop
  participant LinnStrument
  Note over BleakLoop,LinnStrument: Load, one message per display tick
  BleakLoop->>LinnStrument: user_firmware_mode(True), NRPN 245 = 1
  Note over BleakLoop,LinnStrument: every step below also sends loading_column(tick)
  loop read_steps(), two queries per tick
    BleakLoop->>LinnStrument: NRPN 299 = N, NRPN 299 = M
    LinnStrument-->>BleakLoop: NRPN N, NRPN M = player's values, saved
  end
  loop fixed_steps(), then computed_steps(), one setting per tick
    BleakLoop->>LinnStrument: NRPN 299 = N (query), then NRPN N
    LinnStrument-->>BleakLoop: NRPN N = player's value, saved
  end
  Note over BleakLoop: enter_mode(SESSION)
  BleakLoop->>LinnStrument: user_firmware_mode(True), NRPN 245 = 1, already on
  Note over BleakLoop: set_session_highlight(track, scene, 13, 7, False)
  BleakLoop->>LinnStrument: LED driver reset, then the whole frame (CC 20, 21, 22)
  Note over BleakLoop: start the Live.Base.Timer
  Note over BleakLoop,LinnStrument: Unload, disconnect()
  Note over BleakLoop: stop the timer, end_undo_step() if a step is open
  BleakLoop->>LinnStrument: y_axis(False), CC 11 = 0 on channels 1–8
  BleakLoop->>LinnStrument: user_firmware_mode(False), NRPN 245 = 0
  BleakLoop->>LinnStrument: release_column_1(), column 1 lights to value 0
  loop split_restore(saved, set numbers), RESTORE_GAP_MS sleep before each
    BleakLoop->>LinnStrument: NRPN N = player's value
  end
  Note over BleakLoop: set_session_highlight(-1, -1, -1, -1, False)
```
### Clocks

- **Tick.** Two clocks. Live's display callback (a steady 100 ms) reads a snapshot, renders a frame and sends the differences. A `Live.Base.Timer` at 10 ms (measured: about 12 ms on average, 32 ms at worst) checks the blink phases and triggers an extra render when one flips, so tempo blinks land within about one timer period of the beat. The timer reads only the transport (`live_state.read_transport`); the full snapshot is read only when a frame is drawn. Sending MIDI, reading Live state and setting volumes are all allowed from the timer callback.

```mermaid
flowchart LR
  subgraph display["display callback (100 ms)"]
    snapshot["snapshot"] --> draw["render"] --> send["send differences"]
  end
  subgraph timer["Live.Base.Timer (10 ms)"]
    pending{"glide or continuation pending?"} -->|"yes"| tick["engine.tick"]
    pending -->|"no"| transport["read_transport"]
    tick --> transport
    transport --> flipped{"blink phase flipped?"}
    flipped -->|"yes"| extra["extra render"]
  end
```
### Mixer

- **Mixer toggle.** `SetMixer(on)` sends the Y-axis CCs and re-listens, with the Y elements only when on, in one burst with the repaint that follows. There's no LED driver reset: nothing else has touched the device's lights, so the diff is accurate and the burst stays smaller.
- **Fader glide.** `engine.tick(state, now_ms)` runs from the 10 ms timer while any glide or pending continuation exists; it also expires continuation windows and times each press, since events carry no time. A press takes Y relative to its first report, and a press next to a pad released within `CONTINUE_MS` continues the slide, bridging the gap between pads. During a continued slide the glide moves at the measured pad pace (section 8). It needs no snapshot and moves each volume toward its target by an amount scaled by the elapsed time. The surface redraws only when a fader's lit height changes, since the fader shows only 8 heights. A Y report only moves a glide target, so it goes to `engine.y_axis(state, event)` with no snapshot, actions or redraw: the device sends 50–100 a second per finger.

```mermaid
stateDiagram-v2
  [*] --> Idle
  Idle --> Touched: coarse press, BeginUndoStep
  Touched --> Lifted: release
  Lifted --> Touched: press (the next pad continues the slide, any other pad is a coarse step)
  Lifted --> Gliding: CONTINUE_MS window expires, glide still moving
  Lifted --> Idle: CONTINUE_MS window expires, glide done, EndUndoStep
  Gliding --> Touched: press, coarse step
  Gliding --> Idle: glide reaches its target, EndUndoStep
  note right of Idle: leaving Mixer Mode or unload closes an open step
```
### Follow-up events

- **Follow-up events.** `live_actions.apply` may return an event, which `_handle` feeds to the core once after the action loop. The follow-up's own actions are applied, but any events they return are dropped, so this never recurses. Used by Capture: after `song.capture_and_insert_scene()` the adapter returns `SceneSelected` with the index of `song.view.selected_scene` (already updated when the call returns), and the core scrolls the window the minimum distance.
### Detail view

- **Detail-view focus is polled on the display tick.** Live refuses changes made inside a listener callback, and polling needs no listener lifecycle. The surface holds one pending clip slot, and a new `ShowClip` replaces it. On each tick:
  - If the slot has a clip, the surface shows it and clears the pending slot.
  - On any tick after the first, if the slot has no clip and is neither triggered nor recording, the recording was cancelled. The pending slot is cleared, so a clip that lands there later doesn't take the view.
  - If reading the slot raises (its track or scene was deleted), the error is logged and the pending slot is cleared.

> [!IMPORTANT]
> `highlighted_clip_slot` is never set, because that would change the selected track and, with auto-arm, which track is armed.

```mermaid
stateDiagram-v2
  state "pending slot" as Pending
  state "clip shown, slot cleared" as Shown
  state "slot cleared, recording cancelled" as Cancelled
  state "slot cleared, error logged" as Failed
  [*] --> Pending: ShowClip
  Pending --> Pending: a new ShowClip replaces it
  Pending --> Shown: slot has a clip
  Pending --> Cancelled: no clip, not triggered or recording, on a tick after the first
  Pending --> Failed: reading the slot raised
  Shown --> [*]
  Cancelled --> [*]
  Failed --> [*]
```
### Session ring

- **Session ring.** `c_instance.set_session_highlight(track, scene, 13, 7, False)` draws it from the core's window state whenever the window changes and on every Session entry; `(-1, -1, -1, -1, False)` removes it on Linnstrument Mode entry and on unload. v3 draws no ring of its own. Live picks the ring's colour, not BleakLoop.

## 7. Adapters: Live mechanisms

| Behaviour | Mechanism |
| --- | --- |
| Clip and scene launch | `ClipSlot.fire()` and `Scene.fire()`. Legato passes `force_legato=True`, which the LOM doesn't document but Live accepts, also together with `record_length`. |
| Fixed Length | `ClipSlot.fire(record_length=beats)`, with beats = N × numerator × 4 / denominator. Passed only for an empty slot on an armed track, the only case where Live starts a new recording (`fire` raises if the slot owns a clip). Live records the exact length natively, from a stopped transport and with quantization None, so no relaunch timer is needed. |
| Detail view focus | Poll the pending slot on the display tick; set `song.view.detail_clip` and show `Detail/Clip` (section 6). |
| Auto Linnstrument Mode | The core decides from the snapshot (track type, arm, slot state and Session Record) and emits a mode-switch action. |
| Launch quantization | `song.clip_trigger_quantization = Live.Song.Quantization.values[n]`, read back with `int(...)`. Names in `session.QUANTIZATION_NAMES` match Live's dropdown. The remembered choice is core state, not Live. |
| Track and global stop | `Track.stop_all_clips()`, `Song.stop_all_clips()`. Both stop at the next launch quantization mark, like Live's own stop buttons, on purpose. |
| Arm | Exclusive arm disarms the others in `song.tracks`, then sets `track.arm`. Tracks are compared with `!=`, not `is`, because `song.tracks` and `song.visible_tracks` may return different wrappers for one track. `live_state` reads `arm` and `implicit_arm` only when `can_be_armed` is true, because Live is expected to raise on unarmable tracks such as groups. Both guards are deliberate. |
| Track list | `song.visible_tracks`: folded group members are skipped, and unfolding shifts the columns. |
| Status bar messages | `ShowMessage` action, through v3's `ControlSurface.show_message`. |
| Clip copy | `ClipSlot.duplicate_clip_to`. It raises on a MIDI/audio mismatch and on group slots, so the core refuses both first, using the track's `has_midi_input` and `is_foldable`. |
| Group slots | Live reports a group track's slot as having no clip, even when its members hold clips (#12, #13). |
| Scene copy | Every track in `song.tracks` except group tracks, including folded group members. `live_state` reads "scene has a clip" across them only while Copy is held, when the window can't move. |
| Clip and scene delete | `ClipSlot.delete_clip()`, `song.delete_scene()`. |
| Quantize | `clip.quantize(Live.Song.RecordingQuantization.rec_q_sixtenth, 1.0)`. Three candidates (highlighted slot's clip, `song.view.detail_clip`, the selected track's `playing_slot_index` clip), resolved by one helper, `live_state.candidate_clip`, used by both the snapshot and the action. |
| Record pad | Session View: toggle `song.session_record`. Arrangement View: clear `song.back_to_arranger` if set, then toggle `song.record_mode`. Session View's record light counts MIDI Arrangement Overdub, on purpose. |
| Track volume | Read and set `track.mixer_device.volume.value`, clamped to the parameter's `min`/`max`. A glide for a track index that no longer exists is skipped. |
| Fader gesture undo | `song.begin_undo_step()` on the first coarse press and `song.end_undo_step()` once no touch, continuation window or glide is left, so one gesture is one undo step. The core tracks the open step (`State.undo_open`); leaving Mixer Mode and unload close it. |
| Record Clip | `live_state` reads the selected track (`song.view.selected_track`, only if it's in `song.visible_tracks`) and every scene of its slots, plus `song.view.selected_scene`, only in Linnstrument Mode. The core searches from the highlighted scene down, wrapping. When no slot is empty, `song.create_scene(-1)` runs before `FireSlot`: actions resolve their slot when applied, so the new scene exists by then. |
| Capture MIDI | `song.capture_midi()` with no argument, only when `song.can_capture_midi` is true; otherwise the core posts "Nothing to capture". |

## 8. Values

Every tuned number lives here with its reason and status. Code reads them from `core/values.py` by name and never repeats them as literals. Device protocol numbers are in section 5.

| Value | Used by | Source | Status |
| --- | --- | --- | --- |
| Control channel: the highest channel the right split doesn't use; with none free, its highest per-note channel other than the main one, turned off (101 + c = 0); channel 16 if the right split can't be read | `device.control_channel` | Chosen at load from reads 100, 101, 102–117 and 118. Main always counts as used: no NRPN reads the firmware's main-channel-off switch, so a free channel can be skipped, which is harmless | Confirmed on device for Per Note, Per Row and One Channel, including the borrow; the channel 16 fallback can't be reached on a working device |
| Fixed setup NRPNs: 200 = 1 (split on), 202 = `SPLIT_POINT` = 2 (left split is column 1), 0 = 0 (one channel), 20, 24, 27 = 0 (Send X/Y/Z off), 32 = 0 (Played colour off), 34 = 0 (LowRow off), 35 = 0 (no special mode), 37 = 38 = 7 (Transpose 0) | `device.fixed_steps`, each preceded by its query | Device protocol | Confirmed on device: one reply per query, in setup order, all restored on unload |
| Computed setup NRPNs: 1 = control channel, 36 = the Octave fit, plus the borrowed per-note channel if any | `device.computed_steps`, each preceded by its query | Device protocol | Confirmed on device: borrowed channel restored on unload |
| Octave fit: the NRPN 36 value in 0–10 closest to 5, ties lower, that keeps column 1's eight notes in 0–127 | `device.fit_octave` | Device protocol; every Row Offset spans at most 112, so one always fits | Confirmed on device: 5 for Row Offsets 4, 5, 7, No Overlap, +12, −5 and inverted guitar, 4 for +16 and −16 |
| NRPN 299 = N: query setting N, answered as NRPN N | `device.query` | Device protocol | Confirmed on device |
| `RESTORE_GAP_MS = 20`: sleep before each unload restore NRPN | `surface.disconnect` | Tuned: 0 lost the last 18 messages, 20 restored all 13 | Confirmed on device |
| `POLL_MS = 1000`: Linnstrument Mode re-check of Row Offset and the left split's Octave/Transpose | `surface` | Chosen: shorter than a trip through Global Settings and back | Confirmed on device: NRPN 36 refits and a left-split Octave change is reset within about 1 s, with no flicker |
| Control channel clash: each poll also reads 100, 101, 118 and the control channel's per-note switch; on a clash the next poll reads 102–117 and NRPN 1 moves to the highest free channel, or the controls go off with none free | `device.channel_clash`, `device.free_channel`, `surface` | Chosen (#34): all 16 per-note reads on every poll would slow the Row Offset re-check by about 0.8 s | Confirmed on device: moves on a clash, controls off with no channel free, back on when one frees up |
| Off colour value: 7 | `leds` | Device protocol | Confirmed; 0 also dark |
| `FAST_BLINK_MS = 200`: fast blink, 200 ms on, 200 ms off | `leds` | Tuned | Confirmed on device |
| Light refresh: Live's display callback, about 100 ms | `surface` | Mechanism | Measured |
| `BLINK_TIMER_MS = 10`: blink clock, `Live.Base.Timer` | `surface` | Mechanism | Confirmed |
| `TRACK_COLOUR_REFERENCES`: reference RGB per device colour, fitted to Live 12's 70-colour palette (pinned in `tests/test_leds.py`) | `leds` track colour matching | Tuned by eye | Tuned on device; refine if a swatch looks wrong |
| `TEMPO_MIN = 20`, `TEMPO_MAX = 999`: tempo nudge limits | Shift + column 15 | Live's tempo range | Matches Live |
| `VOLUME_ZERO_DB = 0.85`: Live volume control position for 0 dB (1.0 = +6 dB) | `mixer` | Live behaviour | Confirmed |
| `VOLUME_MAX = 1.0`: top of Live's volume range (+6 dB), where fine setting stops | `mixer` | Live behaviour | Confirmed |
| `GLIDE_STEP = 0.018`: fader glide, at most 1.8 % of range per 10 ms, scaled by elapsed time | `mixer` | Tuned | Fine on device; retuning stays in #15 |
| `GLIDE_DEAD_BAND = 0.003`: Y reports moving the target less than 0.3 % of range are ignored, and a glide this close snaps to its target | `mixer` | Tuned | Fine on device; retuning stays in #15 |
| `CONTINUE_MS = 600`: a press next to a pad released within this time continues the slide (device gaps 160–460 ms, section 5) | `mixer` | Tuned | Fine on device; retuning stays in #15 |
| Slide pace: during a continued slide the glide moves one step per press-to-press period of the last pad crossed, never faster than `GLIDE_STEP` | `mixer` | Derived | Fine on device; retuning stays in #15 |
