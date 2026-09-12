# Driver Station

DearPyGui ground control station for the battlebot. Keyboard and Xbox/gamepad
input, with all bindings fixed in code (`drive_modes.py`).

## Setup

```bash
cd driver
pip install -r requirements.txt
```

> **Note:** If you use a virtual environment, create it inside this directory (e.g. `python -m venv venv`). It is already ignored by `.gitignore`.

## Run

```bash
# Auto-detect dongle port and start ground station
python station.py

# Calibrate gamepad (see axis/button numbers)
python station.py --calibrate

# Set or clear the weapon unlock password
python station.py --set-weapon-password
```

## The screen

- **Banner** (top): the one place that states the overall state. Grey
  DISARMED, green ARMED, amber ARMED - WEAPON LIVE, red KILLSWITCH LATCHED.
- **Left card**: the controls used mid-match. ARM/DISARM, the weapon
  lock button (unlocking asks for the password), KILL ROBOT, the
  weapon/drive/kill indicators, drive mode dropdown, and the live motor
  output bars.
- **Right card**: setup and telemetry. Trim and output multipliers, the
  keybind reference (collapsed by default), and the event log, which grows
  with the window.

Buttons are labelled with the action a click performs (ARM, DISARM, UNLOCK
WEAPON); the banner and indicator pills carry the state.

## Drive modes

Two fixed modes, selected with the dropdown in the left card. There is
deliberately no keyboard shortcut for switching: a hidden key that swaps the
control layout mid-match is a hazard. Switching modes re-safes the weapon and
clears drive invert.

| Mode | Controls |
|------|----------|
| Tank Drive | Left stick Y = left track, right stick Y = right track |
| Arcade Drive | Left stick Y = forward/back, right stick X = steer |

Shared controls in every mode:

| Function | Gamepad | Keyboard |
|----------|---------|----------|
| Weapon toggle | RB (B5) | Space |
| Weapon attack / spin-up | RT | LShift |
| Killswitch | B (B1) | F |
| Arm | View (B6) | A |
| Drive invert | LB (B4) | I |

The weapon only responds while the robot is armed, the killswitch is clear,
and the weapon is unlocked. It re-locks automatically on disarm and on
killswitch. Unlock is only offered while armed (an unlock done disarmed
would be undone within a frame), the button pulses orange while the weapon
is live, and clicking it again re-locks instantly with no password.

Keyboard bindings are ignored while the unlock dialog is open or a number
box is being edited, so typing a password cannot arm, steer, or killswitch
the robot. The gamepad and the on-screen buttons stay live throughout.

## Killswitch and recovery

KILL ROBOT (click, key F, or gamepad B1) latches the killswitch: the
failsafe byte goes to 255 immediately and with every packet after, and the
robot deep sleeps until it is power cycled.

The station side stays latched on purpose. The radio link is one-way, so
the station cannot see the robot power cycle; automatic recovery would be a
guess. Once the robot has been power cycled, click RESET KILLSWITCH, which
replaces the kill button while latched. Reset returns the station to the
safest state: disarmed, weapon locked.

### Failsafe on dongle removal

`safety.failsafe_on_dongle_removal` in `config.json` (default **on**) makes
pulling the dongle a real kill. The station's serial link is to the dongle over
USB, so when the dongle leaves USB the station latches the killswitch; the
moment it is plugged back in, the robot is commanded into deep sleep. It clears
with RESET KILLSWITCH like any other kill.

This keys off USB removal only, not the radio: an RF dropout leaves the dongle
enumerated and the serial link up, so it does **not** trigger, and mid-match
radio blips stay recoverable exactly as before.

**Turn this OFF for competition matches.** During a match a momentary USB glitch
would otherwise latch the kill and permanently deep-sleep the bot mid-fight
instead of riding out the blip. It is meant for bench testing, where "unplug =
guaranteed kill" is exactly what you want.

## Weapon bench test

The right card has a collapsible **WEAPON TEST (BENCH)** section: a wireless
version of the USB weapon-motor test, so you can spin the weapon up at a set
percentage over the radio with all the normal failsafes in place.

1. Open the section and set the percentage (capped at the firmware ceiling) and
   direction.
2. Press **SPIN** - the first press asks for the weapon password.
3. The weapon spins at that percent with the **wheels forced neutral**, so the
   bot cannot drive off the bench. It ignores the ARM button; arming is refused
   while a test is running.
4. **SPIN is a deadman: re-press it within 5 seconds or the weapon stops.** The
   button shows a live countdown. STOP ends it at once.

Anything that should stop it does: the deadman lapsing, the link dropping, the
STOP button, or the killswitch (which also latches deep sleep as usual). The
robot clamps the percentage to `WEAPON_MAX_OUTPUT_PCT` regardless of what the
station sends, and a throttle percentage is not a kinetic-energy figure - see
`docs/hardware/weapon-limits.md` before trusting any particular number.

## Changing controls

Bindings live in `drive_modes.py`. Edit that file and restart; there is no
in-app editor. This is deliberate: rebindable profiles meant every laptop
drifted to a different layout and nobody could say what a given button did
without opening someone's `profiles.json`.

To find axis and button numbers for your pad:

```bash
python station.py --calibrate
```

## Packet Format

The station sends one line of ASCII hex at 50 Hz (`rate_hz` in
`config.json`):

```
"7f7f7f00\n"
 |  |  |  |
 ml mr wb fs      two hex digits each
```

Motor bytes are 0-255 with 127 as centre. Weapon bytes: 127 safe, 160 idle,
255 attack, 95 held forward spin-up ramp. Failsafe byte 255 latches the robot into deep
sleep until power cycled; 0 otherwise.

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| "Serial searching..." persists | Make sure the nRF52840 dongle is plugged in. Try unplugging and re-plugging it. |
| Gamepad not detected | Run `python station.py --calibrate` to verify the OS sees it. Try unplugging and re-plugging. |
| Keyboard driving feels sluggish | Raise `KB_RATE` in `drive_modes.py` (motor bytes per frame while a key is held, default 8). |
| Text looks tiny and pixelated | No system font was found, so the built-in bitmap font is in use. On WSL/Ubuntu: `sudo apt install fonts-dejavu-core` and restart the station. |
