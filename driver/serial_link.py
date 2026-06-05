import glob
import time

try:
    import serial
    import serial.tools.list_ports
except ImportError:
    import sys
    print("ERROR: pyserial required. pip install pyserial")
    sys.exit(1)


def find_dongle_port():
    ports = sorted(glob.glob("/dev/cu.usbmodem*"))
    if ports:
        return ports[-1]
    linux = sorted(glob.glob("/dev/ttyACM*"))
    if linux:
        return linux[-1]
    for p in serial.tools.list_ports.comports():
        desc = (p.description or "").lower()
        hwid = (p.hwid or "").lower()
        if any(k in desc or k in hwid for k in ["nordic", "segger", "usb cdc", "usb serial"]):
            return p.device
    return None


class SerialLink:
    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.ser = None
        self.port_name = None
        self.packet_count = 0
        self.last_ok = 0
        self.state = "searching"

    def _try_open(self):
        port = self.cfg["serial"]["port"]
        if port == "auto":
            port = find_dongle_port()
        if not port:
            return False
        try:
            self.ser = serial.Serial(port, self.cfg["serial"]["baudrate"], timeout=0.1)
            self.port_name = port
            self.state = "connected"
            self.last_ok = time.time()
            return True
        except serial.SerialException:
            self.ser = None
            self.port_name = None
            return False

    def ensure_connected(self):
        if self.ser is None:
            if self._try_open():
                return True
            self.state = "searching"
            return False
        return True

    def send(self, data: bytes) -> bool:
        if self.ser is None:
            return False
        try:
            self.ser.write(data)
            self.packet_count += 1
            self.last_ok = time.time()
            self.state = "connected"
            return True
        except serial.SerialException:
            self.ser.close()
            self.ser = None
            self.state = "lost"
            return False

    @property
    def connected(self):
        return self.ser is not None

    @property
    def idle_ms(self):
        return int((time.time() - self.last_ok) * 1000) if self.last_ok else 9999
