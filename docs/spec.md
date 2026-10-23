# BleakLoop behaviour spec

## 1. Purpose and scope

This document says what BleakLoop does, from the player's side: what each pad does when pressed, held or combined with Shift, and what each pad shows. It is the target for the first release. Every behaviour is a numbered requirement (`S-<n>`) so plans and reviews can track progress against it. IDs are permanent: new requirements get new numbers, and removed ones are marked as removed rather than renumbered.

The spec describes observable behaviour only. How it is achieved, and every tuned value (timings, smoothing amounts, colour references), lives in `docs/architecture.md`.

Section 9 collects ideas that are not needed for the first release.

Requirements marked **(verify on device)** describe intent where an exact detail still needs confirming on a real LinnStrument and Live 12.

## 2. Terms and orientation

- **Device.** A LinnStrument 128: 16 playing columns by 8 rows, plus a column of the device's own control switches on the far left.
- **Columns** are counted from the player's left. The control switches are column 0; the playing surface is columns 1 to 16.
- **Pads** within a column are counted 1 to 8 starting from the row farthest from the player (pad 1) and ending at the row nearest the player (pad 8).
- **Device rows** are what the LinnStrument itself reports and accepts. They run the other way: device row 0 is the nearest row and device row 7 the farthest. So device row = 8 − pad. Wherever this document says "pad", the device row is 8 minus that number.
- **Live's session grid** has tracks across and scenes down. BleakLoop shows a 13-track by 7-scene window onto it. The top of the window (pad 1) is the lower-numbered scene.
- **Track list.** The tracks BleakLoop controls are Live's visible tracks in order: tracks inside a folded group are skipped, and return and master tracks are never included.
- **Hold.** Some pads act only while held down; releasing the pad ends the effect.
- **Modifiers** are the held pads Shift, Copy and Delete (section 4.1).
- **Tempo blink** and **fast blink** are defined in section 8.

Layout of the playing surface in Session Mode:

| Pad | Column 1 | Columns 2–14 | Column 15 | Column 16 |
| --- | --- | --- | --- | --- |
| 1 | Undo | scene row 1 of the window | Fixed Length 1 bar | scene 1 launch |
| 2 | Copy (hold) | scene row 2 | Fixed Length 2 bars | scene 2 launch |
| 3 | Capture | scene row 3 | Fixed Length 4 bars | scene 3 launch |
| 4 | Delete (hold) | scene row 4 | Fixed Length 8 bars | scene 4 launch |
| 5 | Metronome | scene row 5 | Mixer toggle | scene 5 launch |
| 6 | Play/Stop | scene row 6 | Track Control: Mute | scene 6 launch |
| 7 | Record | scene row 7 | Track Control: Solo | scene 7 launch |
| 8 | Note Mode | per-track control | Track Control: Arm | Shift (hold) |

In Mixer Mode, columns 2–14 become volume faders (section 6). Every other column keeps its Session Mode role.

The Shift layer: what each pad does while Shift is held. A dash means the pad does nothing and is dark (S-101, S-102).

| Pad | Column 1 | Columns 2–14 | Column 15 | Column 16 |
| --- | --- | --- | --- | --- |
| 1 | Redo | legato launch | window up | legato scene launch |
| 2 | Copy (hold) | legato launch | window down | legato scene launch |
| 3 | Quantize clip | legato launch | window left | legato scene launch |
| 4 | Delete (hold) | legato launch | window right | legato scene launch |
| 5 | Launch quantization on/off | legato launch | Stop all clips | legato scene launch |
| 6 | — | legato launch | — | legato scene launch |
| 7 | — | legato launch | Tempo +1 | legato scene launch |
| 8 | — | Mute mode: stop track's clips. Solo and Arm modes: — | Tempo −1 | Shift (hold) |

In Mixer Mode, the fader columns 2–14 do nothing while Shift is held (S-75).

Layout of column 1 in Note Mode (section 7):

| Pad | CC | Controls page | Scene page |
| --- | --- | --- | --- |
| 1 | 8 | Undo | scene 1 launch |
| 2 | 7 | Record Clip | scene 2 launch |
| 3 | 6 | Capture MIDI | scene 3 launch |
| 4 | 5 | Scene page | scene 4 launch |
| 5 | 4 | Metronome | scene 5 launch |
| 6 | 3 | Stop track / transport | scene 6 launch |
| 7 | 2 | Record | scene 7 launch |
| 8 | 1 | Session Mode | back to controls |

## 3. Device interface

Sources (Roger Linn Design):

- [User Firmware Mode](https://github.com/rogerlinndesign/linnstrument-firmware/blob/master/user_firmware_mode.md)
- [MIDI input and colour values](https://github.com/rogerlinndesign/linnstrument-firmware/blob/master/midi.md)
- [Panel settings: CC Faders](https://www.rogerlinndesign.com/support/linnstrument-support-panel-settings)
- [Tips & tricks: one-column CC Faders split](https://www.rogerlinndesign.com/support/support-linnstrument-linnstrument-tips-tricks)

- **S-1** To take over the pads, BleakLoop switches the device into User Firmware Mode by sending NRPN 245 with value 1. The device accepts this on any MIDI channel. To hand the pads back for playing, it sends NRPN 245 with value 0. NRPNs are sent as the standard CC 99 / 98 / 6 / 38 sequence, followed by the CC 101 / 100 = 127 reset.
- **S-2** In User Firmware Mode the device reports a pad press as a Note On and a release as a Note Off. The MIDI channel gives the device row (channel 1 = device row 0, the nearest row). The note number gives the column, with 0 being the control-switch column. A Note On with velocity 0 also counts as a release.
- **S-3** To light a pad, BleakLoop sends CC 20 (column, counted from 0), then CC 21 (device row, counted from 0), then CC 22 (colour value). The colour values are in section 8.
- **S-4** In Mixer Mode, BleakLoop turns on Y-axis reporting for every row by sending CC 11 = 1 on channels 1 to 8, and turns it off again with CC 11 = 0 on the same channels. While Y-axis reporting is on, the device sends CC (64 + column) on the row's channel, with value 0–127 running from the near edge of the pad to the far edge.
- **S-5** In Note Mode the device behaves as the instrument the player has configured, except column 1, which is always BleakLoop's control split. When BleakLoop loads, it configures the device's left split as column 1 only, set to CC Faders, in one-channel mode on the control channel, with faders 1–8 sending CC 1–8. The control channel is a BleakLoop setting that defaults to channel 1. The right split, the player's instrument, is left untouched. In this one-column split, each pad sends 127 when pressed and 0 when released. The nearest row sends CC 1 and the farthest row sends CC 8. BleakLoop listens for CC 1–8 only on the control channel. Every other message in Note Mode, including CC 1–8 on other channels, passes through to Live's tracks untouched. The device has only two splits (one for playing, one for controls), so BleakLoop puts all its Note Mode controls in column 1.
- **S-6** When BleakLoop is unloaded (Live closes, the Set changes, or the control surface is deselected), it turns Y-axis reporting off, leaves User Firmware Mode and returns column 1's lights to the device's own defaults. The device is then playable as a normal instrument, and column 1 stays the control split.

## 4. Modes and switching

There are three modes: **Session**, **Mixer** (a sub-mode of Session) and **Note**.

- **S-7** When BleakLoop loads, it starts in Session Mode.
- **S-8** Entering Session Mode puts the device into User Firmware Mode and draws every pad.
- **S-9** On every entry into Session Mode, Mixer Mode is off and the Track Control mode (section 5.2) resets to Arm.
- **S-10** While in Session Mode, Live shows a ring around the 13 × 7 region of the session grid that the pads control, and the ring follows grid navigation. The ring is removed when entering Note Mode and when BleakLoop is unloaded.
- **S-11** *(Removed: BleakLoop ignores the column 0 hardware buttons. Note Mode is entered from column 1, pad 8 (S-56). Remapping them is S-113.)*
- **S-12** *(Removed: the control-switch lockout after entering Session Mode had no known cause. Re-add only if the device shows a bounce back into Note Mode.)*
- **S-13** Entering Note Mode turns Y-axis reporting off, leaves User Firmware Mode and removes the session ring. It ends Mixer Mode, Delete, Copy (including any chosen copy source) and Shift. Releases of held pads are only seen in Session Mode, so a pad held while switching to Note Mode must not stay latched on return. Column 1 starts on its controls page (S-106).
- **S-14** Asking for Note Mode while already in Note Mode just repeats the "leave User Firmware Mode" message and has no other effect.
- **S-15** Asking for Session Mode while already in Session Mode redraws the pads and refreshes the session ring.
- **S-16** Mixer Mode is entered and left from Session Mode with column 15, pad 5 (section 5.4 and section 6).
- **S-17** Most actions also post a short message in Live's status bar naming what happened, for example "Fixed Length 2 bars", "Delete Mode ON" or "Tempo 121.0 BPM". Refusals always explain why, as listed in the requirements below.

### 4.1 Modifiers

- **S-100** Shift (column 16, pad 8), Copy (column 1, pad 2) and Delete (column 1, pad 4) are modifiers. Each is on while its pad is held and off on release.
- **S-101** While Shift is held, each pad performs its Shift function (the Shift layer table in section 2), or does nothing if it has none. The modifier pads themselves always act as modifiers.
- **S-102** While Shift is held, every pad shows its Shift-layer colour, or is dark if it has no Shift function. A Shift function that is a variant of the pad's normal action (legato launch, Redo) keeps the normal colour. The Copy and Delete pads keep their normal colours.
- **S-103** When modifiers are held together, Copy takes precedence over Delete, and Delete over Shift, unless a requirement defines that combination. No combinations are defined yet.
- **S-104** In Mixer Mode, Copy and Delete do nothing, and the fader columns do nothing while Shift is held. These are reserved for later use (S-111).
- **S-105** Note Mode has no modifiers yet. Column 1 reports releases (S-5), so holds are possible there later (S-114).
- **S-112** While Copy or Delete is held, only the pads it targets respond: clip slots (pads 1–7 of columns 2–14), scene pads, and the other modifier pads. Every other pad does nothing.

## 5. Session Mode

### 5.1 Clip slots (pads 1–7 of columns 2–14)

Each column is one track in the window. Each of pads 1–7 is one scene in the window.

- **S-18** Pressing a pad launches that clip slot. Launching an empty slot on an armed track starts recording into it, following Live's own behaviour.
- **S-19** With Shift held, the slot launches with legato.
- **S-20** With Delete held, pressing a pad deletes that slot's clip. An empty slot is left alone.
- **S-21** With Copy held, the first press on a slot that has a clip makes it the copy source. Pressing a slot without a clip while no source is chosen does nothing except post a hint to pick a clip or scene.
- **S-22** With Copy held and a clip source chosen, pressing an empty slot copies the clip there. The target can be on any track in the window.
- **S-23** Copies are only made between matching kinds: a MIDI clip into a MIDI track, and an audio clip into an audio track. On a mismatch, BleakLoop posts a message and drops the source. Copy stays active while its pad is held, so the next press picks a new source instead of launching a slot.
- **S-24** With Copy held, pressing a slot that already has a clip as the target posts "target not empty" and drops the source. Copy stays active.
- **S-25** After a successful clip copy, the source is cleared and Copy stays active, ready for another source.
- **S-26** If a scene was chosen as the copy source, pressing a grid slot posts a hint to pick a scene target and does nothing else.
- **S-27** Copy takes precedence over Delete when both are held (see S-103).
- **S-28** A slot outside the session (a track column past the last track, or a row past the last scene) does nothing when pressed.
- **S-29** *(Removed: the refusal to start a Fixed Length recording while the transport is stopped. Live records the fixed length correctly from a stopped transport.)*
- **S-30** When a Fixed Length recording starts, it stops by itself after N bars, so the clip is exactly N bars long whatever the launch quantization. A bar is the current time signature's bar (for example 3 quarter notes in 6/8). If the recording is stopped earlier by other means, BleakLoop does nothing further with it.
- **S-31** Auto Note Mode: if pressing a slot starts a recording, BleakLoop switches to Note Mode, provided the track is a MIDI track. A recording here means an empty slot on an armed track, a slot that is already recording, or a playing clip while Session Record or Overdub is on. An audio track stays in Session Mode so audio looping isn't interrupted.
- **S-32** Whenever a press starts or continues a recording (as in S-31, on any track type) or starts a Fixed Length recording, Live shows that clip in the Detail view as soon as the clip exists.

Colours, highest priority first:

- **S-33** Chosen copy source: red, fast blink.
- **S-34** Recording: red.
- **S-35** Triggered (waiting to launch): yellow.
- **S-36** Playing: the track's colour, tempo blink.
- **S-37** Has a clip, not playing: the track's colour, steady.
- **S-38** Empty slot on an armed track (armed directly or by selection): white.
- **S-39** Empty slot otherwise, or outside the session: off.

### 5.2 Bottom row of columns 2–14 (pad 8): per-track switches

Each of these pads acts on its column's track. Which switch it is (Mute, Solo or Arm) is set from column 15, pads 6–8; Arm is the default.

- **S-40** Mute mode: a press toggles the track's mute. Colour: orange while the track is audible (not muted), lime while muted.
- **S-41** Mute mode with Shift held: a press stops all clips on that track instead. Shift colour: red.
- **S-42** Solo mode: a press toggles the track's solo. It has no Shift function. Colour: blue when soloed, lime when not.
- **S-43** Arm mode: a press selects the track in Live. If the track can be armed, every other armable track is disarmed and this track's arm is toggled. Pressing an armed track therefore disarms it and leaves nothing armed. A track that can't be armed (for example a group) is only selected. It has no Shift function. Colour: red when armed (directly or because selecting it auto-arms it), lime when not.
- **S-44** A column with no track: the pad is off and does nothing.

### 5.3 Column 1: transport and editing

- **S-45** Pad 1: Undo. With Shift: Redo. Colour: white.
- **S-46** Pad 2 (hold): Copy. It is on while held and off on release. Releasing it also clears any chosen source. While on, grid and scene presses follow the copy rules (S-21 to S-26, S-66, S-67). Colour: magenta, or red fast blink while held.
- **S-47** Pad 3: Live's Capture and Insert Scene. Afterwards, the window scrolls the minimum distance needed to keep the newly selected scene within the seven visible scene rows, and the session ring follows. Colour: lime.
- **S-48** Pad 3 with Shift: apply 1/16-note quantization, at 100 % amount, to the current MIDI clip. The current clip is the highlighted slot's clip if it has one, otherwise the clip in the Detail view, otherwise the first playing or recording clip on the selected track. If none is found, or it's an audio clip, BleakLoop posts a message and does nothing. Shift colour: magenta.
- **S-49** Pad 4 (hold): Delete. It is on while held and off on release. While on, grid and scene presses delete (S-20, S-65). Colour: red, fast blink while held.
- **S-50** Pad 5: toggle the metronome. Colour: orange, fast blink while the metronome is on.
- **S-51** Pad 5 with Shift: switch global launch quantization off and on. Switching it off sets it to None and remembers the previous value. Switching it on restores the remembered value, or 1 Bar if there is none. Shift colour: green when quantized, red when None.
- **S-52** Pad 6: start the transport if stopped, stop it if playing. Colour: blue while stopped, green tempo blink while playing.
- **S-53** *(Removed: Play/Stop protection. Pad 6 has no Shift function.)*
- **S-54** Pad 7 (record), when Live's Session View is showing: toggle Session Record. Colour: red, or red tempo blink while Session Record or Overdub is on.
- **S-55** Pad 7 when Live's Arrangement View is showing: first turn off Back to Arrangement, then toggle Arrangement Record. Colour: red tempo blink while Arrangement Record is on. Otherwise orange tempo blink while Back to Arrangement is lit, otherwise red.
- **S-56** Pad 8: switch to Note Mode. Colour: white.

### 5.4 Column 15: recording length, mixer, per-track switch mode

- **S-57** Pads 1–4 select a Fixed Length of 1, 2, 4 and 8 bars. Only one length can be selected at a time. Pressing the selected length again clears it (no fixed length). The length applies to new recordings started from the clip grid (S-30) and from Note Mode Record Clip (S-78). Colour: cyan, fast blink on the selected length.
- **S-58** Pads 1–4 with Shift move the window by one step. Pad 1 moves it up one scene and pad 2 down one scene; pad 3 moves it left one track and pad 4 right one track. The window never moves past the first scene or track. It stops moving down or right once the last scene or track is in view, so that a full 7 scenes and 13 tracks stay visible when the session has that many. The session ring follows. Shift colour: yellow.
- **S-59** Pad 5: enter or leave Mixer Mode (section 6). Colour: white.
- **S-60** Pad 5 with Shift: stop all clips in the Set. Shift colour: red.
- **S-61** Pads 6, 7 and 8 select the Track Control mode: Mute, Solo and Arm. The selected mode's pad blinks with the tempo, and the others are steady. Colours: pad 6 orange, pad 7 blue, pad 8 red.
- **S-62** Pad 7 with Shift: raise the tempo by 1 BPM. Pad 8 with Shift: lower it by 1 BPM. The tempo stays within 20–999 BPM. Shift colour: green.

### 5.5 Column 16: scenes and Shift

- **S-63** Pads 1–7: launch the scene on that row of the window, using Live's launch quantization.
- **S-64** With Shift held: launch the scene with legato.
- **S-65** With Delete held: delete the scene, unless it's the only scene left, in which case BleakLoop posts "cannot delete last scene". After a delete, the window moves up if needed so it still points at existing scenes.
- **S-66** With Copy held, the first press chooses a source scene. The scene must contain at least one clip on any track, otherwise BleakLoop posts a hint. If a clip was chosen as the source instead, a scene press posts a hint to pick a clip target.
- **S-67** With Copy held and a scene source chosen, pressing another scene copies every clip from the source scene into the same tracks of the target. The target must be empty on every track; if not, BleakLoop posts "target scene not empty" and drops the source. After a successful copy, the source is cleared and Copy stays active.
- **S-68** Scene pad colours, highest priority first: copy source, red fast blink; a clip playing on one of the 13 tracks in the window, lime tempo blink; at least one clip on those 13 tracks, white; otherwise off. Scenes past the end of the Set are off.
- **S-69** Pad 8 (hold): Shift (S-100). Colour: white, fast blink while held.

## 6. Mixer Mode

Mixer Mode turns columns 2–14 into one volume fader per track in the window. Columns 1, 15 and 16 keep their Session Mode behaviour, except as stated in S-104.

- **S-70** Entering Mixer Mode turns on Y-axis reporting (S-4), drops any chosen copy source, and redraws columns 2–14 as faders. Leaving Mixer Mode (column 15, pad 5 again) turns Y-axis reporting off and redraws columns 2–14 as the clip grid. Fine-control state (S-72) is reset on both entry and exit.
- **S-71** Coarse setting: the first press in a track's column sets the track volume to one of eight steps, measured in Live's volume control position up to the 0 dB position. Pad 1 is 0 dB, pad 2 is 7/8 of the 0 dB position, and so on down to pad 8 at 1/8.
- **S-72** Fine setting: while a finger stays down in a column, BleakLoop remembers the last-pressed pad as that column's band. Further presses in the same column, as the finger slides between pads, move the band without jumping the volume. The finger's Y position within the pad (0–127, S-4) then sets the volume within that band. Each pad's band runs from the coarse step of the pad below it up to its own coarse step. The two ends stretch: pad 8's band starts at silence, and pad 1's band runs from pad 2's step up to the top of Live's range (above 0 dB). The device sends only a few Y reports per slide, with large steps between them, so the movement is smoothed: the volume glides between reports instead of jumping, and doesn't stall while the finger crosses the gap between two pads. The first Y report of every touch is the pad's centre whatever the finger's position, so it is ignored.
- **S-73** Fader colour: a bar in the track's colour, lit from pad 8 up to the pad nearest the current volume. Any existing track shows at least pad 8 lit. A column with no track is fully off.
- **S-74** A fader column redraws immediately when its volume changes from a press or slide.
- **S-75** Column 15, pad 5 shows white with a fast blink the whole time, including while faders are being moved. The fader columns do nothing while Shift is held (S-104).

## 7. Note Mode

In Note Mode the device is an instrument again. BleakLoop only listens to column 1 (a one-column CC Faders split, S-5) and lights its pads. Column 1 has two pages: the controls page and the scene page.

- **S-76** Each column 1 pad acts when pressed (CC value 127). Releases (value 0) do nothing. Column 1 CCs that arrive while in Session Mode are ignored.
- **S-77** Pad 1 (CC 8): Undo. Colour: white.
- **S-78** Pad 2 (CC 7): Record Clip. On the selected track, start recording into the next empty slot, searching from the highlighted scene downward and then wrapping to the top. If the track has no empty slot, a new scene is added at the end and used. Fixed Length applies (S-30), and the clip is shown in the Detail view. If the selected track is the master or a return track (not in the track list), nothing is recorded and BleakLoop posts "no selected track". Colour: magenta.
- **S-79** Pad 3 (CC 6): Live's Capture MIDI. Colour: lime.
- **S-80** *(Removed: Note Mode delete clip. Pad 4 opens the scene page instead (S-106). Clips can still be deleted from Session Mode.)*
- **S-81** Pad 5 (CC 4): toggle the metronome. Colour: orange, fast blink while on.
- **S-82** Pad 6 (CC 3), when Live's Session View is showing: stop all clips on the selected track. Colour: green.
- **S-83** Pad 6 when Live's Arrangement View is showing: start or stop the transport. Colour: blue while stopped, green tempo blink while playing.
- **S-84** Pad 7 (CC 2): record, behaving and lit exactly as described in S-54 and S-55.
- **S-85** Pad 8 (CC 1): switch to Session Mode. Colour: white.
- **S-86** Column 1's lights keep updating in Note Mode, and both blink styles keep running there.
- **S-106** Pad 4 (CC 5) on the controls page: switch column 1 to the scene page. Colour: pink. Every entry into Note Mode starts on the controls page.
- **S-107** On the scene page, pads 1–7 launch the scenes on rows 1–7 of the Session Mode window, using Live's launch quantization. After a launch, column 1 returns to the controls page. Colours as S-68, without the copy-source state.
- **S-108** On the scene page, pad 8 (CC 1) returns to the controls page without launching anything. Colour: white.

## 8. LEDs and blinking

- **S-87** Colours used, by the device's own colour names and CC 22 values: red 1, yellow 2, green 3, cyan 4, blue 5, magenta 6, white 8, orange 9, lime 10, pink 11.
- **S-88** "Off" means the pad is dark, sent as colour value 7. Value 0 ("as set in Note Lights settings") also shows dark in User Firmware Mode and in the control split, but means "device default" and is used only for handing lights back (S-6).
- **S-89** Track colour: Live's track colour is shown as the closest device colour. The candidates are red, yellow, green, cyan, blue, magenta, white, orange, lime and pink, each matched against a reference colour tuned on the device.
- **S-90** Tempo blink: the pad is lit during the opening half of every beat and dark during the closing half. While the transport plays, the phase follows the song position, so blinks land on the beat. While stopped, it keeps pulsing at the Set's tempo. It keeps running in Note Mode.
- **S-91** Fast blink: a fixed on/off rhythm, independent of tempo.
- **S-92** Lights follow state changes promptly, and tempo blinks are never late.
- **S-93** All tempo-blinking pads switch together, as closely as the device allows. The device applies light changes one at a time, so a full-grid change shows a slight ripple. BleakLoop sends each change once and in one pass, and never adds to the ripple by spreading changes across refreshes.
- **S-94** After any switch between Session, Mixer and Note Mode, every pad shows its correct colour, regardless of what was lit before.

## 9. Later

Ideas not needed for the first release. None of these are reachable from any pad today.

- **S-95** Launch quantization pads: one pad each for global launch quantization of a bar, a quarter, an eighth or a sixteenth, with the active choice blinking.
- **S-96** Duplicate clip: copy the most recently pressed clip (or the highlighted or playing one) into the next free slot below it on the same track, adding a scene if needed.
- **S-97** Duplicate scene: duplicate the selected scene in place and select the copy.
- **S-98** A latching scene-copy mode, separate from the held Copy pad, toggled on and off by a pad.
- **S-99** Notice when the player leaves User Firmware Mode from the device's Global Settings (the device reports every User Firmware Mode change as NRPN 245 on channel 9, about 20 ms after the switch), and treat it as switching to Note Mode.
- **S-109** FX view: a third view of columns 2–14 alongside the clip grid and Mixer. It offers mixer-style faders for effects the player sets up, plus pads that recall FX scenes. Column 16 and the view switches stay as in Session Mode, and Copy and Delete act on FX scenes. Open: where its view switch goes (column 15 has no free pad), and what the faders are mapped to.
- **S-110** FX scenes (name to be decided): a stored snapshot of effect parameter values that can be recalled later. Each FX scene stores a transition length, and recalling it morphs the parameters from their current values to the stored ones over that length. Snapshots live in a Max for Live device in the Set. The concept comes from the Neuzeit Drop; the player will describe the intended behaviour.
- **S-111** Reserved combinations: Copy and Delete in Mixer Mode, Shift on the Mixer faders, and Shift combined with Copy or Delete (S-103, S-104).
- **S-113** Remap the column 0 hardware buttons in Session Mode to BleakLoop functions. In User Firmware Mode they report presses like any pad (S-2).
- **S-114** Note Mode modifiers: use held column 1 pads (S-5) for a Shift layer in Note Mode.
