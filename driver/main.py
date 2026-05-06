import serial
import serial.tools.list_ports
import time
import glob
import sys


def find_dongle_port():
    """Auto-detect the nRF52840 dongle CDC serial port."""
    # macOS
    ports = glob.glob("/dev/cu.usbmodem*") + glob.glob("/dev/tty.usbmodem*")
    # Linux
    ports += glob.glob("/dev/ttyACM*")
    # Windows — try to find Nordic / Segger / USB CDC devices
    if not ports:
        for p in serial.tools.list_ports.comports():
            desc = (p.description or "").lower()
            hwid = (p.hwid or "").lower()
            if any(k in desc or k in hwid for k in ["nordic", "segger", "usb cdc", "usb serial"]):
                ports.append(p.device)
    if not ports:
        print("Error: No dongle serial port found.")
        print("Please pass the port manually, e.g.:")
        print(f"  python {sys.argv[0]} /dev/cu.usbmodem1301")
        print(f"  python {sys.argv[0]} COM11")
        sys.exit(1)
    return ports[0]


PORT = sys.argv[1] if len(sys.argv) > 1 else find_dongle_port()
print(f"Using port: {PORT}")

ser = serial.Serial(PORT, 115200, timeout=1)

while True:
    pkt = bytes([100, 101, 1, 0]) + b'\n'
    ser.write(pkt)

    resp = ser.readline()     # read until newline
    print("sent :", list(pkt))
    print("recv :", list(resp))

    time.sleep(1)
