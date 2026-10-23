# BleakLoop architecture

How BleakLoop implements `docs/spec.md`. Only the values register exists so far; the rest is written in the architecture phase.

## Values

Every tuned number lives here with its reason and status. Code names these values as constants and never repeats them as literals. Device protocol numbers (NRPN 245, CC 11/20/21/22, colour values) are part of the device interface and are documented in spec section 3.

| Value | Used by | Source | Status |
| --- | --- | --- | --- |
| Fast blink: about 200 ms on, 200 ms off | S-91 | Tuned | Verify on device |
| Light refresh: about every 200 ms, plus an immediate refresh when the tempo blink flips | S-92 | Mechanism | Revisit in architecture |
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
