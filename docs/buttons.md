# Buttons

<!-- Generated from src/BleakLoop/buttons.toml by PYTHONPATH=src python3 -m tools.docs. Edit that file, not this one. -->

Where every button is, and what it says in Live's status bar. Pads are column/pad: column 1 is
the Global column, pad 1 the far row. Refusals always show; a function with
`show = false` keeps its other messages quiet.

## Global column: Session, Mixer and FX Mode

`global`

| Pad | Label | Function | Message | Outcomes | Refusals | Shown |
|---|---|---|---|---|---|---|
| 1/1 | Play | `play_stop` |  | play: Play<br>stop: Stop |  | yes |
| 1/2 | Record | `record` |  | session_on: Session Record: ON<br>session_off: Session Record: OFF<br>arrangement_on: Arrangement Record: ON<br>arrangement_off: Arrangement Record: OFF |  | yes |
| 1/3 | Capture | `capture` | Capture and Insert Scene |  |  | yes |
| 1/4 | Metro | `metronome` |  | on: Metronome: ON<br>off: Metronome: OFF |  | yes |
| 1/5 | Length | `fixed_length` | Fixed Length: {bars} {unit} | off: Fixed Length: OFF |  | yes |
| 1/6 | Undo | `undo` | Undo |  | nothing: Nothing to undo | yes |
| 1/7 | Linn | `linnstrument_mode` | Linnstrument Mode |  |  | yes |
| 1/8 | Shift | `shift` | Shift |  |  | yes |

## Global column with Shift: Session, Mixer and FX Mode

`global-shift`

| Pad | Label | Function | Message | Outcomes | Refusals | Shown |
|---|---|---|---|---|---|---|
| 1/1 | StopAll | `stop_all` | Stop all clips |  |  | yes |
| 1/3 | Quant | `quantize` | Quantize: 1/16 |  | no_clip: No clip to quantize<br>audio: Cannot quantize an audio clip | yes |
| 1/4 | LaunchQ | `launch_quantization` | Launch Quantization: {name} |  |  | yes |
| 1/6 | Redo | `redo` | Redo |  | nothing: Nothing to redo | yes |

## Column 15: Session, Mixer and FX Mode

`view`

| Pad | Label | Function | Message | Outcomes | Refusals | Shown |
|---|---|---|---|---|---|---|
| 15/7 | Unmute | `unmute_all` | Unmute all |  |  | yes |
| 15/8 | Stop | `stop` | Stop clips: {track} | held: Stop: pick a track |  | yes |

## Column 15 with Shift

`view-shift`

| Pad | Label | Function | Message | Outcomes | Refusals | Shown |
|---|---|---|---|---|---|---|
| 15/7 | Unsolo | `unsolo_all` | Unsolo all |  |  | yes |
| 15/8 | Unarm | `unarm_all` | Unarm all |  |  | yes |

## Navigation column: Session, Mixer and FX Mode

`navigation`

| Pad | Label | Function | Message | Outcomes | Refusals | Shown |
|---|---|---|---|---|---|---|
| 16/1 | Session | `session` | Session Mode | split_on: Split view: ON<br>split_off: Split view: OFF |  | yes |
| 16/2 | Mixer | `mixer` |  | split_on: Split view: ON<br>split_off: Split view: OFF<br>on: Mixer Mode: ON<br>off: Mixer Mode: OFF |  | yes |
| 16/3 | FX | `fx` |  | on: FX Mode: ON<br>off: FX Mode: OFF |  | yes |
| 16/4 | reserved | `reserved` |  |  |  | yes |
| 16/5 | Seq | `seq` | Seq: tap for Sequencer, or press a clip | entered: Sequencer<br>left: Session Mode | needs_midi: Sequencer needs a MIDI track | yes |
| 16/6 | Delete | `delete` |  | held: Delete: pick a clip or scene<br>held_steps: Delete: pick a step or note pad | last_scene: Cannot delete last scene | yes |
| 16/7 | Copy | `copy` |  | held: Copy: pick a clip or scene<br>held_slots: Copy: pick a snapshot<br>picked_snapshot: Copy: pick an empty slot<br>snapshot_copied: {source} copied to {target}<br>picked_clip: Copy: pick an empty slot<br>clip_copied: Clip copied<br>clips_copied: Clips copied<br>picked_scene: Copy: pick an empty scene<br>scene_copied: Scene copied<br>held_steps: Copy: pick a step<br>picked_step: Copy: pick steps | empty_slot: Copy: pick a clip or scene<br>scene_source: Pick a scene target<br>target_full: Target not empty<br>group_target: Cannot copy into a group track<br>kinds: Cannot copy between MIDI and audio tracks<br>other_group: Pick a slot in the same group<br>empty_scene: Scene is empty<br>clip_source: Pick a clip target<br>scene_full: Target scene not empty<br>empty_step: Step is empty<br>empty_snapshot: Copy: pick a snapshot<br>bound_scene: Scene snapshots can't be bound | yes |
| 16/8 | DevClip | `device_clip` | Device/Clip: tracks and devices | device: Device view<br>clip: Clip view |  | yes |

## Navigation column with Shift

`navigation-shift`

| Pad | Label | Function | Message | Outcomes | Refusals | Shown |
|---|---|---|---|---|---|---|
| 16/1 | Tempo+ | `tempo` 1 | Tempo: {bpm:.1f} BPM |  |  | yes |
| 16/2 | Tempo- | `tempo` -1 | Tempo: {bpm:.1f} BPM |  |  | yes |
| 16/3 | Panel | `fader_source` |  | device: Faders: Device FX<br>snapshots: Faders: FX snapshots |  | yes |
| 16/5 | Up | `window` (0, -1) | Tracks {first_track}–{last_track}, Scenes {first_scene}–{last_scene} |  |  | yes |
| 16/6 | Down | `window` (0, 1) | Tracks {first_track}–{last_track}, Scenes {first_scene}–{last_scene} |  |  | yes |
| 16/7 | Right | `window` (1, 0) | Tracks {first_track}–{last_track}, Scenes {first_scene}–{last_scene} |  |  | yes |
| 16/8 | Left | `window` (-1, 0) | Tracks {first_track}–{last_track}, Scenes {first_scene}–{last_scene} |  |  | yes |

## Device/Clip held

`device-clip`

| Pad | Label | Function | Message | Outcomes | Refusals | Shown |
|---|---|---|---|---|---|---|
| 16/4 | Device+ | `devices` 1 |  |  |  | yes |
| 16/5 | Device- | `devices` -1 |  |  |  | yes |
| 16/6 | Track+ | `tracks` 1 |  |  |  | yes |
| 16/7 | Track- | `tracks` -1 |  |  |  | yes |

## FX Mode and the split views' snapshot panel

`fx`

| Pad | Label | Function | Message | Outcomes | Refusals | Shown |
|---|---|---|---|---|---|---|
| 10/1 | 1 bar | `bars` 1 | Bars: {bars}, press a snapshot or scene |  |  | yes |
| 10/2 | 2 bars | `bars` 2 | Bars: {bars}, press a snapshot or scene |  |  | yes |
| 10/3 | 4 bars | `bars` 4 | Bars: {bars}, press a snapshot or scene |  |  | yes |
| 10/4 | 8 bars | `bars` 8 | Bars: {bars}, press a snapshot or scene |  |  | yes |
| 10/5 | 16 bars | `bars` 16 | Bars: {bars}, press a snapshot or scene |  |  | yes |
| 11/1 | slots | `slots` 1 |  | cleared: {name} cleared<br>stored: {name} stored ({racks})<br>recalled: {name} recalled{note}<br>morphing: {name} {timing}{note}<br>bound: {name}: {params}<br>removed: Removed {param} from {name}<br>unbound: Unbound {param} from {name}<br>rebound: Bound {param} to {name} again<br>updated: {name} punch value: {param}<br>restored: {name}: {param}'s punch value put back<br>punched: {name} punched in{note}<br>slid: {name} at {percent}%{note}<br>slid_bound: {name} at {percent}%: {params}{note}<br>named: {name}: {params}{note} | no_racks: No racks to store<br>no_parameter: Click a parameter in Live first<br>set_wide: Delete {name} to bind to it<br>cannot_hold: {name} can't hold {parameter}<br>nothing: {name}: nothing to recall{note}<br>no_punch: {name}: no punch value for {params}, Shift + slot to store | yes |
| 11/2 | slots | `slots` 2 |  | cleared: {name} cleared<br>stored: {name} stored ({racks})<br>recalled: {name} recalled{note}<br>morphing: {name} {timing}{note}<br>bound: {name}: {params}<br>removed: Removed {param} from {name}<br>unbound: Unbound {param} from {name}<br>rebound: Bound {param} to {name} again<br>updated: {name} punch value: {param}<br>restored: {name}: {param}'s punch value put back<br>punched: {name} punched in{note}<br>slid: {name} at {percent}%{note}<br>slid_bound: {name} at {percent}%: {params}{note}<br>named: {name}: {params}{note} | no_racks: No racks to store<br>no_parameter: Click a parameter in Live first<br>set_wide: Delete {name} to bind to it<br>cannot_hold: {name} can't hold {parameter}<br>nothing: {name}: nothing to recall{note}<br>no_punch: {name}: no punch value for {params}, Shift + slot to store | yes |
| 11/3 | slots | `slots` 3 |  | cleared: {name} cleared<br>stored: {name} stored ({racks})<br>recalled: {name} recalled{note}<br>morphing: {name} {timing}{note}<br>bound: {name}: {params}<br>removed: Removed {param} from {name}<br>unbound: Unbound {param} from {name}<br>rebound: Bound {param} to {name} again<br>updated: {name} punch value: {param}<br>restored: {name}: {param}'s punch value put back<br>punched: {name} punched in{note}<br>slid: {name} at {percent}%{note}<br>slid_bound: {name} at {percent}%: {params}{note}<br>named: {name}: {params}{note} | no_racks: No racks to store<br>no_parameter: Click a parameter in Live first<br>set_wide: Delete {name} to bind to it<br>cannot_hold: {name} can't hold {parameter}<br>nothing: {name}: nothing to recall{note}<br>no_punch: {name}: no punch value for {params}, Shift + slot to store | yes |
| 11/4 | slots | `slots` 4 |  | cleared: {name} cleared<br>stored: {name} stored ({racks})<br>recalled: {name} recalled{note}<br>morphing: {name} {timing}{note}<br>bound: {name}: {params}<br>removed: Removed {param} from {name}<br>unbound: Unbound {param} from {name}<br>rebound: Bound {param} to {name} again<br>updated: {name} punch value: {param}<br>restored: {name}: {param}'s punch value put back<br>punched: {name} punched in{note}<br>slid: {name} at {percent}%{note}<br>slid_bound: {name} at {percent}%: {params}{note}<br>named: {name}: {params}{note} | no_racks: No racks to store<br>no_parameter: Click a parameter in Live first<br>set_wide: Delete {name} to bind to it<br>cannot_hold: {name} can't hold {parameter}<br>nothing: {name}: nothing to recall{note}<br>no_punch: {name}: no punch value for {params}, Shift + slot to store | yes |
| 11/5 | slots | `slots` 5 |  | cleared: {name} cleared<br>stored: {name} stored ({racks})<br>recalled: {name} recalled{note}<br>morphing: {name} {timing}{note}<br>bound: {name}: {params}<br>removed: Removed {param} from {name}<br>unbound: Unbound {param} from {name}<br>rebound: Bound {param} to {name} again<br>updated: {name} punch value: {param}<br>restored: {name}: {param}'s punch value put back<br>punched: {name} punched in{note}<br>slid: {name} at {percent}%{note}<br>slid_bound: {name} at {percent}%: {params}{note}<br>named: {name}: {params}{note} | no_racks: No racks to store<br>no_parameter: Click a parameter in Live first<br>set_wide: Delete {name} to bind to it<br>cannot_hold: {name} can't hold {parameter}<br>nothing: {name}: nothing to recall{note}<br>no_punch: {name}: no punch value for {params}, Shift + slot to store | yes |
| 11/6 | slots | `slots` 6 |  | cleared: {name} cleared<br>stored: {name} stored ({racks})<br>recalled: {name} recalled{note}<br>morphing: {name} {timing}{note}<br>bound: {name}: {params}<br>removed: Removed {param} from {name}<br>unbound: Unbound {param} from {name}<br>rebound: Bound {param} to {name} again<br>updated: {name} punch value: {param}<br>restored: {name}: {param}'s punch value put back<br>punched: {name} punched in{note}<br>slid: {name} at {percent}%{note}<br>slid_bound: {name} at {percent}%: {params}{note}<br>named: {name}: {params}{note} | no_racks: No racks to store<br>no_parameter: Click a parameter in Live first<br>set_wide: Delete {name} to bind to it<br>cannot_hold: {name} can't hold {parameter}<br>nothing: {name}: nothing to recall{note}<br>no_punch: {name}: no punch value for {params}, Shift + slot to store | yes |
| 11/7 | slots | `slots` 7 |  | cleared: {name} cleared<br>stored: {name} stored ({racks})<br>recalled: {name} recalled{note}<br>morphing: {name} {timing}{note}<br>bound: {name}: {params}<br>removed: Removed {param} from {name}<br>unbound: Unbound {param} from {name}<br>rebound: Bound {param} to {name} again<br>updated: {name} punch value: {param}<br>restored: {name}: {param}'s punch value put back<br>punched: {name} punched in{note}<br>slid: {name} at {percent}%{note}<br>slid_bound: {name} at {percent}%: {params}{note}<br>named: {name}: {params}{note} | no_racks: No racks to store<br>no_parameter: Click a parameter in Live first<br>set_wide: Delete {name} to bind to it<br>cannot_hold: {name} can't hold {parameter}<br>nothing: {name}: nothing to recall{note}<br>no_punch: {name}: no punch value for {params}, Shift + slot to store | yes |
| 11/8 | slots | `slots` 8 |  | cleared: {name} cleared<br>stored: {name} stored ({racks})<br>recalled: {name} recalled{note}<br>morphing: {name} {timing}{note}<br>bound: {name}: {params}<br>removed: Removed {param} from {name}<br>unbound: Unbound {param} from {name}<br>rebound: Bound {param} to {name} again<br>updated: {name} punch value: {param}<br>restored: {name}: {param}'s punch value put back<br>punched: {name} punched in{note}<br>slid: {name} at {percent}%{note}<br>slid_bound: {name} at {percent}%: {params}{note}<br>named: {name}: {params}{note} | no_racks: No racks to store<br>no_parameter: Click a parameter in Live first<br>set_wide: Delete {name} to bind to it<br>cannot_hold: {name} can't hold {parameter}<br>nothing: {name}: nothing to recall{note}<br>no_punch: {name}: no punch value for {params}, Shift + slot to store | yes |
| 12/1 | slots | `slots` 9 |  | cleared: {name} cleared<br>stored: {name} stored ({racks})<br>recalled: {name} recalled{note}<br>morphing: {name} {timing}{note}<br>bound: {name}: {params}<br>removed: Removed {param} from {name}<br>unbound: Unbound {param} from {name}<br>rebound: Bound {param} to {name} again<br>updated: {name} punch value: {param}<br>restored: {name}: {param}'s punch value put back<br>punched: {name} punched in{note}<br>slid: {name} at {percent}%{note}<br>slid_bound: {name} at {percent}%: {params}{note}<br>named: {name}: {params}{note} | no_racks: No racks to store<br>no_parameter: Click a parameter in Live first<br>set_wide: Delete {name} to bind to it<br>cannot_hold: {name} can't hold {parameter}<br>nothing: {name}: nothing to recall{note}<br>no_punch: {name}: no punch value for {params}, Shift + slot to store | yes |
| 12/2 | slots | `slots` 10 |  | cleared: {name} cleared<br>stored: {name} stored ({racks})<br>recalled: {name} recalled{note}<br>morphing: {name} {timing}{note}<br>bound: {name}: {params}<br>removed: Removed {param} from {name}<br>unbound: Unbound {param} from {name}<br>rebound: Bound {param} to {name} again<br>updated: {name} punch value: {param}<br>restored: {name}: {param}'s punch value put back<br>punched: {name} punched in{note}<br>slid: {name} at {percent}%{note}<br>slid_bound: {name} at {percent}%: {params}{note}<br>named: {name}: {params}{note} | no_racks: No racks to store<br>no_parameter: Click a parameter in Live first<br>set_wide: Delete {name} to bind to it<br>cannot_hold: {name} can't hold {parameter}<br>nothing: {name}: nothing to recall{note}<br>no_punch: {name}: no punch value for {params}, Shift + slot to store | yes |
| 12/3 | slots | `slots` 11 |  | cleared: {name} cleared<br>stored: {name} stored ({racks})<br>recalled: {name} recalled{note}<br>morphing: {name} {timing}{note}<br>bound: {name}: {params}<br>removed: Removed {param} from {name}<br>unbound: Unbound {param} from {name}<br>rebound: Bound {param} to {name} again<br>updated: {name} punch value: {param}<br>restored: {name}: {param}'s punch value put back<br>punched: {name} punched in{note}<br>slid: {name} at {percent}%{note}<br>slid_bound: {name} at {percent}%: {params}{note}<br>named: {name}: {params}{note} | no_racks: No racks to store<br>no_parameter: Click a parameter in Live first<br>set_wide: Delete {name} to bind to it<br>cannot_hold: {name} can't hold {parameter}<br>nothing: {name}: nothing to recall{note}<br>no_punch: {name}: no punch value for {params}, Shift + slot to store | yes |
| 12/4 | slots | `slots` 12 |  | cleared: {name} cleared<br>stored: {name} stored ({racks})<br>recalled: {name} recalled{note}<br>morphing: {name} {timing}{note}<br>bound: {name}: {params}<br>removed: Removed {param} from {name}<br>unbound: Unbound {param} from {name}<br>rebound: Bound {param} to {name} again<br>updated: {name} punch value: {param}<br>restored: {name}: {param}'s punch value put back<br>punched: {name} punched in{note}<br>slid: {name} at {percent}%{note}<br>slid_bound: {name} at {percent}%: {params}{note}<br>named: {name}: {params}{note} | no_racks: No racks to store<br>no_parameter: Click a parameter in Live first<br>set_wide: Delete {name} to bind to it<br>cannot_hold: {name} can't hold {parameter}<br>nothing: {name}: nothing to recall{note}<br>no_punch: {name}: no punch value for {params}, Shift + slot to store | yes |
| 12/5 | slots | `slots` 13 |  | cleared: {name} cleared<br>stored: {name} stored ({racks})<br>recalled: {name} recalled{note}<br>morphing: {name} {timing}{note}<br>bound: {name}: {params}<br>removed: Removed {param} from {name}<br>unbound: Unbound {param} from {name}<br>rebound: Bound {param} to {name} again<br>updated: {name} punch value: {param}<br>restored: {name}: {param}'s punch value put back<br>punched: {name} punched in{note}<br>slid: {name} at {percent}%{note}<br>slid_bound: {name} at {percent}%: {params}{note}<br>named: {name}: {params}{note} | no_racks: No racks to store<br>no_parameter: Click a parameter in Live first<br>set_wide: Delete {name} to bind to it<br>cannot_hold: {name} can't hold {parameter}<br>nothing: {name}: nothing to recall{note}<br>no_punch: {name}: no punch value for {params}, Shift + slot to store | yes |
| 12/6 | slots | `slots` 14 |  | cleared: {name} cleared<br>stored: {name} stored ({racks})<br>recalled: {name} recalled{note}<br>morphing: {name} {timing}{note}<br>bound: {name}: {params}<br>removed: Removed {param} from {name}<br>unbound: Unbound {param} from {name}<br>rebound: Bound {param} to {name} again<br>updated: {name} punch value: {param}<br>restored: {name}: {param}'s punch value put back<br>punched: {name} punched in{note}<br>slid: {name} at {percent}%{note}<br>slid_bound: {name} at {percent}%: {params}{note}<br>named: {name}: {params}{note} | no_racks: No racks to store<br>no_parameter: Click a parameter in Live first<br>set_wide: Delete {name} to bind to it<br>cannot_hold: {name} can't hold {parameter}<br>nothing: {name}: nothing to recall{note}<br>no_punch: {name}: no punch value for {params}, Shift + slot to store | yes |
| 12/7 | slots | `slots` 15 |  | cleared: {name} cleared<br>stored: {name} stored ({racks})<br>recalled: {name} recalled{note}<br>morphing: {name} {timing}{note}<br>bound: {name}: {params}<br>removed: Removed {param} from {name}<br>unbound: Unbound {param} from {name}<br>rebound: Bound {param} to {name} again<br>updated: {name} punch value: {param}<br>restored: {name}: {param}'s punch value put back<br>punched: {name} punched in{note}<br>slid: {name} at {percent}%{note}<br>slid_bound: {name} at {percent}%: {params}{note}<br>named: {name}: {params}{note} | no_racks: No racks to store<br>no_parameter: Click a parameter in Live first<br>set_wide: Delete {name} to bind to it<br>cannot_hold: {name} can't hold {parameter}<br>nothing: {name}: nothing to recall{note}<br>no_punch: {name}: no punch value for {params}, Shift + slot to store | yes |
| 12/8 | slots | `slots` 16 |  | cleared: {name} cleared<br>stored: {name} stored ({racks})<br>recalled: {name} recalled{note}<br>morphing: {name} {timing}{note}<br>bound: {name}: {params}<br>removed: Removed {param} from {name}<br>unbound: Unbound {param} from {name}<br>rebound: Bound {param} to {name} again<br>updated: {name} punch value: {param}<br>restored: {name}: {param}'s punch value put back<br>punched: {name} punched in{note}<br>slid: {name} at {percent}%{note}<br>slid_bound: {name} at {percent}%: {params}{note}<br>named: {name}: {params}{note} | no_racks: No racks to store<br>no_parameter: Click a parameter in Live first<br>set_wide: Delete {name} to bind to it<br>cannot_hold: {name} can't hold {parameter}<br>nothing: {name}: nothing to recall{note}<br>no_punch: {name}: no punch value for {params}, Shift + slot to store | yes |
| 13/1 | Bank 1 | `banks` 1 |  | selected: Bank {bank} |  | yes |
| 13/2 | Bank 2 | `banks` 2 |  | selected: Bank {bank} |  | yes |
| 13/3 | Bank 3 | `banks` 3 |  | selected: Bank {bank} |  | yes |
| 13/4 | Bank 4 | `banks` 4 |  | selected: Bank {bank} |  | yes |
| 13/5 | Bank 5 | `banks` 5 |  | selected: Bank {bank} |  | yes |
| 13/6 | Bank 6 | `banks` 6 |  | selected: Bank {bank} |  | yes |
| 13/7 | Bank 7 | `banks` 7 |  | selected: Bank {bank} |  | yes |
| 13/8 | Bank 8 | `banks` 8 |  | selected: Bank {bank} |  | yes |
| 14/1 | Scene 1 | `scene_slots` 1 |  | cleared: {name} cleared<br>stored: {name} stored ({racks})<br>recalled: {name} recalled{note}<br>morphing: {name} {timing}{note} | no_racks: No racks to store<br>nothing: {name}: nothing to recall{note} | yes |
| 14/2 | Scene 2 | `scene_slots` 2 |  | cleared: {name} cleared<br>stored: {name} stored ({racks})<br>recalled: {name} recalled{note}<br>morphing: {name} {timing}{note} | no_racks: No racks to store<br>nothing: {name}: nothing to recall{note} | yes |
| 14/3 | Scene 3 | `scene_slots` 3 |  | cleared: {name} cleared<br>stored: {name} stored ({racks})<br>recalled: {name} recalled{note}<br>morphing: {name} {timing}{note} | no_racks: No racks to store<br>nothing: {name}: nothing to recall{note} | yes |
| 14/4 | Scene 4 | `scene_slots` 4 |  | cleared: {name} cleared<br>stored: {name} stored ({racks})<br>recalled: {name} recalled{note}<br>morphing: {name} {timing}{note} | no_racks: No racks to store<br>nothing: {name}: nothing to recall{note} | yes |
| 14/5 | Scene 5 | `scene_slots` 5 |  | cleared: {name} cleared<br>stored: {name} stored ({racks})<br>recalled: {name} recalled{note}<br>morphing: {name} {timing}{note} | no_racks: No racks to store<br>nothing: {name}: nothing to recall{note} | yes |
| 14/6 | Scene 6 | `scene_slots` 6 |  | cleared: {name} cleared<br>stored: {name} stored ({racks})<br>recalled: {name} recalled{note}<br>morphing: {name} {timing}{note} | no_racks: No racks to store<br>nothing: {name}: nothing to recall{note} | yes |

## Global column: Linnstrument Mode

`linnstrument`

| Pad | Label | Function | Message | Outcomes | Refusals | Shown |
|---|---|---|---|---|---|---|
| 1/1 | Play | `play_stop` |  | play: Play<br>stop: Stop |  | yes |
| 1/2 | RecClip | `record_clip` | Record Clip | new_scene: Record Clip: new scene | no_track: No selected track<br>group_track: Cannot record on a group track<br>not_armed: Track not armed | yes |
| 1/3 | CapMIDI | `capture_midi` | Capture MIDI |  | nothing: Nothing to capture | yes |
| 1/4 | Metro | `metronome` |  | on: Metronome: ON<br>off: Metronome: OFF |  | yes |
| 1/5 | Length | `fixed_length` | Fixed Length: {bars} {unit} | off: Fixed Length: OFF |  | yes |
| 1/6 | Undo | `undo` | Undo |  | nothing: Nothing to undo | yes |
| 1/7 | Back | `back` |  | session: Back: Session Mode<br>mixer: Back: Mixer Mode<br>fx: Back: FX Mode<br>sequencer: Back: Sequencer |  | yes |
| 1/8 | Shift | `shift` | Shift |  |  | yes |

## Global column with Shift: Linnstrument Mode

`linnstrument-shift`

| Pad | Label | Function | Message | Outcomes | Refusals | Shown |
|---|---|---|---|---|---|---|
| 1/1 | StopTrk | `stop_track` | Stop clips: {track} |  | no_track: No selected track | yes |
| 1/2 | Record | `record` |  | session_on: Session Record: ON<br>session_off: Session Record: OFF<br>arrangement_on: Arrangement Record: ON<br>arrangement_off: Arrangement Record: OFF |  | yes |
| 1/3 | Quant | `quantize` | Quantize: 1/16 |  | no_clip: No clip to quantize<br>audio: Cannot quantize an audio clip | yes |
| 1/4 | LaunchQ | `launch_quantization` | Launch Quantization: {name} |  |  | yes |
| 1/6 | Redo | `redo` | Redo |  | nothing: Nothing to redo | yes |
| 1/7 | Scenes | `scene_page` | Scene page: pick a scene |  |  | yes |

## Scene page: Linnstrument and Sequencer Mode

`linnstrument-scenes`

| Pad | Label | Function | Message | Outcomes | Refusals | Shown |
|---|---|---|---|---|---|---|
| 1/8 | Back | `close_scenes` | Scene page: closed |  |  | yes |

## Global column: Sequencer Mode

`sequencer-global`

| Pad | Label | Function | Message | Outcomes | Refusals | Shown |
|---|---|---|---|---|---|---|
| 1/1 | Play | `play_stop` |  | play: Play<br>stop: Stop |  | yes |
| 1/2 | RecClip | `record_clip` | Record Clip | new_scene: Record Clip: new scene | no_track: No selected track<br>group_track: Cannot record on a group track<br>not_armed: Track not armed | yes |
| 1/3 | CapMIDI | `capture_midi` | Capture MIDI |  | nothing: Nothing to capture | yes |
| 1/4 | Metro | `metronome` |  | on: Metronome: ON<br>off: Metronome: OFF |  | yes |
| 1/5 | Length | `fixed_length` | Fixed Length: {bars} {unit} | off: Fixed Length: OFF |  | yes |
| 1/6 | Undo | `undo` | Undo |  | nothing: Nothing to undo | yes |
| 1/7 | Linn | `linnstrument_mode` | Linnstrument Mode |  |  | yes |
| 1/8 | Shift | `shift` | Shift |  |  | yes |

## Global column with Shift: Sequencer Mode

`sequencer-global-shift`

| Pad | Label | Function | Message | Outcomes | Refusals | Shown |
|---|---|---|---|---|---|---|
| 1/1 | StopTrk | `stop_track` | Stop clips: {track} |  | no_track: No selected track | yes |
| 1/2 | Record | `record` |  | session_on: Session Record: ON<br>session_off: Session Record: OFF<br>arrangement_on: Arrangement Record: ON<br>arrangement_off: Arrangement Record: OFF |  | yes |
| 1/3 | Quant | `quantize` | Quantize: 1/16 |  | no_clip: No clip to quantize<br>audio: Cannot quantize an audio clip | yes |
| 1/4 | LaunchQ | `launch_quantization` | Launch Quantization: {name} |  |  | yes |
| 1/6 | Redo | `redo` | Redo |  | nothing: Nothing to redo | yes |
| 1/7 | Scenes | `scene_page` | Scene page: pick a scene |  |  | yes |

## Navigation column: Sequencer Mode

`sequencer-nav`

| Pad | Label | Function | Message | Outcomes | Refusals | Shown |
|---|---|---|---|---|---|---|
| 16/1 | Session | `session` | Session Mode | split_on: Split view: ON<br>split_off: Split view: OFF |  | yes |
| 16/2 | Mixer | `mixer` |  | split_on: Split view: ON<br>split_off: Split view: OFF<br>on: Mixer Mode: ON<br>off: Mixer Mode: OFF |  | yes |
| 16/3 | FX | `fx` |  | on: FX Mode: ON<br>off: FX Mode: OFF |  | yes |
| 16/5 | Seq | `seq` | Seq: tap for Sequencer, or press a clip | entered: Sequencer<br>left: Session Mode | needs_midi: Sequencer needs a MIDI track | yes |
| 16/6 | Delete | `delete` |  | held: Delete: pick a clip or scene<br>held_steps: Delete: pick a step or note pad | last_scene: Cannot delete last scene | yes |
| 16/7 | Copy | `copy` |  | held: Copy: pick a clip or scene<br>held_slots: Copy: pick a snapshot<br>picked_snapshot: Copy: pick an empty slot<br>snapshot_copied: {source} copied to {target}<br>picked_clip: Copy: pick an empty slot<br>clip_copied: Clip copied<br>clips_copied: Clips copied<br>picked_scene: Copy: pick an empty scene<br>scene_copied: Scene copied<br>held_steps: Copy: pick a step<br>picked_step: Copy: pick steps | empty_slot: Copy: pick a clip or scene<br>scene_source: Pick a scene target<br>target_full: Target not empty<br>group_target: Cannot copy into a group track<br>kinds: Cannot copy between MIDI and audio tracks<br>other_group: Pick a slot in the same group<br>empty_scene: Scene is empty<br>clip_source: Pick a clip target<br>scene_full: Target scene not empty<br>empty_step: Step is empty<br>empty_snapshot: Copy: pick a snapshot<br>bound_scene: Scene snapshots can't be bound | yes |
| 16/8 | DevClip | `device_clip` | Device/Clip: tracks and devices | device: Device view<br>clip: Clip view |  | yes |

## Navigation column with Shift: Sequencer Mode

`sequencer-nav-shift`

| Pad | Label | Function | Message | Outcomes | Refusals | Shown |
|---|---|---|---|---|---|---|
| 16/1 | Tempo+ | `tempo` 1 | Tempo: {bpm:.1f} BPM |  |  | yes |
| 16/2 | Tempo- | `tempo` -1 | Tempo: {bpm:.1f} BPM |  |  | yes |
| 16/3 | Panel | `fader_source` |  | device: Faders: Device FX<br>snapshots: Faders: FX snapshots |  | yes |
| 16/5 | Up | `window` (0, -1) | Tracks {first_track}–{last_track}, Scenes {first_scene}–{last_scene} |  |  | yes |
| 16/6 | Down | `window` (0, 1) | Tracks {first_track}–{last_track}, Scenes {first_scene}–{last_scene} |  |  | yes |
| 16/7 | Right | `window` (1, 0) | Tracks {first_track}–{last_track}, Scenes {first_scene}–{last_scene} |  |  | yes |
| 16/8 | Left | `window` (-1, 0) | Tracks {first_track}–{last_track}, Scenes {first_scene}–{last_scene} |  |  | yes |

## Column 15: Sequencer Mode

`sequencer-grid`

| Pad | Label | Function | Message | Outcomes | Refusals | Shown |
|---|---|---|---|---|---|---|
| 15/1 | Double | `double` | Loop doubled |  | no_clip: No clip | yes |
| 15/2 | Halve | `halve` | Loop halved |  | no_clip: No clip<br>too_short: Loop can't be shorter than a step | yes |
| 15/4 | Follow | `follow` |  | on: Follow: ON<br>off: Follow: OFF |  | yes |
| 15/6 | Up | `up` |  | notes: Note pads: from {note}<br>pads: Drum pads: from {note} |  | yes |
| 15/7 | Down | `down` |  | notes: Note pads: from {note}<br>pads: Drum pads: from {note} |  | yes |
| 15/8 | View | `view` |  | settings: View: settings<br>notes: View: note pads |  | yes |

## Settings view: Sequencer Mode

`sequencer-settings`

| Pad | Label | Function | Message | Outcomes | Refusals | Shown |
|---|---|---|---|---|---|---|
| 11/1 | 1/4 | `rates` 1.0 | Rate: {rate} | triplet: Rate: {rate} triplet |  | yes |
| 11/2 | 1/8 | `rates` 0.5 | Rate: {rate} | triplet: Rate: {rate} triplet |  | yes |
| 11/3 | 1/16 | `rates` 0.25 | Rate: {rate} | triplet: Rate: {rate} triplet |  | yes |
| 11/4 | 1/32 | `rates` 0.125 | Rate: {rate} | triplet: Rate: {rate} triplet |  | yes |
| 11/5 | Triplet | `triplet` | Rate: {rate} | triplet: Rate: {rate} triplet |  | yes |
| 12/1 | pages | `pages` 1 | Page: {page} | loop: Loop: pages {first}–{last} |  | yes |
| 12/2 | pages | `pages` 2 | Page: {page} | loop: Loop: pages {first}–{last} |  | yes |
| 12/3 | pages | `pages` 3 | Page: {page} | loop: Loop: pages {first}–{last} |  | yes |
| 12/4 | pages | `pages` 4 | Page: {page} | loop: Loop: pages {first}–{last} |  | yes |
| 12/5 | pages | `pages` 5 | Page: {page} | loop: Loop: pages {first}–{last} |  | yes |
| 12/6 | pages | `pages` 6 | Page: {page} | loop: Loop: pages {first}–{last} |  | yes |
| 12/7 | pages | `pages` 7 | Page: {page} | loop: Loop: pages {first}–{last} |  | yes |
| 12/8 | pages | `pages` 8 | Page: {page} | loop: Loop: pages {first}–{last} |  | yes |
| 13/1 | pages | `pages` 9 | Page: {page} | loop: Loop: pages {first}–{last} |  | yes |
| 13/2 | pages | `pages` 10 | Page: {page} | loop: Loop: pages {first}–{last} |  | yes |
| 13/3 | pages | `pages` 11 | Page: {page} | loop: Loop: pages {first}–{last} |  | yes |
| 13/4 | pages | `pages` 12 | Page: {page} | loop: Loop: pages {first}–{last} |  | yes |
| 13/5 | pages | `pages` 13 | Page: {page} | loop: Loop: pages {first}–{last} |  | yes |
| 13/6 | pages | `pages` 14 | Page: {page} | loop: Loop: pages {first}–{last} |  | yes |
| 13/7 | pages | `pages` 15 | Page: {page} | loop: Loop: pages {first}–{last} |  | yes |
| 13/8 | pages | `pages` 16 | Page: {page} | loop: Loop: pages {first}–{last} |  | yes |

## Messages without a button

The faders' and timed scene launches' wording.

| Function | Outcomes | Refusals | Shown |
|---|---|---|---|
| `scenes` | timed: Scene {scene} in {bars}<br>cancelled: Scene {scene} launch cancelled |  | yes |

## System messages

The device setup, Device/Clip's track and device names, and why the button editor shows a function dark. These always show.

| Key | Message |
|---|---|
| `refuse_duplicates` | Row Offset repeats notes in the Global column: controls off |
| `refuse_row_offset` | Couldn't read Row Offset: controls off |
| `refuse_right_split` | Couldn't read the right split: controls off |
| `refuse_channels` | The right split uses every channel: controls off |
| `controls_on` | Global column controls on |
| `controls_moved` | The right split took the Global column's channel: controls moved to channel {channel} |
| `octave_reset` | Left split Octave/Transpose reset: select the right split to change yours |
| `track` | {track} |
| `no_more_tracks` | No more tracks |
| `device` | {device} |
| `no_more_devices` | No more devices |
| `unavailable_leaves_mode` | Use Back to leave Linnstrument Mode |
| `unavailable_edits_surface` | Needs Session, Mixer, FX or Sequencer Mode |
| `unavailable_clip_grid` | Needs Session, Mixer or FX Mode |
| `unavailable_came_from` | Only Linnstrument Mode has a mode to go back to |
| `unavailable_scene_page` | The scene page opens in Linnstrument and Sequencer Mode |
| `unavailable_sequencer` | Needs a sequencer clip |
