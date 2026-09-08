# Driver Station

Pygame-based ground control station for the battlebot. Supports keyboard and Xbox/gamepad input with an editable control mapping.

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
```

## Drive modes

Three fixed modes. Cycle with **T** or the dropdown in the header.

| Mode | Controls |
|------|----------|
| Tank Drive | Left stick Y = left track, right stick Y = right track |
| Arcade Drive | Left stick Y = throttle, left stick X = steer |
| Rocket League | RT = forward, LT = reverse, left stick X = steer |

Rocket League steering stays live at zero throttle, so the robot can spin on
the spot. The game does not allow that; a battlebot needs it.

Shared controls in every mode:

| Function | Gamepad | Keyboard |
|----------|---------|----------|
| Weapon toggle | B10 | Space |
| Weapon attack / reverse | RT (not in Rocket League) | LShift |
| Failsafe | B1 | F |
| Arm | B6 | A |
| Drive invert | B9 | I |

Rocket League mode has no gamepad binding for weapon attack, because both
triggers are the throttle. Use LShift, or pick a free button and add it.

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

The station sends 5 bytes every 20 ms (50 Hz):

```
[motor_left] [motor_right] [weapon] [failsafe] '\n'
```

Each value is 0–255 with 127 as center for motors.

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| "Serial searching..." persists | Make sure the nRF52840 dongle is plugged in. Try unplugging and re-plugging it. |
| Gamepad not detected | Run `python station.py --calibrate` to verify the OS sees it. Try unplugging and re-plugging. |
| Keyboard inputs feel sluggish | Increase `rate` in `config.json` for that axis (default is 8). |
