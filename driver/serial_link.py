import glob
import time

try:
    import serial
    import serial.tools.list_ports
except ImportError:
    import sys
    print("ERROR: pyserial required. pip install pyserial")
    sys.exit(1)


# The dongle's USB vendor IDs: 1915 = Nordic, 2fe3 = Zephyr. This is the same
# fingerprint scripts/flash.py uses to tell the dongle from everything else. It
# is a hardware identity, so it will not match a mouse or some other USB-serial
# device that merely has a similar description string - which is exactly the
# bug the old "usb serial" keyword match caused.
DONGLE_VIDS = ("1915", "2fe3")


def _is_dongle(p) -> bool:
    hwid = (p.hwid or "").lower()
    return any(f"vid:pid={v}" in hwid for v in DONGLE_VIDS)


def list_serial_ports():
    """Every serial port as (device, description, is_dongle). Dongle(s) first,
    then alphabetical, so the UI picker can show and flag them."""
    ports = [(p.device, (p.description or "").strip() or "unknown", _is_dongle(p))
             for p in serial.tools.list_ports.comports()]
    ports.sort(key=lambda t: (not t[2], t[0]))
    return ports


def find_dongle_port():
    """The dongle's port, or None. Identified by USB vendor ID first so it can
    never grab the wrong device; the /dev globs and vendor-name descriptions are
    fallbacks for setups where the VID does not populate."""
    for p in serial.tools.list_ports.comports():
        if _is_dongle(p):
            return p.device
    for pattern in ("/dev/cu.usbmodem*", "/dev/ttyACM*"):
        matches = sorted(glob.glob(pattern))
        if matches:
            return matches[-1]
    for p in serial.tools.list_ports.comports():
        desc = (p.description or "").lower()
        if "nordic" in desc or "segger" in desc:
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
        self._last_reconnect_attempt = 0.0
        self._last_liveness_check = 0.0
        self._hz_t0 = time.time()
        self._hz_n = 0
        self._hz_current = 0.0
        # "auto" resolves to the dongle by USB ID; a specific device name
        # ("COM5", "/dev/cu.usbmodemXXXX") pins that port. The UI can change
        # this at runtime with set_port().
        self.forced_port = cfg["serial"].get("port", "auto")

    def list_ports(self):
        return list_serial_ports()

    def _resolve_port(self):
        if self.forced_port and self.forced_port != "auto":
            return self.forced_port
        return find_dongle_port()

    def set_port(self, port: str) -> None:
        """Switch to a specific device or 'auto'. Drops the current connection
        so the next ensure_connected() reopens on the new target immediately."""
        self.forced_port = port
        if self.ser is not None:
            try:
                self.ser.close()
            except Exception:
                pass
        self.ser = None
        self.port_name = None
        self.state = "searching"
        self._last_reconnect_attempt = 0.0

    def _try_open(self):
        port = self._resolve_port()
        if not port:
            return False
        try:
            self.ser = serial.Serial(port, self.cfg["serial"]["baudrate"], timeout=0.1)
            self.port_name = port
            self.state = "connected"
            self.last_ok = time.time()
            return True
        except (serial.SerialException, OSError):
            self.ser = None
            self.port_name = None
            return False

    def _drop(self, state: str) -> None:
        if self.ser is not None:
            try:
                self.ser.close()
            except Exception:
                pass
        self.ser = None
        self.port_name = None
        self.state = state

    def ensure_connected(self):
        if self.ser is None:
            now = time.time()
            if now - self._last_reconnect_attempt < 0.5:
                return False
            self._last_reconnect_attempt = now
            if self._try_open():
                return True
            self.state = "searching"
            return False

        # Windows does not reliably fail a write when a USB CDC device is
        # yanked, so a dropped dongle would otherwise still read as connected.
        # Once a second, confirm the port is still enumerated; if it vanished,
        # treat it as lost. This is what makes the dongle-removal failsafe fire
        # on Windows, not just on macOS/Linux.
        now = time.time()
        if now - self._last_liveness_check >= 1.0:
            self._last_liveness_check = now
            if not any(p.device == self.port_name
                       for p in serial.tools.list_ports.comports()):
                self._drop("lost")
                return False
        return True

    def send(self, data: bytes) -> bool:
        if self.ser is None:
            return False
        try:
            self.ser.write(data)
            self.packet_count += 1
            now = time.time()
            self.last_ok = now
            self.state = "connected"
            self._hz_n += 1
            elapsed = now - self._hz_t0
            if elapsed >= 1.0:
                self._hz_current = self._hz_n / elapsed
                self._hz_n = 0
                self._hz_t0 = now
            return True
        except (serial.SerialException, OSError):
            self._drop("lost")
            return False

    @property
    def connected(self):
        return self.ser is not None

    @property
    def idle_ms(self):
        return int((time.time() - self.last_ok) * 1000) if self.last_ok else 9999

    @property
    def current_hz(self) -> float:
        return self._hz_current
