#!/usr/bin/env python3
"""
Battlebot Ground Station
Cross-platform driver station with keyboard + Xbox/gamepad support.
Edit config.json to change controls without touching code.
"""

import argparse
import json
import os
import sys
import time
from collections import deque
from pathlib import Path

# ---------------------------------------------------------------------------
# Pygame & serial are external dependencies
# ---------------------------------------------------------------------------
try:
    import pygame
except ImportError:
    print("ERROR: pygame is required. Install it with: pip install pygame")
    sys.exit(1)

try:
    import serial
    import serial.tools.list_ports
except ImportError:
    print("ERROR: pyserial is required. Install it with: pip install pyserial")
    sys.exit(1)


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
SCRIPT_DIR = Path(__file__).resolve().parent
CONFIG_PATH = SCRIPT_DIR / "config.json"


def load_config(path=CONFIG_PATH):
    with open(path, "r") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Serial helpers
# ---------------------------------------------------------------------------
def find_dongle_port():
    """Auto-detect the nRF52840 dongle CDC serial port."""
    import glob

    # macOS
    ports = glob.glob("/dev/cu.usbmodem*") + glob.glob("/dev/tty.usbmodem*")
    # Linux
    ports += glob.glob("/dev/ttyACM*")
    if ports:
        return ports[0]

    # Windows / generic fallback by description
    for p in serial.tools.list_ports.comports():
        desc = (p.description or "").lower()
        hwid = (p.hwid or "").lower()
        if any(k in desc or k in hwid for k in ["nordic", "segger", "usb cdc", "usb serial"]):
            return p.device

    return None


class SerialLink:
    def __init__(self, cfg):
        self.cfg = cfg
        self.ser = None
        self.port_name = None
        self.packet_count = 0
        self.last_ok = 0
        self.state = "searching"  # searching | connected | lost

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

    def send(self, data):
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


# ---------------------------------------------------------------------------
# Input mapping
# ---------------------------------------------------------------------------
def _resolve_key(name):
    """Resolve a key name like 'space' or 'lshift' to a pygame key constant."""
    if not name:
        return None
    key = getattr(pygame, f"K_{name.upper()}", None)
    if key is not None:
        return key
    # Fallback for a few common aliases not following the K_<name> pattern
    aliases = {
        "return": pygame.K_RETURN,
        "enter": pygame.K_RETURN,
        "escape": pygame.K_ESCAPE,
        "up": pygame.K_UP,
        "down": pygame.K_DOWN,
        "left": pygame.K_LEFT,
        "right": pygame.K_RIGHT,
    }
    return aliases.get(name.lower())


class InputMapper:
    def __init__(self, cfg):
        self.cfg = cfg
        self.joystick = None
        self.joystick_name = None
        self.keyboard_axis_state = {}
        self._scan_gamepads()

    def _scan_gamepads(self):
        pygame.joystick.init()
        count = pygame.joystick.get_count()
        if count > 0:
            self._attach(0)
        else:
            self.joystick = None
            self.joystick_name = None

    def _attach(self, device_index):
        try:
            self.joystick = pygame.joystick.Joystick(device_index)
            self.joystick.init()
            self.joystick_name = self.joystick.get_name()
        except pygame.error:
            self.joystick = None
            self.joystick_name = None

    def _detach(self):
        self.joystick = None
        self.joystick_name = None

    def handle_event(self, event):
        if event.type == pygame.JOYDEVICEADDED:
            self._attach(event.device_index)
            return f"Gamepad connected: {self.joystick_name}"
        elif event.type == pygame.JOYDEVICEREMOVED:
            name = self.joystick_name or "?"
            self._detach()
            return f"Gamepad disconnected: {name}"
        return None

    def read_axis(self, name, keys):
        spec = self.cfg["inputs"][name]
        center = self.cfg["packet"]["center"]
        range_min, range_max = self.cfg["packet"]["range"]

        value = center

        # Gamepad axis
        if self.joystick and "gamepad" in spec:
            gp = spec["gamepad"]
            try:
                raw = self.joystick.get_axis(gp["axis"])
            except pygame.error:
                self._detach()
                raw = 0.0
            if gp.get("invert", False):
                raw = -raw
            deadzone = gp.get("deadzone", 0.0)
            if abs(raw) < deadzone:
                raw = 0.0
            else:
                raw = (abs(raw) - deadzone) / (1.0 - deadzone) * (1.0 if raw > 0 else -1.0)
            # expo
            expo = spec.get("expo", 0.0)
            if expo:
                raw = raw * (1.0 - expo) + (raw ** 3) * expo
            value = center + raw * ((range_max - range_min) / 2.0)
            return int(max(range_min, min(range_max, value)))

        # Keyboard axis
        if "keyboard" in spec:
            kb = spec["keyboard"]
            pos_key = _resolve_key(kb["positive"])
            neg_key = _resolve_key(kb["negative"])
            rate = kb.get("rate", 8)

            current = self.keyboard_axis_state.get(name, center)
            if pos_key and keys[pos_key]:
                current = min(current + rate, range_max)
            elif neg_key and keys[neg_key]:
                current = max(current - rate, range_min)
            else:
                if current > center:
                    current = max(current - rate, center)
                elif current < center:
                    current = min(current + rate, center)
            self.keyboard_axis_state[name] = current
            return int(current)

        return center

    def read_button(self, name, keys):
        spec = self.cfg["inputs"][name]
        off = spec.get("off_value", 0)
        on = spec.get("on_value", 255)

        # Gamepad button
        if self.joystick and "gamepad" in spec:
            try:
                gp = spec["gamepad"]
                if "button" in gp:
                    if self.joystick.get_button(gp["button"]):
                        return on
                elif "axis" in gp:
                    val = self.joystick.get_axis(gp["axis"])
                    threshold = gp.get("threshold", 0.5)
                    if val > threshold:
                        return on
            except pygame.error:
                self._detach()

        # Keyboard button
        if "keyboard" in spec:
            k = _resolve_key(spec["keyboard"])
            if k and keys[k]:
                return on

        return off


# ---------------------------------------------------------------------------
# GUI
# ---------------------------------------------------------------------------
class GUI:
    def __init__(self, cfg):
        pygame.init()
        pygame.display.set_caption("Battlebot Ground Station")
        self.screen = pygame.display.set_mode((cfg["ui"]["width"], cfg["ui"]["height"]))
        self.clock = pygame.time.Clock()
        self.font = pygame.font.SysFont("monospace", 16)
        self.font_big = pygame.font.SysFont("monospace", 24)
        self.font_small = pygame.font.SysFont("monospace", 12)
        self.theme = cfg["ui"]["theme"]
        self.log = deque(maxlen=6)

    def _c(self, name):
        return self.theme.get(name, [255, 255, 255])

    def _txt(self, text, color_name, pos, big=False, small=False):
        font = self.font_big if big else (self.font_small if small else self.font)
        surf = font.render(text, True, self._c(color_name))
        self.screen.blit(surf, pos)

    def _rect(self, color_name, rect, width=0):
        pygame.draw.rect(self.screen, self._c(color_name), rect, width, border_radius=4)

    def _hline(self, y, color_name="panel"):
        pygame.draw.line(self.screen, self._c(color_name), (20, y), (780, y), 1)

    def _bar(self, x, y, w, h, value, center, range_min, range_max, label, color="accent"):
        self._rect("panel", (x, y, w, h))
        cx = x + w * (center - range_min) / (range_max - range_min)
        pygame.draw.line(self.screen, self._c("text"), (cx, y), (cx, y + h), 2)
        if value != center:
            if value > center:
                vx = cx
                vw = w * (value - center) / (range_max - range_min)
            else:
                vx = x + w * (value - range_min) / (range_max - range_min)
                vw = cx - vx
            pygame.draw.rect(self.screen, self._c(color), (vx, y + 4, max(2, vw), h - 8), border_radius=2)
        self._txt(label, "text", (x, y - 18))
        self._txt(f"{value}", "text", (x + w + 10, y + 4))

    def add_log(self, msg):
        self.log.append(f"[{time.strftime('%H:%M:%S')}] {msg}")

    def draw(self, link, mapper, values, runtime_ms):
        self.screen.fill(self._c("bg"))

        # Header
        self._txt("BATTLEBOT GROUND STATION", "accent", (20, 10), big=True)

        # Serial status block
        if link.state == "connected":
            serial_color = "good"
            serial_text = f"● SERIAL OK  ({link.port_name})"
        elif link.state == "searching":
            serial_color = "warning"
            serial_text = "● SERIAL SEARCHING..."
        else:
            serial_color = "danger"
            serial_text = "● SERIAL LOST"
        self._txt(serial_text, serial_color, (20, 42))

        # Gamepad status block
        if mapper.joystick_name:
            gp_color = "good"
            gp_text = f"🎮 {mapper.joystick_name}"
        else:
            gp_color = "warning"
            gp_text = "⌨ KEYBOARD ONLY (no gamepad)"
        self._txt(gp_text, gp_color, (400, 42))

        self._hline(72)

        # Motor bars
        center = 127
        rmin, rmax = 0, 255
        self._bar(80, 100, 300, 30, values.get("motor_left", center), center, rmin, rmax, "LEFT MOTOR")
        self._bar(80, 170, 300, 30, values.get("motor_right", center), center, rmin, rmax, "RIGHT MOTOR")

        # Weapon / Failsafe indicators
        weapon_on = values.get("weapon", 0) > 127
        failsafe_on = values.get("failsafe", 0) > 127

        w_color = "danger" if weapon_on else "panel"
        self._rect(w_color, (420, 100, 160, 40))
        w_txt = "WEAPON ARMED" if weapon_on else "WEAPON SAFE"
        self._txt(w_txt, "text", (440, 108))

        f_color = "danger" if failsafe_on else "panel"
        self._rect(f_color, (420, 160, 160, 40))
        f_txt = "FAILSAFE ACTIVE" if failsafe_on else "NORMAL"
        self._txt(f_txt, "text", (440, 168))

        # Stats
        hz = link.packet_count / (runtime_ms / 1000.0) if runtime_ms > 0 else 0
        self._txt(
            f"Pkts: {link.packet_count}  |  Rate: {hz:.1f} Hz  |  Idle: {link.idle_ms} ms",
            "text",
            (20, 220),
            small=True,
        )

        # Event log
        self._hline(255)
        self._txt("EVENT LOG", "accent", (20, 265))
        ly = 285
        for entry in self.log:
            self._txt(entry, "text", (20, ly), small=True)
            ly += 16

        # Controls legend
        self._hline(380)
        self._txt("CONTROLS", "accent", (20, 390))
        self._txt("Gamepad:  Left stick Y = Left motor    Right stick Y = Right motor", "text", (20, 412), small=True)
        self._txt("          RB = Weapon                    B = Failsafe", "text", (20, 428), small=True)
        self._txt("Keyboard: W/S = Left motor    UP/DOWN = Right motor", "text", (20, 444), small=True)
        self._txt("          SPACE = Weapon      F = Failsafe    ESC = Exit", "text", (20, 460), small=True)

        pygame.display.flip()


# ---------------------------------------------------------------------------
# Calibration helper
# ---------------------------------------------------------------------------
def calibrate():
    pygame.init()
    pygame.joystick.init()
    print("=== Gamepad Calibration ===")
    print("Move sticks and press buttons. Press ESC to quit.\n")

    clock = pygame.time.Clock()
    screen = pygame.display.set_mode((600, 400))
    pygame.display.set_caption("Gamepad Calibration")
    font = pygame.font.SysFont("monospace", 16)

    js = None
    if pygame.joystick.get_count() > 0:
        js = pygame.joystick.Joystick(0)
        js.init()
        print(f"Connected: {js.get_name()}")
        print(f"Axes: {js.get_numaxes()}  Buttons: {js.get_numbuttons()}  Hats: {js.get_numhats()}")
    else:
        print("No gamepad connected. Plug one in to see live data.")

    running = True
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                running = False
            if event.type == pygame.JOYDEVICEADDED:
                js = pygame.joystick.Joystick(event.device_index)
                js.init()
                print(f"Connected: {js.get_name()}")
            if event.type == pygame.JOYDEVICEREMOVED:
                js = None

        screen.fill((30, 30, 35))
        y = 20

        if js:
            for i in range(js.get_numaxes()):
                val = js.get_axis(i)
                col = (0, 200, 255) if abs(val) > 0.1 else (220, 220, 220)
                txt = font.render(f"Axis {i}: {val:+.3f}", True, col)
                screen.blit(txt, (20, y))
                y += 22

            y += 10
            buttons = [js.get_button(i) for i in range(js.get_numbuttons())]
            btn_str = "  ".join(f"B{i}={'ON' if v else 'off'}" for i, v in enumerate(buttons))
            for line in [btn_str[j:j+80] for j in range(0, len(btn_str), 80)]:
                txt = font.render(line, True, (220, 220, 220))
                screen.blit(txt, (20, y))
                y += 22
        else:
            txt = font.render("No gamepad connected.", True, (255, 60, 60))
            screen.blit(txt, (20, y))

        pygame.display.flip()
        clock.tick(30)

    pygame.quit()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Battlebot Ground Station")
    parser.add_argument("--calibrate", action="store_true", help="Show gamepad axis/button numbers")
    args = parser.parse_args()

    if args.calibrate:
        calibrate()
        return

    cfg = load_config()

    # Init pygame
    pygame.init()
    gui = GUI(cfg)
    mapper = InputMapper(cfg)
    link = SerialLink(cfg)

    # Initial connection attempt
    if link.ensure_connected():
        gui.add_log(f"Serial connected: {link.port_name}")
    else:
        gui.add_log("Serial searching...")

    if mapper.joystick_name:
        gui.add_log(f"Gamepad: {mapper.joystick_name}")
    else:
        gui.add_log("No gamepad — keyboard only")

    packet_order = cfg["packet"]["order"]
    rate_hz = cfg["serial"]["rate_hz"]

    running = True
    start_time = pygame.time.get_ticks()
    last_send = 0

    while running:
        now = pygame.time.get_ticks()

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                running = False

            msg = mapper.handle_event(event)
            if msg:
                gui.add_log(msg)

        keys = pygame.key.get_pressed()

        # Read all inputs
        values = {}
        for name, spec in cfg["inputs"].items():
            if spec["type"] == "axis":
                values[name] = mapper.read_axis(name, keys)
            else:
                values[name] = mapper.read_button(name, keys)

        # Weapon logic: off=0, idle=64, attack=255
        weapon_base = values.get("weapon", 0)
        weapon_rev = values.get("weapon_rev", 0)

        if weapon_base == 0:
            weapon_byte = 0
        elif weapon_rev > 127:
            weapon_byte = 255
        else:
            weapon_byte = 64

        packet = bytes([
            values.get("motor_left", 127),
            values.get("motor_right", 127),
            weapon_byte,
            values.get("failsafe", 0),
        ]) + b"\n"

        # Send at configured rate
        if now - last_send >= 1000 / rate_hz:
            was_searching = link.state == "searching"
            if link.ensure_connected():
                if was_searching:
                    gui.add_log(f"Serial connected: {link.port_name}")
                if link.send(packet):
                    pass  # ok
                else:
                    gui.add_log("Serial write failed")
            last_send = now

        # Draw
        elapsed = now - start_time
        gui.draw(link, mapper, values, elapsed)
        gui.clock.tick(rate_hz)

    pygame.quit()
    print("Ground station shut down.")


if __name__ == "__main__":
    main()
