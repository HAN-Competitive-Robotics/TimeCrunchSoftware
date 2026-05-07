# Battlebot Radio Control

One-way radio control system for a battlebot using Nordic ESB (Enhanced ShockBurst).

```
┌─────────────────┐      USB CDC      ┌─────────────────┐     2.4 GHz ESB     ┌─────────────────┐
│  Driver Station │  ──────────────►  │  nRF52840 Dongle │  ──────────────►  │  ESP32 + nRF24  │
│  (Python/Pygame)│   115200 baud     │  (radio-dongle/) │    Channel 40     │  (robot/)       │
└─────────────────┘                   └─────────────────┘                   └─────────────────┘
                                                                             │  • Motor drivers
                                                                             │  • Weapon PI ctrl
                                                                             │  • Temp sensors
                                                                             │  • Encoder RPM
```

## Structure

| Directory | Hardware | Stack | Role |
|-----------|----------|-------|------|
| [`radio-dongle/`](radio-dongle/) | nRF52840 USB Dongle | Zephyr RTOS + Nordic ESB | Bridges USB CDC serial → 2.4 GHz radio |
| [`robot/`](robot/) | ESP32 DevKit + nRF24L01+ | ESP-IDF (FreeRTOS) | Receives packets, drives motors / weapon |
| [`driver/`](driver/) | Laptop | Python + Pygame + PySerial | Ground station with gamepad / keyboard input |

## Prerequisites

### All platforms

- Python 3.10+ with `pyserial` and `pygame`:
  ```bash
  pip3 install pyserial pygame
  ```

### ESP32 receiver (`robot/`)

- [ESP-IDF](https://docs.espressif.com/projects/esp-idf/en/latest/esp32/get-started/index.html) installed at `~/esp/esp-idf`
- ESP32 DevKit
- nRF24L01+ radio module

### nRF52840 dongle (`radio-dongle/`)

- [nRF Connect SDK](https://www.nordicsemi.com/Products/Development-software/nRF-Connect-SDK) (v2.7+ recommended)
- `west` and `nrfutil` in your PATH (or configured via `radio-dongle/local/ncs.env`)
- nRF52840 Dongle (PCA10059)

## Quick Start

Flash both devices and open the robot monitor. Ports are auto-detected on all platforms.

**Any OS:**
```bash
python scripts/flash.py                    # interactive menu
python scripts/flash.py --both             # competition build
python scripts/flash.py --both --telemetry # test build with RF telemetry
```

---

## Flash Individually

### ESP32 receiver

```bash
./robot/idf -p $(python scripts/find-ports.py | grep FIRST_ESP32 | cut -d= -f2) flash monitor
```

If auto-detection fails, pass the port manually:
```bash
./robot/idf -p /dev/cu.usbserial-0001 flash monitor
```

### nRF52840 dongle

```bash
# Build only
python scripts/build-dongle.py

# Build + flash via USB DFU
python scripts/build-dongle.py flash
```

> **Note:** The dongle must be in bootloader mode to flash. Hold the reset button while plugging it in, or use `nrfutil` directly.

---

## Auto-Detect Ports

```bash
python scripts/find-ports.py
```

---

## Radio Config

| Parameter | Value |
|-----------|-------|
| **Protocol** | Enhanced ShockBurst (ESB) |
| **Channel** | 40 |
| **Bitrate** | 2 Mbps |
| **Payload** | 4 bytes |
| **Address** | `1NODE` (5 bytes) |
| **CRC** | 2 bytes |

## Packet Format

The driver station sends 5 bytes at 50 Hz:

```
[motor_left] [motor_right] [weapon] [failsafe] '\n'
```

Each value is a raw byte (`0–255`). Center for motors is `127`.

| Byte | Meaning | Range |
|------|---------|-------|
| 0 | Left motor throttle | 0–255 (127 = stop) |
| 1 | Right motor throttle | 0–255 (127 = stop) |
| 2 | Weapon throttle | 0 = off, 1–127 = idle, 128–255 = attack |
| 3 | Failsafe trigger | 0 = normal, 255 = stop all |

---

## Safety Features

- **500 ms packet timeout** — If the robot receives no packets for 500 ms, all motors stop automatically.
- **Failsafe button** — Holding the failsafe button (gamepad B / keyboard `F`) immediately stops all motors.
- **Thermal cutoff** — If any motor temperature exceeds 100 °C (or a sensor fails / returns NAN), throttle is cut to 0.
- **Weapon PI controller** — Closed-loop speed control with anti-windup (tune `WEAPON_KP` / `WEAPON_KI` in `weapon_controller.h`).

---

## RF Telemetry (Test Mode)

During testing, the robot sends temperature and weapon RPM back to the ground station via nRF24 ACK payloads. This feature is compile-time gated — competition builds have zero overhead and the radio protocol is unchanged.

**What you see in the ground station:**

```
RF TELEM  L:42.3°C  R:41.8°C  W:38.1°C  RPM:8420
```

Displayed in the GUI at 1 Hz, below the packet stats line. Absent in competition builds since no frames are sent.

**To flash a telemetry build:**

```bash
# Interactive menu — choose option 4
python scripts/flash.py

# Or directly
python scripts/flash.py --both --telemetry
```

**Telemetry payload (16 bytes, sent back with every ACK):**

| Bytes | Type | Field |
|-------|------|-------|
| 0–3 | float32 LE | Left wheel temperature (°C) |
| 4–7 | float32 LE | Right wheel temperature (°C) |
| 8–11 | float32 LE | Weapon temperature (°C) |
| 12–15 | float32 LE | Weapon RPM |

**What changes in telemetry mode:**

| | Competition | Telemetry |
|---|---|---|
| ESB mode | Fixed payload, no-ACK | Dynamic payload (DPL), ACK enabled |
| nRF24 FEATURE | `0x00` | `EN_DPL \| EN_ACK_PAY` |
| Build directory | `build/` | `build_telemetry/` |
| Packet overhead | None | ~1 round-trip per packet |

Telemetry builds use separate build directories on both sides so you can switch modes without a full rebuild.

**To return to a competition build:**

```bash
python scripts/flash.py --both
```

---

## Troubleshooting

| Symptom | Likely Cause | Fix |
|---------|--------------|-----|
| `ModuleNotFoundError: No module named 'serial'` | `pyserial` not installed | `pip3 install pyserial` |
| `ESP-IDF not found at ~/esp/esp-idf` | ESP-IDF installed elsewhere or not installed | Set `IDF_PATH` or reinstall ESP-IDF to `~/esp/esp-idf` |
| `west not found in PATH` | nRF Connect SDK environment not activated | Run `ncs-env` or copy `radio-dongle/local/ncs.env.example` to `ncs.env` and fill in paths |
| Dongle flashes but robot doesn't respond | Wrong channel / address mismatch | Verify both firmwares use channel 40 and address `1NODE` |
| Robot stops after ~500 ms | Packet timeout triggered | Check that the driver station is running and the dongle is plugged in |
| Ground station quits when pressing Escape | Escape is mapped to quit in Pygame | Use `F` for failsafe (changed in recent versions) |

---

## Development

### Formatting

This repo uses Prettier for non-code files (JSON, YAML, Markdown). Run before committing:

```bash
npx prettier --write .
```

### Project Layout

```
├── radio-dongle/      # Zephyr project for nRF52840
│   ├── src/            # main.c, esb_ptx.c, usb.c
│   ├── CMakeLists.txt
│   └── prj.conf        # Zephyr Kconfig
├── robot/              # ESP-IDF project for ESP32
│   ├── main/src/       # Application code
│   ├── main/include/   # Headers
│   └── sdkconfig       # ESP-IDF config (auto-generated)
├── driver/             # Python ground station
│   ├── station.py      # Main GUI application
│   ├── config.json     # Control mapping
│   └── requirements.txt
└── scripts/            # Cross-platform build & flash helpers
    ├── build-dongle.py
    ├── flash.py
    └── find-ports.py
```
