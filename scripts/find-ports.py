#!/usr/bin/env python3
"""Cross-platform serial port finder for battlebot hardware."""

import sys
import serial.tools.list_ports


def is_esp32(port):
    desc = (port.description or "").lower()
    hwid = (port.hwid or "").lower()
    return any(
        k in desc or k in hwid
        for k in ["cp210", "ch340", "ch341", "ftdi", "usb-uart", "usb serial"]
    )


def is_dongle(port):
    desc = (port.description or "").lower()
    hwid = (port.hwid or "").lower()
    return any(
        k in desc or k in hwid
        for k in ["nordic", "segger", "j-link", "usb cdc", "nrf52", "nrf52840"]
    )


def find_ports():
    esp32 = []
    dongle = []
    other = []

    for p in serial.tools.list_ports.comports():
        if is_esp32(p):
            esp32.append(p)
        elif is_dongle(p):
            dongle.append(p)
        else:
            other.append(p)

    # macOS / Linux fallback pattern matching when description is empty
    if sys.platform == "darwin":
        for p in serial.tools.list_ports.comports():
            if p in esp32 or p in dongle:
                continue
            dev = p.device.lower()
            if "usbserial" in dev or "tty.usbserial" in dev:
                esp32.append(p)
            elif "usbmodem" in dev or "tty.usbmodem" in dev:
                dongle.append(p)
    elif sys.platform.startswith("linux"):
        for p in serial.tools.list_ports.comports():
            if p in esp32 or p in dongle:
                continue
            dev = p.device.lower()
            if "ttyusb" in dev:
                esp32.append(p)
            elif "ttyacm" in dev:
                dongle.append(p)

    return esp32, dongle, other


def main():
    esp32, dongle, other = find_ports()

    print("=== Detected serial ports ===")

    if esp32:
        print("ESP32 (robot):")
        for p in esp32:
            print(f"  {p.device:<20} {p.description}")
    else:
        print("ESP32 (robot):    none found")

    if dongle:
        print("nRF52840 dongle:")
        for p in dongle:
            print(f"  {p.device:<20} {p.description}")
    else:
        print("nRF52840 dongle:  none found")

    if other:
        print("Other ports:")
        for p in other:
            print(f"  {p.device:<20} {p.description}")

    # Return first found port as convenience for shell callers
    if esp32:
        print(f"\nFIRST_ESP32={esp32[0].device}")
    if dongle:
        print(f"FIRST_DONGLE={dongle[0].device}")


if __name__ == "__main__":
    main()
