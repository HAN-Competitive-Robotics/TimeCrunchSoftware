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

## Controls (default)

| Function | Gamepad | Keyboard |
|----------|---------|----------|
| Left motor | Left stick Y | W / S |
| Right motor | Right stick Y | UP / DOWN |
| Weapon | RB | Space |
| Failsafe | B | F |

> **Note:** `F` triggers failsafe. `ESC` quits the application.

## Edit Controls

Open `config.json` and change the mapping without touching code:

```json
{
  "inputs": {
    "motor_left": {
      "type": "axis",
      "gamepad": { "axis": 1, "invert": true, "deadzone": 0.15 },
      "keyboard": { "positive": "w", "negative": "s", "rate": 8 }
    },
    "weapon": {
      "type": "button",
      "gamepad": { "button": 5 },
      "keyboard": "space",
      "off_value": 0,
      "on_value": 255
    }
  }
}
```

Run `python station.py --calibrate` to discover your gamepad's axis and button numbers.

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
