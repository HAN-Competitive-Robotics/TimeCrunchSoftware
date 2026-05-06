# Radio Dongle

nRF52840 USB dongle that bridges CDC ACM serial packets to Enhanced ShockBurst (ESB) radio packets.

## Hardware

- [nRF52840 Dongle](https://www.nordicsemi.com/Products/Development-hardware/nRF52840-Dongle)

## Build & Flash

```bash
cd radio-dongle
bash build.sh        # build only
bash build.sh flash  # build + flash via USB DFU
```

> **Note:** The dongle must be in bootloader mode to flash. Hold the reset button while plugging in, or use `nrfutil` directly.

## USB Protocol

Send 4 bytes + newline (`\n`) over USB CDC at 115200 baud:

```
motor1 motor2 weapon failsafe\n
# Example:
100 101 1 0\n
# Values are raw bytes (0-255)
```

The dongle echoes the first 4 bytes back as confirmation.

## ESB Config

| Parameter | Value |
|-----------|-------|
| Mode | PTX (Primary Transmitter) |
| Channel | 40 |
| Bitrate | 1 Mbps |
| Address | `1NODE` |
| Payload | 4 bytes |
| CRC | 2 bytes |
