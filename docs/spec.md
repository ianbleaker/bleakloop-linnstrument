# BleakLoop behaviour spec

## 1. Purpose and scope

This document says what BleakLoop does, from the player's side: what each pad does when pressed, held or combined with Shift, and what each pad shows. It is the parity target for the first release. Every behaviour is a numbered requirement (`S-<n>`) so plans and reviews can track progress against it. IDs are permanent: new requirements get new numbers, and removed ones are marked as removed rather than renumbered.

Section 9 collects ideas that are not needed for parity.

Requirements marked **(verify on device)** describe intent where an exact detail (a timing, a message value) still needs confirming on a real LinnStrument and Live 12.

## 2. Terms and orientation

- **Device.** A LinnStrument 128: 16 playing columns by 8 rows, plus a column of the device's own control switches on the far left.
- **Columns** are counted from the player's left. The control switches are column 0; the playing surface is columns 1 to 16.
- **Pads** within a column are counted 1 to 8 starting from the row farthest from the player (pad 1) and ending at the row nearest the player (pad 8).
- **Device rows** are what the LinnStrument itself reports and accepts. They run the other way: device row 0 is the nearest row and device row 7 the farthest. So device row = 8 − pad. Wherever this document says "pad", the device row is 8 minus that number.
- **Live's session grid** has tracks across and scenes down. BleakLoop shows a 13-track by 7-scene window onto it. The top of the window (pad 1) is the lower-numbered scene.
- **Track list.** The tracks BleakLoop controls are Live's visible tracks in order: tracks inside a folded group are skipped, and return and master tracks are never included.
- **Hold.** Some pads act only while held down; releasing the pad ends the effect.
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
- **S-5** In Note Mode the device behaves as the instrument the player has configured. Column 1 is expected to be a one-column left split set to CC Faders. In a one-column CC Faders split, each row is an on/off switch: each press alternately sends 127 and 0. The nearest row sends CC 1 and the farthest row sends CC 8, on the split's main channel. BleakLoop listens for CC 1–8 on any channel.
- **S-6** When BleakLoop is unloaded (Live closes, the Set changes, or the control surface is deselected), the device's mode is left unchanged. The device is deliberately not forced out of User Firmware Mode, so reloading a Set doesn't drop the player into Note Mode. **(verify on device)**: what the device shows after Live quits.

## 4. Modes and switching

There are three modes: **Session**, **Mixer** (a sub-mode of Session) and **Note**.

- **S-7** When BleakLoop loads, it starts in Session Mode.
- **S-8** Entering Session Mode puts the device into User Firmware Mode. It then draws every pad, and about 0.2 s later sends every pad's colour again in case the device missed the first draw.
- **S-9** On every entry into Session Mode, Mixer Mode is off and the Track Control mode (section 5.2) resets to Arm.
- **S-10** While in Session Mode, Live shows a ring around the 13 × 7 region of the session grid that the pads control, and the ring follows grid navigation. The ring is removed when entering Note Mode and when BleakLoop is unloaded.
- **S-11** Pressing any control switch in column 0 switches to Note Mode.
- **S-12** For a short time after entering Session Mode (about 1.5 s; **verify on device**), control-switch presses are ignored. This stops the press that triggered the mode change from bouncing straight back into Note Mode.
- **S-13** Entering Note Mode turns Y-axis reporting off, leaves User Firmware Mode and removes the session ring. It ends Mixer Mode, Delete, Copy (including any chosen copy source) and Shift. Releases of held pads are only seen in Session Mode, so a pad held while switching to Note Mode must not stay latched on return.
- **S-14** Asking for Note Mode while already in Note Mode just repeats the "leave User Firmware Mode" message and has no other effect.
- **S-15** Asking for Session Mode while already in Session Mode redraws the pads and refreshes the session ring.
- **S-16** Mixer Mode is entered and left from Session Mode with column 15, pad 5 (section 5.4 and section 6).
- **S-17** Most actions also post a short message in Live's status bar naming what happened, for example "Fixed Length 2 bars", "Delete Mode ON" or "Tempo 121.0 BPM". Refusals always explain why, as listed in the requirements below.

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
- **S-27** Copy takes precedence over Delete when both are held.
- **S-28** A slot outside the session (a track column past the last track, or a row past the last scene) does nothing when pressed.
- **S-29** Fixed Length (section 5.4): when a length is selected and the press would start a new recording (empty slot, armed track) while the transport is stopped, nothing is launched. BleakLoop posts "Start Play first for Fixed Length". The Note Mode auto-switch (S-31) does not happen either.
- **S-30** When a Fixed Length recording does start, the recording ends automatically. N bars after the press (one bar = the time signature's numerator in beats), BleakLoop launches the slot again, which Live turns into "stop recording, start playing". With launch quantization at 1 bar, the resulting clip is exactly N bars long. If the recording stops early by other means, the automatic stop is abandoned.
- **S-31** Auto Note Mode: if pressing a slot starts a recording, BleakLoop switches to Note Mode, provided the track is a MIDI track. A recording here means an empty slot on an armed track, a slot that is already recording, or a playing clip while Session Record or Overdub is on. An audio track stays in Session Mode so audio looping isn't interrupted.
- **S-32** Whenever a press starts or continues a recording (as in S-31, on any track type) or starts a Fixed Length recording, Live shows that clip in the Detail view. The new clip appears in Live a moment after launch, so the focus is retried a few times over about 1.5 s.

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
- **S-41** Mute mode with Shift held: a press stops all clips on that track instead.
- **S-42** Solo mode: a press toggles the track's solo. Shift makes no difference. Colour: blue when soloed, lime when not.
- **S-43** Arm mode: a press selects the track in Live. If the track can be armed, every other armable track is disarmed and this track's arm is toggled. Pressing an armed track therefore disarms it and leaves nothing armed. A track that can't be armed (for example a group) is only selected. Shift makes no difference. Colour: red when armed (directly or because selecting it auto-arms it), lime when not.
- **S-44** A column with no track: the pad is off and does nothing.

### 5.3 Column 1: transport and editing

- **S-45** Pad 1: Undo. With Shift: Redo. Colour: white.
- **S-46** Pad 2 (hold): Copy. It is on while held and off on release. Releasing it also clears any chosen source. While on, grid and scene presses follow the copy rules (S-21 to S-26, S-66, S-67). Colour: magenta, or red fast blink while held.
- **S-47** Pad 3: Live's Capture and Insert Scene. Afterwards, the window scrolls the minimum distance needed to keep the newly selected scene within the seven visible scene rows, and the session ring follows. Colour: lime.
- **S-48** Pad 3 with Shift: apply 1/16-note quantization, at 100 % amount, to the current MIDI clip. The current clip is the highlighted slot's clip if it has one, otherwise the clip in the Detail view, otherwise the first playing or recording clip on the selected track. If none is found, or it's an audio clip, BleakLoop posts a message and does nothing.
- **S-49** Pad 4 (hold): Delete. It is on while held and off on release. While on, grid and scene presses delete (S-20, S-65). Colour: red, fast blink while held.
- **S-50** Pad 5: toggle the metronome. Colour: orange, fast blink while the metronome is on.
- **S-51** Pad 5 with Shift: toggle global launch quantization. If it is None it becomes 1 Bar; otherwise (any value) it becomes None. While Shift is held, this pad shows the launch quantization instead of the metronome: green when quantized, red when None.
- **S-52** Pad 6: start the transport if stopped, stop it if playing. Colour: blue while stopped, green tempo blink while playing.
- **S-53** Pad 6 with Shift: toggle Play/Stop protection. While protected, pad 6 doesn't start or stop the transport; it only posts "Play/Stop protected". Protection doesn't change the pad's colour.
- **S-54** Pad 7 (record), when Live's Session View is showing: toggle Session Record. Colour: red, or red tempo blink while Session Record or Overdub is on.
- **S-55** Pad 7 when Live's Arrangement View is showing: first turn off Back to Arrangement, then toggle Arrangement Record. Colour: red tempo blink while Arrangement Record is on. Otherwise orange tempo blink while Back to Arrangement is lit, otherwise red.
- **S-56** Pad 8: switch to Note Mode. Colour: white.

### 5.4 Column 15: recording length, mixer, per-track switch mode

- **S-57** Pads 1–4 select a Fixed Length of 1, 2, 4 and 8 bars. Only one length can be selected at a time. Pressing the selected length again clears it (no fixed length). The length applies to new recordings started from the clip grid (S-29, S-30) and from Note Mode Record Clip (S-78). Colour: cyan, fast blink on the selected length.
- **S-58** Pads 1–4 with Shift move the window by one step. Pad 1 moves it up one scene and pad 2 down one scene; pad 3 moves it left one track and pad 4 right one track. The window never moves past the first scene or track. It stops moving down or right once the last scene or track is in view, so that a full 7 scenes and 13 tracks stay visible when the session has that many. The session ring follows.
- **S-59** Pad 5: enter Mixer Mode (section 6). Colour: white.
- **S-60** Pad 5 with Shift: stop all clips in the Set.
- **S-61** Pads 6, 7 and 8 select the Track Control mode: Mute, Solo and Arm. The selected mode's pad blinks with the tempo, and the others are steady. Colours: pad 6 orange, pad 7 blue, pad 8 red.
- **S-62** Pad 7 with Shift: raise the tempo by 1 BPM. Pad 8 with Shift: lower it by 1 BPM. The tempo stays within 20–999 BPM. While Shift is held, pads 7 and 8 show green instead of their Track Control colour. Pad 6 ignores Shift.

### 5.5 Column 16: scenes and Shift

- **S-63** Pads 1–7: launch the scene on that row of the window.
- **S-64** With Shift held: launch the scene with legato.
- **S-65** With Delete held: delete the scene, unless it's the only scene left, in which case BleakLoop posts "cannot delete last scene". After a delete, the window moves up if needed so it still points at existing scenes.
- **S-66** With Copy held, the first press chooses a source scene. The scene must contain at least one clip on any track, otherwise BleakLoop posts a hint. If a clip was chosen as the source instead, a scene press posts a hint to pick a clip target.
- **S-67** With Copy held and a scene source chosen, pressing another scene copies every clip from the source scene into the same tracks of the target. The target must be empty on every track; if not, BleakLoop posts "target scene not empty" and drops the source. After a successful copy, the source is cleared and Copy stays active.
- **S-68** Scene pad colours, highest priority first: copy source, red fast blink; a clip playing on one of the 13 tracks in the window, lime tempo blink; at least one clip on those 13 tracks, white; otherwise off. Scenes past the end of the Set are off.
- **S-69** Pad 8 (hold): Shift. It is on while held and off on release. Colour: white, fast blink while held.

## 6. Mixer Mode

Mixer Mode turns columns 2–14 into one volume fader per track in the window.

- **S-70** Entering Mixer Mode releases Shift and Delete and turns on Y-axis reporting (S-4). It clears every pad on the surface once, then draws the faders. Leaving Mixer Mode (column 15, pad 5 again) turns Y-axis reporting off and redraws Session Mode. Fine-control state (S-72) is reset on both entry and exit.
- **S-71** Coarse setting: the first press in a track's column sets the track volume to one of eight steps. Pad 8 is 1/8 of the volume control's range, pad 7 is 2/8, and so on up to pad 1 at the full range. The value is Live's volume control position (0 to 1), not decibels.
- **S-72** Fine setting: while a finger stays down in a column, BleakLoop remembers the last-pressed pad as that column's band. Further presses in the same column, as the finger slides between pads, move the band without jumping the volume. The finger's Y position within the pad (0–127, S-4) then sets the volume within that band's eighth of the range. The movement is smoothed:
  - each update moves the volume by at most about 1.8 % of the range
  - changes smaller than about 0.3 % are ignored
  - when Y reports stop briefly while the finger crosses the gap between two pads, the last movement continues for up to three refresh ticks, slowing as it goes

  **(verify on device)**: the exact smoothing amounts.
- **S-73** Fader colour: a bar in the track's colour, lit from pad 8 up to the pad nearest the current volume. Any existing track shows at least pad 8 lit. A column with no track is fully off. If the track colour can't be read, the bar is cyan.
- **S-74** A fader column redraws immediately when its volume changes from a press or slide.
- **S-75** Column 15, pad 5 shows white with a fast blink and stays lit the whole time, including while faders are being moved. Every other pad in columns 1, 15 and 16 is off and does nothing in Mixer Mode.

## 7. Note Mode

In Note Mode the device is an instrument again. BleakLoop only listens to column 1 (a one-column CC Faders split, S-5) and lights its pads.

- **S-76** Each column 1 pad acts when its CC value changes. With the device's one-column toggle behaviour, every press is a change. A repeated identical value is ignored. CC values that arrive while in Session Mode are remembered but don't act.
- **S-77** Pad 1 (CC 8): Undo. Colour: white.
- **S-78** Pad 2 (CC 7): Record Clip. On the selected track, start recording into the next empty slot, searching from the highlighted scene downward and then wrapping to the top. If the track has no empty slot, a new scene is added at the end and used. Fixed Length applies (S-29, S-30), and the clip is shown in the Detail view. If the selected track is the master or a return track (not in the track list), nothing is recorded and BleakLoop posts "no selected track". If Fixed Length refuses because the transport is stopped, that warning is the one left showing. Colour: magenta.
- **S-79** Pad 3 (CC 6): Live's Capture MIDI. Colour: lime.
- **S-80** Pad 4 (CC 5): delete a clip on the selected track: the highlighted slot's clip if it has one, otherwise the first playing or recording clip on that track. If there is none, BleakLoop posts a message. Colour: red.
- **S-81** Pad 5 (CC 4): toggle the metronome. Colour: orange, fast blink while on.
- **S-82** Pad 6 (CC 3), when Live's Session View is showing: stop all clips on the selected track. Colour: green.
- **S-83** Pad 6 when Live's Arrangement View is showing: start or stop the transport. Play/Stop protection does not apply here. Colour: blue while stopped, green tempo blink while playing.
- **S-84** Pad 7 (CC 2): record, behaving and lit exactly as described in S-54 and S-55.
- **S-85** Pad 8 (CC 1): switch to Session Mode. Colour: white.
- **S-86** Column 1's lights keep updating in Note Mode on the same refresh cycle as Session Mode, and both blink styles keep running there.

## 8. LEDs and blinking

- **S-87** Colours used, by the device's own colour names and CC 22 values: red 1, yellow 2, green 3, cyan 4, blue 5, magenta 6, white 8, orange 9, lime 10, pink 11.
- **S-88** "Off" means the pad is dark. The device's table lists value 7 as off and value 0 as "as set in Note Lights settings". **(verify on device)**: which value gives a dark pad in User Firmware Mode, and in the Note Mode CC Faders split.
- **S-89** Track colour: Live's track colour (24-bit RGB) is shown as the device colour closest to it by straight-line RGB distance. The candidates are red, yellow, green, cyan, blue, magenta, white, orange, lime and pink, each with a reference RGB value tuned by eye on the device. If the track colour can't be read, a fixed rotation of device colours is used by column position.
- **S-90** Tempo blink: the pad is lit during the opening half of every beat and dark during the closing half. While the transport plays, the phase follows the song position, so blinks land on the beat. While stopped, it keeps pulsing at the Set's tempo from the system clock. It keeps running in Note Mode.
- **S-91** Fast blink: a fixed rhythm of about 200 ms on and 200 ms off, independent of tempo.
- **S-92** Refresh: BleakLoop refreshes the lights about every 200 ms. It also refreshes immediately whenever the tempo blink flips, so tempo blinks are never late by a refresh period.
- **S-93** In Session and Mixer Mode, only pads whose colour differs from the last colour sent are transmitted. This keeps every tempo-blinking pad switching on the same refresh, rather than rippling across the grid as a full resend would. In Note Mode, column 1 may be resent each refresh.
- **S-94** Switching between Session and Note Mode forgets every remembered colour, so the next draw repaints everything. The follow-up resend after entering Session Mode (S-8) does the same.

## 9. Later

Ideas not needed for parity. None of these are reachable from any pad today.

- **S-95** Launch quantization pads: one pad each for global launch quantization of a bar, a quarter, an eighth or a sixteenth, with the active choice blinking.
- **S-96** Duplicate clip: copy the most recently pressed clip (or the highlighted or playing one) into the next free slot below it on the same track, adding a scene if needed.
- **S-97** Duplicate scene: duplicate the selected scene in place and select the copy.
- **S-98** A latching scene-copy mode, separate from the held Copy pad, toggled on and off by a pad.
- **S-99** Notice when the player leaves User Firmware Mode from the device's Global Settings (the device reports this as NRPN 245 = 0 on channel 9), and treat it as switching to Note Mode.
