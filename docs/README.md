# HCR Battlebot — Engineering Documentation

A gamecontroller plugged into a laptop controls a combat robot wirelessly in real time across three microcontrollers:

```
Laptop (Python) → nRF52840 Dongle (Zephyr) → ESP32 Robot (ESP-IDF)
  gamecontroller input     USB-to-radio bridge        motors + weapon + safety
```

**New here?** Start with [Architecture](architecture.md), then [Onboarding](onboarding.md).

---

## Documents

| Document | Contents |
|---|---|
| [Architecture](architecture.md) | System split, FreeRTOS tasks, safety mechanisms, hardware topology |
| [Communication](communication.md) | Packet format, serial protocol, ESB radio config, failsafe behaviour |
| [Onboarding](onboarding.md) | Tool setup, flashing, first bringup checklist, debugging |
| [Robot Firmware](firmware/robot-firmware.md) | ESP32 drivers, motor PWM, weapon PI controller |
| [Radio Dongle Firmware](firmware/radio-dongle.md) | nRF52840 Zephyr firmware: USB CDC bridge + ESB transmitter |
| [Weapon Motor Utility](firmware/weapon-motor-utility.md) | Standalone ESC calibration and motor test firmware |
| [Build and Flash](firmware/build-and-flash.md) | Build system details, `idf.py` / `west` reference |
| [Pinout](hardware/pinout.md) | Every GPIO, SPI, I²C, and PWM assignment |
| [Wiring](hardware/wiring.md) | Physical wiring for nRF24L01+, ESCs, encoder, sensors |

---

## Quick Reference

### Radio parameters (must match on both sides)

| Parameter | Value |
|---|---|
| Protocol | Nordic Enhanced ShockBurst (ESB) |
| Channel | 40 (2440 MHz) |
| Bitrate | 2 Mbps |
| Address | `1NODE` (`0x31 0x4E 0x4F 0x44 0x45`) |
| Payload | 4 bytes, fixed |
| CRC | 2 bytes |

### Packet format

```
Byte 0: motor_left   (0–255, center=127)
Byte 1: motor_right  (0–255, center=127)
Byte 2: weapon       (0=off, 1–127=idle, 128–255=attack)
Byte 3: killswitch   (0=normal, >127=deep sleep)
```

Transmitted over serial as: `[byte0][byte1][byte2][byte3]\n`

### Safety limits

| Condition | Response | Recovery |
|---|---|---|
| No packet for 500 ms | Stop all motors | Automatic on next packet |
| Killswitch byte > 127 | Deep sleep | Power cycle only |
| Any sensor ≥ 90 °C | Deep sleep | Power cycle only |
| Any motor ≥ 100 °C | Cut that motor's throttle | Automatic, 10 °C hysteresis |

---

## Repository Layout

```
esp-software/
├── driver/          Python ground station (laptop)
├── radio-dongle/    Zephyr firmware for nRF52840 dongle
├── robot/           ESP-IDF firmware for ESP32 robot controller
├── weapon-motor/    Standalone weapon ESC calibration/test utility
├── scripts/         Flash and port-detection helpers
└── docs/            This documentation
```
