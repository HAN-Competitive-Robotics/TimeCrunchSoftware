"""Port detection and selection, with mocked serial ports.

Run:  python test_serial.py

No dearpygui/pygame import, so it runs anywhere. Proves the dongle is picked
by USB vendor ID and that a mouse on a serial port is never mistaken for it.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import serial.tools.list_ports as lp
import serial_link

fails = []


def check(name, cond, detail=""):
    print(f"  {'ok  ' if cond else 'FAIL'} {name} {detail}")
    if not cond:
        fails.append(name)


class FakePort:
    def __init__(self, device, description, hwid):
        self.device = device
        self.description = description
        self.hwid = hwid


MOUSE  = FakePort("COM3", "USB Serial Device", "USB VID:PID=046D:C077 SER=x")
DONGLE = FakePort("COM5", "USB Serial Device", "USB VID:PID=1915:520F SER=y")

# No /dev nodes on the test box should interfere with the fallback path.
serial_link.glob.glob = lambda pattern: []


def set_ports(ports):
    lp.comports = lambda: ports


# ── mouse on COM3, dongle on COM5: must pick the dongle ──────────────────────
set_ports([MOUSE, DONGLE])
check("dongle found by Nordic VID, not the mouse",
      serial_link.find_dongle_port() == "COM5", f"(got {serial_link.find_dongle_port()})")
check("mouse is not identified as the dongle", serial_link._is_dongle(MOUSE) is False)
check("Nordic VID is the dongle", serial_link._is_dongle(DONGLE) is True)
check("Zephyr VID is the dongle",
      serial_link._is_dongle(FakePort("COM6", "d", "USB VID:PID=2FE3:0100")) is True)

ports = serial_link.list_serial_ports()
check("port list flags and sorts the dongle first",
      ports[0][0] == "COM5" and ports[0][2] is True, f"(got {ports})")

# ── only the mouse present: auto must return None, never the mouse ───────────
set_ports([MOUSE])
check("no dongle -> auto returns None (does not grab the mouse)",
      serial_link.find_dongle_port() is None, f"(got {serial_link.find_dongle_port()})")

# ── runtime port override ────────────────────────────────────────────────────
set_ports([MOUSE, DONGLE])
link = serial_link.SerialLink({"serial": {"port": "auto", "baudrate": 115200}})
check("auto resolves to the dongle", link._resolve_port() == "COM5")

link.ser = object()          # pretend connected
link.port_name = "COM5"
link.state = "connected"
link.set_port("COM9")
check("set_port pins the chosen device", link.forced_port == "COM9")
check("set_port drops the live connection", link.ser is None and link.state == "searching")
check("pinned port resolves to itself", link._resolve_port() == "COM9")

link.set_port("auto")
check("set_port auto goes back to matching by ID", link._resolve_port() == "COM5")

print()
print("PASS" if not fails else f"FAIL: {fails}")
sys.exit(1 if fails else 0)
