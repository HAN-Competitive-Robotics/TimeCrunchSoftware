# Driver Station

Python script that sends control packets to the radio dongle over USB serial.

## Setup

```bash
cd driver
pip install -r requirements.txt
```

## Run

Edit the port in `main.py` to match your dongle (e.g. `COM11` on Windows, `/dev/cu.usbmodem1301` on macOS):

```python
ser = serial.Serial('/dev/cu.usbmodem1301', 115200, timeout=1)
```

Then run:

```bash
python main.py
```

## Packet Format

The script sends 4 bytes + newline every second:

```python
pkt = bytes([100, 101, 1, 0]) + b'\n'
```

- `100` → motor1 speed
- `101` → motor2 speed
- `1`   → weapon enable
- `0`   → failsafe flag
