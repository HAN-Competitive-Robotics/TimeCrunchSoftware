#!/usr/bin/env python3
"""
Simple hardware test script for the nRF52840 radio dongle.
Sends a fixed packet every second and prints the echo response.

For the full ground station GUI, use station.py instead.
"""

import sys
import time

from station import find_dongle_port


def main():
    port = sys.argv[1] if len(sys.argv) > 1 else find_dongle_port()
    if not port:
        print("Error: No dongle serial port found.")
        print("Please pass the port manually, e.g.:")
        print(f"  python {sys.argv[0]} /dev/cu.usbmodem1301")
        print(f"  python {sys.argv[0]} COM11")
        sys.exit(1)

    print(f"Using port: {port}")

    import serial
    ser = serial.Serial(port, 115200, timeout=1)

    while True:
        pkt = bytes([100, 101, 1, 0]) + b'\n'
        ser.write(pkt)

        resp = ser.readline()     # read until newline
        print("sent :", list(pkt))
        print("recv :", list(resp))

        time.sleep(1)


if __name__ == "__main__":
    main()
