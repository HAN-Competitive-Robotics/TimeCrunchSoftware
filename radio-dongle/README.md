# Radio Dongle

nRF52840 USB dongle that bridges CDC ACM serial packets to Enhanced ShockBurst (ESB) radio packets.

## Hardware

- [nRF52840 Dongle (PCA10059)](https://www.nordicsemi.com/Products/Development-hardware/nRF52840-Dongle)

## Prerequisites

- [nRF Connect SDK](https://www.nordicsemi.com/Products/Development-software/nRF-Connect-SDK) v2.7 or later
- `west` and `nrfutil` available in your PATH
- On macOS: copy `local/ncs.env.example` to `local/ncs.env` and fill in your toolchain paths

## Build & Flash

```bash
# Build only
python ../scripts/build-dongle.py

# Build + flash via USB DFU
python ../scripts/build-dongle.py flash

# Build + flash with signed DFU package
python ../scripts/build-dongle.py flash --key-file private.pem

# Clean build
python ../scripts/build-dongle.py clean
```

Or use the shell wrapper from the repo root:

```bash
./scripts/build-dongle.sh        # build only
./scripts/build-dongle.sh flash  # build + flash
```

> **Note:** The dongle must be in bootloader mode to flash. Hold the reset button while plugging it in, or use `nrfutil` directly.

### DFU Signing

If you see a warning about an *unsigned* DFU package, that is normal for development: the stock nRF52840 Dongle bootloader does not require signatures. If you need signed packages (e.g., for a custom bootloader with signature verification enabled), generate a key and pass it to the script:

```bash
nrfutil nrf5sdk-tools keys generate private.pem
python ../scripts/build-dongle.py flash --key-file private.pem
```

The corresponding public key must be programmed into the bootloader, otherwise updates will be rejected.

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

## Architecture

```
┌─────────────┐     UART FIFO      ┌─────────────┐     ring buffer     ┌─────────────┐
│  USB CDC    │  ───────────────►  │  usb_rx_thread │  ─────────────►  │  usb_rb     │
│  (host PC)  │                    │  (Zephyr)     │                   │  (512 bytes)│
└─────────────┘                    └─────────────┘                   └──────┬──────┘
                                                                           │
                                                                           ▼
                                                                    ┌─────────────┐
                                                                    │ main loop   │
                                                                    │ parses \n   │
                                                                    │ → ESB send  │
                                                                    └─────────────┘
```

The USB RX thread drains the CDC FIFO into a ring buffer and signals a semaphore. The main loop waits on the semaphore and parses complete newline-terminated messages before forwarding them over ESB.
