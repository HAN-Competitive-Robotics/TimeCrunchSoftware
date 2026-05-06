# Battlebot Radio Control

One-way radio control system for a battlebot using Nordic ESB (Enhanced ShockBurst).

## Structure

| Directory | Hardware | Role |
|-----------|----------|------|
| [`radio-dongle/`](radio-dongle/) | nRF52840 USB Dongle | Transmits control packets from laptop USB → 2.4 GHz |
| [`robot/`](robot/) | ESP32 + nRF24L01 | Receives packets and drives motors / weapon |
| [`driver/`](driver/) | Python script on laptop | Sends serial commands to the radio dongle |

## Quick Start

Flash both devices and open the robot monitor:

```bash
# From repo root
./scripts/flash-all.sh
```

Or flash individually:

```bash
# ESP32 receiver
cd robot
source ~/esp/esp-idf/export.sh
idf.py -p /dev/cu.usbserial-0001 flash monitor

# nRF52840 dongle
cd radio-dongle
bash build.sh flash
```

## Radio Config

- **Protocol:** Enhanced ShockBurst (ESB)
- **Channel:** 40
- **Bitrate:** 1 Mbps
- **Payload:** 4 bytes (`motor1`, `motor2`, `weapon`, `failsafe`)
- **Address:** `1NODE` (5 bytes)
