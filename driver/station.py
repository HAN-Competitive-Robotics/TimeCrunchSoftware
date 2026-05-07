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
        self.screen = pygame.display.set_mode(
            (cfg["ui"]["width"], cfg["ui"]["height"]), pygame.RESIZABLE
        )
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
        sw = self.screen.get_width()
        lm = int(0.025 * sw)
        pygame.draw.line(self.screen, self._c(color_name), (lm, y), (sw - lm, y), 1)

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

    def _ind(self, color_name, rect, text):
        """Filled indicator box with horizontally and vertically centred text."""
        self._rect(color_name, rect)
        x, y, w, h = rect
        surf = self.font.render(text, True, self._c("text"))
        tw, th = surf.get_size()
        self.screen.blit(surf, (x + (w - tw) // 2, y + (h - th) // 2))

    def add_log(self, msg):
        self.log.append(f"[{time.strftime('%H:%M:%S')}] {msg}")

    def draw(self, link, mapper, values, runtime_ms, drive_inverted=False, armed=False):
        sw, sh = self.screen.get_size()
        self.screen.fill(self._c("bg"))
        lm = int(0.025 * sw)

        # ── Header ──────────────────────────────────────────────────────────
        self._txt("BATTLEBOT GROUND STATION", "accent", (lm, int(0.02 * sh)), big=True)

        sy = int(0.088 * sh)
        if link.state == "connected":
            self._txt(f"● SERIAL OK  ({link.port_name})", "good", (lm, sy))
        elif link.state == "searching":
            self._txt("● SERIAL SEARCHING...", "warning", (lm, sy))
        else:
            self._txt("● SERIAL LOST", "danger", (lm, sy))

        if mapper.joystick_name:
            self._txt(f"🎮 {mapper.joystick_name}", "good", (sw // 2, sy))
        else:
            self._txt("⌨ KEYBOARD ONLY (no gamepad)", "warning", (sw // 2, sy))

        self._hline(int(0.15 * sh))

        # ── Motor bars ──────────────────────────────────────────────────────
        bar_x = int(0.10 * sw)
        bar_w = int(0.37 * sw)
        bar_h = max(20, int(0.065 * sh))
        bar1_y = int(0.225 * sh)
        bar2_y = int(0.40 * sh)

        self._bar(bar_x, bar1_y, bar_w, bar_h,
                  values.get("motor_left", 127), 127, 0, 255, "LEFT MOTOR")
        self._bar(bar_x, bar2_y, bar_w, bar_h,
                  values.get("motor_right", 127), 127, 0, 255, "RIGHT MOTOR")

        # ── Status indicators — 2×2 grid, centred text, aligned with bars ───
        panel_x = int(0.525 * sw)
        ind_w   = int(0.21 * sw)
        ind_x2  = int(0.755 * sw)
        ind_h   = bar_h

        weapon_on   = values.get("weapon", 0) > 127
        weapon_rev  = values.get("weapon_rev", 0) > 127
        failsafe_on = values.get("failsafe", 0) > 127

        w_color = "danger" if weapon_rev else ("warning" if weapon_on else "panel")
        w_txt   = "WEAPON ATTACK" if weapon_rev else ("WEAPON IDLE" if weapon_on else "WEAPON SAFE")
        self._ind(w_color, (panel_x, bar1_y, ind_w, ind_h), w_txt)

        f_txt = "FAILSAFE ACTIVE" if failsafe_on else "NORMAL"
        self._ind("danger" if failsafe_on else "panel",
                  (panel_x, bar2_y, ind_w, ind_h), f_txt)

        self._ind("warning" if drive_inverted else "panel",
                  (ind_x2, bar1_y, ind_w, ind_h),
                  "DRIVE INVERTED" if drive_inverted else "DRIVE NORMAL")

        self._ind("good" if armed else "danger",
                  (ind_x2, bar2_y, ind_w, ind_h),
                  "ARMED" if armed else "DISARMED")

        # ── Stats ────────────────────────────────────────────────────────────
        stats_y = int(0.49 * sh)
        hz = link.packet_count / (runtime_ms / 1000.0) if runtime_ms > 0 else 0
        self._txt(
            f"Pkts: {link.packet_count}  |  Rate: {hz:.1f} Hz  |  Idle: {link.idle_ms} ms",
            "text", (lm, stats_y), small=True,
        )

        # ── Bottom — event log (left) | controls (right) ────────────────────
        sep_y = int(0.535 * sh)
        mid_x = sw // 2
        self._hline(sep_y)
        pygame.draw.line(self.screen, self._c("panel"),
                         (mid_x, sep_y), (mid_x, sh - lm), 1)

        col_title_y = int(0.558 * sh)
        col_start_y = int(0.595 * sh)
        col_line_h  = max(14, int(0.034 * sh))
        col2_x      = mid_x + lm

        # Event log
        self._txt("EVENT LOG", "accent", (lm, col_title_y))
        ly = col_start_y
        for entry in self.log:
            self._txt(entry, "text", (lm, ly), small=True)
            ly += col_line_h

        # Controls
        self._txt("CONTROLS", "accent", (col2_x, col_title_y))
        ctrl_lines = [
            "L-Stick / W-S    = Left drive",
            "R-Stick / UP-DN  = Right drive",
            "RB / SPACE       = Weapon idle",
            "RT / LSHIFT      = Weapon rev",
            "LB / I           = Drive invert",
            "Start / A        = Arm toggle",
            "B  / F           = FAILSAFE",
            "ESC              = Exit",
        ]
        cy = col_start_y
        for line in ctrl_lines:
            self._txt(line, "text", (col2_x, cy), small=True)
            cy += col_line_h

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
    screen = pygame.display.set_mode((600, 400), pygame.RESIZABLE)
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
            if event.type == pygame.VIDEORESIZE:
                screen = pygame.display.set_mode((event.w, event.h), pygame.RESIZABLE)
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

    rate_hz = cfg["serial"]["rate_hz"]

    running = True
    start_time = pygame.time.get_ticks()
    last_send = 0
    drive_inverted = False
    prev_invert_raw = False
    armed = False
    prev_arm_raw = False

    while running:
        now = pygame.time.get_ticks()

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                running = False
            if event.type == pygame.VIDEORESIZE:
                gui.screen = pygame.display.set_mode((event.w, event.h), pygame.RESIZABLE)

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

        # Drive invert toggle — rising edge detection
        invert_raw = values.get("drive_invert", 0) > 127
        if invert_raw and not prev_invert_raw:
            drive_inverted = not drive_inverted
            gui.add_log(f"Drive invert {'ON' if drive_inverted else 'OFF'}")
        prev_invert_raw = invert_raw

        # Apply drive invert: swap sides and negate both around center
        if drive_inverted:
            center = cfg["packet"]["center"]
            range_min, range_max = cfg["packet"]["range"]
            left_raw = values.get("motor_left", center)
            right_raw = values.get("motor_right", center)
            values["motor_left"] = max(range_min, min(range_max, 2 * center - right_raw))
            values["motor_right"] = max(range_min, min(range_max, 2 * center - left_raw))

        # Hard failsafe: latch robot permanently, exit station
        if values.get("failsafe", 0) > 127:
            gui.add_log("HARD FAILSAFE — robot latched, shutting down")
            hard_packet = bytes([127, 127, 0, 255]) + b"\n"
            link.ensure_connected()
            for _ in range(5):
                link.send(hard_packet)
            pygame.quit()
            sys.exit(0)

        # Arm toggle
        arm_raw = values.get("armed", 0) > 127
        if arm_raw and not prev_arm_raw:
            armed = not armed
            gui.add_log(f"Robot {'ARMED' if armed else 'DISARMED'}")
        prev_arm_raw = arm_raw

        # Disarmed: hold all outputs neutral
        if not armed:
            center = cfg["packet"]["center"]
            values["motor_left"] = center
            values["motor_right"] = center
            values["weapon"] = 0
            values["weapon_rev"] = 0

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
        gui.draw(link, mapper, values, elapsed, drive_inverted, armed)
        gui.clock.tick(rate_hz)

    pygame.quit()
    print("Ground station shut down.")


if __name__ == "__main__":
    main()
