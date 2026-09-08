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
  lock button (unlocking asks for the password), the weapon/drive/kill
  indicators, drive mode dropdown, and the live motor output bars.
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
| Weapon toggle | B10 | Space |
| Weapon attack / reverse | RT | LShift |
| Killswitch | B1 | F |
| Arm | B6 | A |
| Drive invert | B9 | I |

The weapon only responds while the robot is armed, the killswitch is clear,
and the weapon is unlocked. It re-locks automatically on disarm and on
killswitch.

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
255 attack, 95 reverse idle. Failsafe byte 255 latches the robot into deep
sleep until power cycled; 0 otherwise.

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| "Serial searching..." persists | Make sure the nRF52840 dongle is plugged in. Try unplugging and re-plugging it. |
| Gamepad not detected | Run `python station.py --calibrate` to verify the OS sees it. Try unplugging and re-plugging. |
| Keyboard driving feels sluggish | Raise `KB_RATE` in `drive_modes.py` (motor bytes per frame while a key is held, default 8). |
| Text looks tiny and pixelated | No system font was found, so the built-in bitmap font is in use. On WSL/Ubuntu: `sudo apt install fonts-dejavu-core` and restart the station. |
