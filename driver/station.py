#!/usr/bin/env python3
"""HCR Mission Control - Dear PyGui driver station."""
from __future__ import annotations

import os, sys, json, time, argparse, hashlib, getpass
from collections import deque
from pathlib import Path

CONFIG_PATH = Path(__file__).resolve().parent / "config.json"

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

for _pkg, _pip in [("dearpygui", "dearpygui"), ("pygame", "pygame"), ("serial", "pyserial")]:
    try:
        __import__(_pkg)
    except ImportError:
        print(f"ERROR: {_pip} required.  pip install {_pip}")
        sys.exit(1)

import pygame
import dearpygui.dearpygui as dpg

import drive
from drive_modes import DRIVE_MODES, MODE_NAMES, index_of
from keymap      import init_keymap, key_display, gp_display
from serial_link import SerialLink
from inputmapper import InputMapper
from calibrate   import calibrate

# ─── Layout ──────────────────────────────────────────────────────────────────
LEFT_W  = 400         # fixed width of the safety/drive column; the rest stretches
BANNER_H = 96
BAR_W   = 68
BAR_H   = 172
BAR_CY  = BAR_H // 2

PW_MODAL_W = 300      # password modal content width

LOG_KEEP  = 200       # history kept in memory
LOG_SLOTS = 60        # lines rendered, newest first

# ─── Palette ─────────────────────────────────────────────────────────────────
C_BG     = [21,  22,  27,  255]
C_PANEL  = [31,  33,  41,  255]   # card background
C_FIELD  = [43,  46,  57,  255]   # input/frame background
C_WELL   = [24,  25,  31,  255]   # recessed areas: bars, event log
C_BORDER = [58,  62,  76,  255]
C_TEXT   = [226, 229, 236, 255]
C_DIM    = [128, 136, 150, 255]
C_ACCENT = [0,   190, 255, 255]
C_GOOD   = [70,  210, 118, 255]
C_WARN   = [255, 178, 44,  255]
C_DANGER = [244, 84,  70,  255]
C_FWD    = [52,  214, 110, 255]
C_REV    = [222, 84,  74,  255]

# ─── Fonts ───────────────────────────────────────────────────────────────────
# Load a real system font when one exists; falls back to DPG's bitmap font.
# WSL: scripts/setup-wsl.sh installs fonts-dejavu-core.
F_BODY = F_SMALL = F_MONO = F_BANNER = None


def _font_paths() -> tuple[list, list, list]:
    win   = "C:/Windows/Fonts"
    mac   = "/System/Library/Fonts/Supplemental"
    linux = "/usr/share/fonts/truetype"
    body = [f"{win}/segoeui.ttf", f"{win}/tahoma.ttf",
            f"{mac}/Tahoma.ttf",  f"{mac}/Arial.ttf",
            f"{linux}/dejavu/DejaVuSans.ttf",
            f"{linux}/ubuntu/Ubuntu-R.ttf",
            f"{linux}/liberation/LiberationSans-Regular.ttf"]
    bold = [f"{win}/segoeuib.ttf", f"{win}/tahomabd.ttf",
            f"{mac}/Tahoma Bold.ttf", f"{mac}/Arial Bold.ttf",
            f"{linux}/dejavu/DejaVuSans-Bold.ttf",
            f"{linux}/ubuntu/Ubuntu-B.ttf",
            f"{linux}/liberation/LiberationSans-Bold.ttf"]
    mono = [f"{win}/consola.ttf",
            f"{mac}/Andale Mono.ttf", f"{mac}/Courier New.ttf",
            f"{linux}/dejavu/DejaVuSansMono.ttf",
            f"{linux}/ubuntu-mono/UbuntuMono-R.ttf",
            f"{linux}/liberation/LiberationMono-Regular.ttf"]
    return body, bold, mono


def _load_fonts() -> None:
    global F_BODY, F_SMALL, F_MONO, F_BANNER
    body_c, bold_c, mono_c = _font_paths()
    body = next((p for p in body_c if Path(p).exists()), None)
    bold = next((p for p in bold_c if Path(p).exists()), None) or body
    mono = next((p for p in mono_c if Path(p).exists()), None)
    with dpg.font_registry():
        if body:
            F_BODY   = dpg.add_font(body, 17)
            F_SMALL  = dpg.add_font(body, 14)
        if bold:
            F_BANNER = dpg.add_font(bold, 30)
        if mono:
            F_MONO   = dpg.add_font(mono, 15)
    if F_BODY:
        dpg.bind_font(F_BODY)


def _use_font(item, font) -> None:
    if font:
        dpg.bind_item_font(item, font)


# ─── Runtime state ────────────────────────────────────────────────────────────
_log: deque[str] = deque(maxlen=LOG_KEEP)
_log_rev: int = 0          # bumped by _log_add so the UI only redraws on change
_log_shown_rev: int = -1

_gs: dict = {
    "drive_inverted": False,
    "weapon_state":   "safe",
    "armed":          False,
    "killswitch":     False,
    "weapon_locked":  True,     # always locked at startup, never persisted
}

_mode_idx: int = 0                # index into drive_modes.DRIVE_MODES
_weapon_pw_hash: str = ""         # from config.json, set in main()
_relock_on_disarm: bool = True
_IND: dict[str, int] = {}
_BANNER: dict[str, int] = {}
_banner_shown: tuple | None = None
_trim: dict = {"L": 0, "R": 0}    # raw offset −127…+127
_mult: dict = {"L": 1.0, "R": 1.0}  # output multiplier 0.0…5.0
_pw_purpose: str = "unlock"       # what the password modal is gating right now
_failsafe_on_dongle_removal: bool = True
_test: dict = {"enabled": False, "mag": 40, "dir": 1, "deadline": 0.0}


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _log_add(msg: str) -> None:
    global _log_rev
    _log.append(f"[{time.strftime('%H:%M:%S')}] {msg}")
    _log_rev += 1


PORT_AUTO = "Auto (find dongle)"


def _port_items(link) -> list:
    """Combo items: Auto first, then every serial port with its description and
    a [DONGLE] flag on the one whose USB ID matches the radio dongle."""
    items = [PORT_AUTO]
    for dev, desc, is_dongle in link.list_ports():
        items.append(f"{dev} | {desc}" + ("  [DONGLE]" if is_dongle else ""))
    return items


def _port_from_item(item: str) -> str:
    """Selected combo string back to a device name, or 'auto'."""
    if item.startswith("Auto"):
        return "auto"
    return item.split(" | ", 1)[0].strip()


def _log_color(line: str, newest: bool) -> list:
    if "KILL" in line:
        return C_DANGER[:3]
    if "WARNING" in line or "failed" in line or "refused" in line:
        return C_WARN[:3]
    return C_TEXT[:3] if newest else C_DIM[:3]


# Must match robot/main/include/robot_config.h. The failsafe byte doubles as
# an opcode so commands fit the existing 4-byte payload.
OPCODE_DRIVE       = 0
OPCODE_SET_TRIM    = 1
OPCODE_WEAPON_TEST = 2
TRIM_MAGIC         = 0x5A
WEAPON_TEST_MAGIC  = 0xA7

# Mirror of WEAPON_MAX_OUTPUT_PCT; the robot clamps anyway.
WPN_TEST_MAX   = 100
TEST_DEADMAN_S = 5.0


def _hex_packet(ml: int, mr: int, wb: int, fb: int) -> bytes:
    return f"{ml:02x}{mr:02x}{wb:02x}{fb:02x}\n".encode()


WEAPON_BYTES = {"safe": 127, "idle": 160, "attack": 255, "spinup": 95}
NEUTRAL = 127


def password_matches(entered: str, expected_sha256: str) -> bool:
    """Empty stored hash means no password: the click-through is the interlock."""
    if not expected_sha256:
        return True
    return hashlib.sha256(entered.encode()).hexdigest() == expected_sha256


def weapon_permitted(armed: bool, killswitch_latched: bool, weapon_locked: bool) -> bool:
    """Weapon may spin only when armed, not killed, and unlocked. The lock
    guards against an accidental keypress; it is not access control."""
    return armed and not killswitch_latched and not weapon_locked


def outputs_inhibited(armed: bool, killswitch_latched: bool) -> bool:
    """Nothing may be commanded when disarmed or killed, whatever the sticks say."""
    return killswitch_latched or not armed


def failsafe_byte(kill_pressed: bool, killswitch_latched: bool) -> int:
    """255 latches the robot into deep sleep; only a power cycle clears it."""
    return 255 if (kill_pressed or killswitch_latched) else 0


def trim_packet(trim_l: int, trim_r: int) -> bytes:
    """Encode a set-trim command. Trim is offset by 127 so it fits a byte."""
    return _hex_packet(max(0, min(255, 127 + trim_l)),
                       max(0, min(255, 127 + trim_r)),
                       TRIM_MAGIC, OPCODE_SET_TRIM)


def weapon_test_packet(signed_pct: int) -> bytes:
    """Wireless weapon-test command: percent (127-centred, sign = direction),
    magic in byte 2, opcode in byte 3."""
    p = max(-100, min(100, signed_pct))
    return _hex_packet(max(0, min(255, 127 + p)), 0, WEAPON_TEST_MAGIC, OPCODE_WEAPON_TEST)


def test_should_spin(enabled: bool, now: float, deadline: float,
                     killswitch_latched: bool, connected: bool) -> bool:
    """Spin only while enabled, connected, not killed, and inside the deadman."""
    return bool(enabled and connected and not killswitch_latched and now < deadline)


def dongle_pull_kills(prev_connected: bool, now_connected: bool,
                      enabled: bool, already_latched: bool) -> bool:
    """Latch on USB removal (connected -> not). An RF dropout keeps the USB
    link up, so radio blips don't trigger this and stay recoverable."""
    return enabled and prev_connected and not now_connected and not already_latched


def trigger_killswitch(link: SerialLink) -> None:
    """Latch the killswitch and burst failsafe 255. Shared by key, gamepad, and
    UI button. Idempotent."""
    if _gs["killswitch"]:
        return
    _gs["killswitch"] = True
    _test["enabled"] = False          # a kill also ends any running bench test
    _log_add("KILLSWITCH - robot latched until power cycle")
    if link.ensure_connected():
        for _ in range(5):
            link.send(b"7f7f7fff\n")
    else:
        _log_add("WARNING: killswitch sent but serial not connected")


_TEXT_INPUTS = ("inp_wpn_pw", "inp_trim_L", "inp_trim_R",
                "inp_mult_L", "inp_mult_R")


def keyboard_captured() -> bool:
    """True while a text field owns the keyboard. Keys are polled globally, so
    without this, typing the password (its chars are control keys) would drive
    the robot. Gamepad and on-screen buttons stay live."""
    if dpg.is_item_shown("wpn_pw_modal"):
        return True
    return any(dpg.is_item_active(t) for t in _TEXT_INPUTS)


# ─── Indicator and button themes ─────────────────────────────────────────────

def _make_ind_themes() -> None:
    # (bg, text[, hover]). Indicators keep hover == bg; real buttons brighten.
    specs: dict[str, tuple] = {
        "panel":       ((44,  47,  58),  (168, 174, 184)),
        "good":        ((36,  150, 82),  (232, 255, 238)),
        "warn":        ((176, 122, 12),  (255, 240, 178)),
        "danger":      ((172, 40,  38),  (255, 208, 204)),
        "attack":      ((156, 22,  22),  (255, 176, 176)),
        "arm_ready":   ((28,  128, 66),  (235, 255, 242), (36,  152, 80)),
        "arm_live":    ((178, 108, 20),  (255, 245, 225), (200, 126, 30)),
        "lock_locked": ((58,  74,  106), (216, 228, 248), (70,  90,  128)),
        "lock_live":   ((172, 62,  34),  (255, 224, 210), (196, 76,  44)),
        "lock_hot":    ((216, 84,  46),  (255, 238, 228), (216, 84,  46)),
        "test_ready":  ((150, 70,  20),  (255, 236, 210), (170, 84,  26)),
        "test_live":   ((196, 96,  26),  (255, 244, 230), (196, 96,  26)),
        "test_hot":    ((230, 120, 40),  (255, 250, 240), (230, 120, 40)),
        "kill_ready":  ((152, 32,  32),  (255, 214, 212), (178, 40,  40)),
        "kill_reset":  ((128, 92,  18),  (255, 240, 200), (148, 108, 24)),
    }
    for name, spec in specs.items():
        bg, fg = spec[0], spec[1]
        hov = spec[2] if len(spec) > 2 else bg
        with dpg.theme() as t:
            with dpg.theme_component(dpg.mvButton):
                dpg.add_theme_color(dpg.mvThemeCol_Button,        bg)
                dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered, hov)
                dpg.add_theme_color(dpg.mvThemeCol_ButtonActive,  hov)
                dpg.add_theme_color(dpg.mvThemeCol_Text,          fg)
        _IND[name] = t


def _set_ind(tag: str, label: str, theme: str) -> None:
    dpg.configure_item(tag, label=label)
    dpg.bind_item_theme(tag, _IND[theme])


def _make_banner_themes() -> None:
    for name, bg in {
        "disarmed": (44,  48,  60),
        "armed":    (24,  118, 62),
        "live":     (164, 106, 16),
        "test":     (176, 92,  20),
        "kill":     (158, 34,  30),
    }.items():
        with dpg.theme() as t:
            with dpg.theme_component(dpg.mvAll):
                dpg.add_theme_color(dpg.mvThemeCol_ChildBg, bg)
        _BANNER[name] = t


def _set_banner(main: str, sub: str, state: str) -> None:
    """The one line that states the overall state (buttons say actions)."""
    global _banner_shown
    key = (main, sub, state)
    if key == _banner_shown:
        return
    _banner_shown = key
    dpg.set_value("txt_banner", main)
    dpg.set_value("txt_banner_sub", sub)
    dpg.bind_item_theme("banner_child", _BANNER[state])


# ─── Motor bars ───────────────────────────────────────────────────────────────

def _make_bar(side: str) -> None:
    t = dpg.add_text(side, color=C_DIM[:3], indent=BAR_W // 2 - 4)
    _use_font(t, F_SMALL)
    with dpg.drawlist(width=BAR_W, height=BAR_H, tag=f"dl_{side}"):
        dpg.draw_rectangle([0, 0], [BAR_W, BAR_H],
                           fill=C_WELL[:3], color=[0, 0, 0, 0], tag=f"dr_bg_{side}")
        for pct in [25, 50, 75]:
            tw = 7 if pct == 50 else 4
            for direction in (1, -1):
                yt = int(BAR_CY - direction * pct / 100 * BAR_CY)
                dpg.draw_line([2, yt], [tw + 1, yt], color=C_BORDER[:3], thickness=1)
                dpg.draw_line([BAR_W - tw - 1, yt], [BAR_W - 2, yt],
                              color=C_BORDER[:3], thickness=1)
        dpg.draw_line([3, BAR_CY], [BAR_W - 3, BAR_CY],
                      color=C_BORDER[:3], thickness=1, tag=f"dr_ctr_{side}")
        dpg.draw_rectangle([3, BAR_CY - 2], [BAR_W - 3, BAR_CY + 2],
                           fill=[100, 100, 100, 35], color=[0, 0, 0, 0],
                           tag=f"dr_glow_{side}")
        dpg.draw_rectangle([5, BAR_CY - 1], [BAR_W - 5, BAR_CY + 1],
                           fill=C_DIM[:3], color=[0, 0, 0, 0], tag=f"dr_bar_{side}")
    v = dpg.add_text("127", tag=f"txt_val_{side}", color=C_TEXT[:3],
                     indent=BAR_W // 2 - 14)
    _use_font(v, F_MONO)


def _update_bar(side: str, value: int) -> None:
    norm = (value - 127) / 127.0
    if norm > 0.008:
        y1, y2 = max(0, int(BAR_CY - norm * BAR_CY)), BAR_CY
        fill = C_FWD[:3]
    elif norm < -0.008:
        y1, y2 = BAR_CY, min(BAR_H, int(BAR_CY + (-norm) * BAR_CY))
        fill = C_REV[:3]
    else:
        y1, y2 = BAR_CY - 1, BAR_CY + 1
        fill = C_DIM[:3]
    dpg.configure_item(f"dr_bar_{side}",
                       pmin=[5, y1], pmax=[BAR_W - 5, max(y1 + 2, y2)], fill=fill)
    dpg.configure_item(f"dr_glow_{side}",
                       pmin=[3, y1 - 1], pmax=[BAR_W - 3, max(y1 + 1, y2 + 1)],
                       fill=[fill[0], fill[1], fill[2], 50])
    dpg.set_value(f"txt_val_{side}", str(value))


# ─── UI construction ──────────────────────────────────────────────────────────

def _section(label: str) -> None:
    dpg.add_spacer(height=6)
    t = dpg.add_text(label, color=C_DIM[:3])
    _use_font(t, F_SMALL)
    dpg.add_separator()


def _build_ui(cfg: dict, link: SerialLink, mapper: InputMapper) -> None:
    """Build the HUD: state banner on top, fixed left card (mid-match controls),
    stretching right card (setup + event log). Mode changes only via the
    dropdown, never a hidden key."""
    _load_fonts()

    with dpg.theme() as g_theme:
        with dpg.theme_component(dpg.mvAll):
            dpg.add_theme_color(dpg.mvThemeCol_WindowBg,         C_BG[:3])
            dpg.add_theme_color(dpg.mvThemeCol_ChildBg,          C_PANEL[:3])
            dpg.add_theme_color(dpg.mvThemeCol_Border,           C_BORDER[:3])
            dpg.add_theme_color(dpg.mvThemeCol_FrameBg,          C_FIELD[:3])
            dpg.add_theme_color(dpg.mvThemeCol_FrameBgHovered,   (53, 57, 70))
            dpg.add_theme_color(dpg.mvThemeCol_FrameBgActive,    (60, 65, 80))
            dpg.add_theme_color(dpg.mvThemeCol_Button,           (52, 56, 70))
            dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered,    (66, 71, 88))
            dpg.add_theme_color(dpg.mvThemeCol_ButtonActive,     (0, 155, 205))
            dpg.add_theme_color(dpg.mvThemeCol_Text,             C_TEXT[:3])
            dpg.add_theme_color(dpg.mvThemeCol_TitleBg,          (16, 17, 21))
            dpg.add_theme_color(dpg.mvThemeCol_TitleBgActive,    (22, 23, 29))
            dpg.add_theme_color(dpg.mvThemeCol_ScrollbarBg,      (24, 25, 30))
            dpg.add_theme_color(dpg.mvThemeCol_ScrollbarGrab,    (62, 67, 82))
            dpg.add_theme_color(dpg.mvThemeCol_Separator,        (52, 56, 68))
            dpg.add_theme_color(dpg.mvThemeCol_Header,           (0, 140, 190, 150))
            dpg.add_theme_color(dpg.mvThemeCol_HeaderHovered,    (0, 190, 240, 200))
            dpg.add_theme_color(dpg.mvThemeCol_HeaderActive,     (0, 200, 255))
            dpg.add_theme_color(dpg.mvThemeCol_PopupBg,          (30, 32, 40))
            dpg.add_theme_color(dpg.mvThemeCol_SliderGrab,       (0, 160, 215))
            dpg.add_theme_color(dpg.mvThemeCol_SliderGrabActive, (0, 200, 255))
            dpg.add_theme_color(dpg.mvThemeCol_CheckMark,        (0, 200, 255))
            dpg.add_theme_color(dpg.mvThemeCol_ModalWindowDimBg, (10, 10, 14, 180))
            dpg.add_theme_style(dpg.mvStyleVar_WindowRounding,  0)
            dpg.add_theme_style(dpg.mvStyleVar_ChildRounding,   8)
            dpg.add_theme_style(dpg.mvStyleVar_FrameRounding,   5)
            dpg.add_theme_style(dpg.mvStyleVar_GrabRounding,    5)
            dpg.add_theme_style(dpg.mvStyleVar_PopupRounding,   6)
            dpg.add_theme_style(dpg.mvStyleVar_ItemSpacing,     8, 6)
            dpg.add_theme_style(dpg.mvStyleVar_FramePadding,    9, 6)
            dpg.add_theme_style(dpg.mvStyleVar_WindowPadding,   14, 12)
            dpg.add_theme_style(dpg.mvStyleVar_CellPadding,     6, 4)
            dpg.add_theme_style(dpg.mvStyleVar_ChildBorderSize, 1)
            dpg.add_theme_style(dpg.mvStyleVar_ScrollbarSize,   12)
    dpg.bind_theme(g_theme)
    _make_ind_themes()
    _make_banner_themes()

    # ── Callbacks ─────────────────────────────────────────────────────────────
    def _apply_mode() -> None:
        """On mode change, re-safe the weapon and clear invert."""
        mode = DRIVE_MODES[_mode_idx]
        mapper.set_mode(mode)
        _gs["drive_inverted"] = False
        _gs["weapon_state"]   = "safe"
        dpg.set_value("cmb_mode", mode["name"])
        dpg.set_value("txt_hint", mode["hint"])
        _log_add(f"Drive mode: {mode['name']}")

    def cb_mode_select(s, val, u):
        global _mode_idx
        _mode_idx = index_of(val)
        _apply_mode()

    def cb_port_select(s, val, u):
        port = _port_from_item(val)
        link.set_port(port)
        _log_add("Serial port set to auto (match dongle by USB ID)"
                 if port == "auto" else f"Serial port set to {port}")

    def cb_port_rescan(s, a, u):
        items = _port_items(link)
        dpg.configure_item("cmb_port", items=items)
        _log_add(f"Rescanned serial ports: {len(items) - 1} found")

    def cb_lock_click(s_, a, u):
        """Locking never needs a password. Unlocking always does."""
        global _pw_purpose
        if not _gs["weapon_locked"]:
            _gs["weapon_locked"] = True
            _gs["weapon_state"] = "safe"
            _log_add("Weapon LOCKED")
            return
        if _test["enabled"]:
            _log_add("Stop the weapon test before unlocking for drive")
            return
        if _relock_on_disarm and not _gs["armed"]:
            # Unlocking while disarmed is undone next frame by relock-on-disarm.
            _log_add("Arm first - the weapon stays locked while disarmed")
            return
        _pw_purpose = "unlock"
        dpg.configure_item("wpn_pw_modal", label="Unlock weapon")
        dpg.set_value("txt_pw_prompt", "Enter the weapon password.")
        dpg.set_value("inp_wpn_pw", "")
        dpg.set_value("txt_wpn_pw_err", " ")
        # Roughly centre on the viewport (autosized, so exact height is unknown).
        vw, vh = dpg.get_viewport_width(), dpg.get_viewport_height()
        dpg.configure_item("wpn_pw_modal",
                           pos=[max(0, vw // 2 - PW_MODAL_W // 2 - 20),
                                max(0, vh // 2 - 90)],
                           show=True)
        dpg.focus_item("inp_wpn_pw")

    def cb_lock_confirm(s_, a, u):
        entered = dpg.get_value("inp_wpn_pw")
        if not password_matches(entered, _weapon_pw_hash):
            dpg.set_value("txt_wpn_pw_err", "Wrong password")
            dpg.set_value("inp_wpn_pw", "")
            _log_add("Password refused: wrong password")
            return
        dpg.configure_item("wpn_pw_modal", show=False)
        if _pw_purpose == "test":
            # Bench test is standalone: disarmed + locked so only the test drives.
            _test["enabled"]  = True
            _test["deadline"] = time.time() + TEST_DEADMAN_S
            _gs["armed"]         = False
            _gs["weapon_locked"] = True
            _gs["weapon_state"]  = "safe"
            _log_add(f"Weapon TEST enabled: {_test['mag']}% "
                     f"{'FWD' if _test['dir'] > 0 else 'REV'} - re-press within 5 s")
        else:
            _gs["weapon_locked"] = False
            _log_add("Weapon UNLOCKED")

    def cb_lock_cancel(s_, a, u):
        dpg.configure_item("wpn_pw_modal", show=False)

    def cb_arm_click(s, a, u):
        if _test["enabled"]:
            _log_add("Stop the weapon test before arming")
            return
        _gs["armed"] = not _gs["armed"]
        _log_add(f"Robot {'ARMED' if _gs['armed'] else 'DISARMED'}")

    def cb_kill_click(s_, a, u):
        trigger_killswitch(link)

    def cb_kill_reset(s_, a, u):
        """Manual by design. The link is one-way, so the station cannot see
        the robot power cycle; automatic recovery would be a guess. Reset
        restarts from the safest state: disarmed, weapon locked."""
        _gs["killswitch"] = False
        _gs["armed"] = False
        _gs["weapon_locked"] = True
        _gs["weapon_state"] = "safe"
        _test["enabled"] = False
        _log_add("Killswitch reset - disarmed, weapon locked")

    def _test_keepalive():
        # Adjusting the test while it's running counts as active presence.
        if _test["enabled"]:
            _test["deadline"] = time.time() + TEST_DEADMAN_S

    def cb_test_mag(s, val, u):
        _test["mag"] = max(0, min(WPN_TEST_MAX, int(val)))
        dpg.set_value("sl_test_mag", _test["mag"])
        dpg.set_value("inp_test_mag", _test["mag"])
        _test_keepalive()

    def cb_test_mag_inp(s, val, u): cb_test_mag(s, val, u)

    def cb_test_dir(s, val, u):
        _test["dir"] = 1 if val == "Forward" else -1
        _test_keepalive()

    def cb_test_spin(s_, a, u):
        """Deadman press. Password once to start the session; after that each
        press extends or resumes the 5 s window with no password."""
        global _pw_purpose
        if _gs["killswitch"]:
            _log_add("Reset the killswitch before testing the weapon")
            return
        if not link.ensure_connected():
            _log_add("WARNING: weapon test needs the serial link connected")
            return
        if _test["enabled"]:
            _test["deadline"] = time.time() + TEST_DEADMAN_S
            return
        _pw_purpose = "test"
        dpg.configure_item("wpn_pw_modal", label="Enable weapon test")
        dpg.set_value("txt_pw_prompt",
                      "Enter the weapon password to enable the bench test.")
        dpg.set_value("inp_wpn_pw", "")
        dpg.set_value("txt_wpn_pw_err", " ")
        vw, vh = dpg.get_viewport_width(), dpg.get_viewport_height()
        dpg.configure_item("wpn_pw_modal",
                           pos=[max(0, vw // 2 - PW_MODAL_W // 2 - 20),
                                max(0, vh // 2 - 90)],
                           show=True)
        dpg.focus_item("inp_wpn_pw")

    def cb_test_stop(s_, a, u):
        if _test["enabled"]:
            _test["enabled"] = False
            _log_add("Weapon test stopped")

    def cb_save_trim(s_, a, u):
        """Push trim to the robot (it saves to NVS). Refused while armed; sent
        several times since the link is one-way and lossy."""
        if _gs["armed"]:
            _log_add("Disarm before saving trim")
            return
        if not link.ensure_connected():
            _log_add("WARNING: trim not sent, serial not connected")
            return
        pkt = trim_packet(_trim["L"], _trim["R"])
        sent = sum(1 for _ in range(5) if link.send(pkt))
        if sent:
            _log_add(f"Trim sent to robot: L={_trim['L']} R={_trim['R']}")
        else:
            _log_add("WARNING: trim send failed")

    def _sync_trim(side, val):
        val = max(-127, min(127, val))
        _trim[side] = val
        dpg.set_value(f"sl_trim_{side}", val)
        dpg.set_value(f"inp_trim_{side}", val)

    def cb_trim_L(s, val, u):     _sync_trim("L", val)
    def cb_trim_R(s, val, u):     _sync_trim("R", val)
    def cb_trim_L_inp(s, val, u): _sync_trim("L", val)
    def cb_trim_R_inp(s, val, u): _sync_trim("R", val)
    def cb_trim_L_inc(s, a, u):   _sync_trim("L", _trim["L"] + 1)
    def cb_trim_L_dec(s, a, u):   _sync_trim("L", _trim["L"] - 1)
    def cb_trim_R_inc(s, a, u):   _sync_trim("R", _trim["R"] + 1)
    def cb_trim_R_dec(s, a, u):   _sync_trim("R", _trim["R"] - 1)

    def _sync_mult(side, val):
        val = max(0.0, min(5.0, round(val, 2)))
        _mult[side] = val
        dpg.set_value(f"sl_mult_{side}", val)
        dpg.set_value(f"inp_mult_{side}", val)

    def cb_mult_L(s, val, u):     _sync_mult("L", val)
    def cb_mult_R(s, val, u):     _sync_mult("R", val)
    def cb_mult_L_inp(s, val, u): _sync_mult("L", val)
    def cb_mult_R_inp(s, val, u): _sync_mult("R", val)
    def cb_mult_L_inc(s, a, u):   _sync_mult("L", _mult["L"] + 0.1)
    def cb_mult_L_dec(s, a, u):   _sync_mult("L", _mult["L"] - 0.1)
    def cb_mult_R_inc(s, a, u):   _sync_mult("R", _mult["R"] + 0.1)
    def cb_mult_R_dec(s, a, u):   _sync_mult("R", _mult["R"] - 0.1)

    def _trim_row(label: str, key: str, cb, cb_inc, cb_dec, cb_inp):
        with dpg.group(horizontal=True):
            t = dpg.add_text(label, color=C_DIM[:3])
            _use_font(t, F_SMALL)
            dpg.add_button(label="-", width=24, callback=cb_dec)
            dpg.add_slider_int(tag=f"sl_trim_{key}", min_value=-127, max_value=127,
                               default_value=0, width=170, format="%d",
                               callback=cb)
            dpg.add_button(label="+", width=24, callback=cb_inc)
            dpg.add_input_int(tag=f"inp_trim_{key}", default_value=0,
                              min_value=-127, max_value=127,
                              min_clamped=True, max_clamped=True,
                              width=64, step=0, on_enter=True,
                              callback=cb_inp)

    def _mult_row(label: str, key: str, cb, cb_inc, cb_dec, cb_inp):
        with dpg.group(horizontal=True):
            t = dpg.add_text(label, color=C_DIM[:3])
            _use_font(t, F_SMALL)
            dpg.add_button(label="-", width=24, callback=cb_dec)
            dpg.add_slider_float(tag=f"sl_mult_{key}", min_value=0.0, max_value=5.0,
                                 default_value=1.0, width=170, format="%.2f",
                                 callback=cb)
            dpg.add_button(label="+", width=24, callback=cb_inc)
            dpg.add_input_float(tag=f"inp_mult_{key}", default_value=1.0,
                                min_value=0.0, max_value=5.0,
                                min_clamped=True, max_clamped=True,
                                width=64, step=0, on_enter=True,
                                format="%.2f", callback=cb_inp)

    # ── Primary window ────────────────────────────────────────────────────────
    with dpg.window(tag="primary", no_title_bar=True, no_move=True,
                    no_resize=True, no_close=True, no_collapse=True,
                    no_scrollbar=True):

        # Brand + telemetry strip
        with dpg.group(horizontal=True):
            b = dpg.add_text("HCR MISSION CONTROL", color=C_ACCENT[:3])
            _use_font(b, F_SMALL)
            dpg.add_spacer(width=18)
            t1 = dpg.add_text("SEARCHING...",   tag="txt_serial",  color=C_WARN[:3])
            _use_font(t1, F_SMALL)
            s1 = dpg.add_text(" | ", color=C_DIM[:3])
            _use_font(s1, F_SMALL)
            t2 = dpg.add_text("NO GAMEPAD",     tag="txt_gamepad", color=C_WARN[:3])
            _use_font(t2, F_SMALL)
            s2 = dpg.add_text(" | ", color=C_DIM[:3])
            _use_font(s2, F_SMALL)
            t3 = dpg.add_text("0.0 Hz | - ms",   tag="txt_stats",   color=C_DIM[:3])
            _use_font(t3, F_MONO)
            dpg.add_spacer(width=18)
            pl = dpg.add_text("Port", color=C_DIM[:3])
            _use_font(pl, F_SMALL)
            dpg.add_combo(tag="cmb_port", width=250, items=_port_items(link),
                          default_value=PORT_AUTO, callback=cb_port_select)
            dpg.add_button(label="Rescan", callback=cb_port_rescan)

        # State banner
        with dpg.child_window(tag="banner_child", height=BANNER_H,
                              border=False, no_scrollbar=True,
                              no_scroll_with_mouse=True):
            dpg.add_spacer(height=8)
            with dpg.group(horizontal=True):
                dpg.add_spacer(width=16)
                bt = dpg.add_text("DISARMED", tag="txt_banner",
                                  color=(245, 247, 250))
                _use_font(bt, F_BANNER)
            with dpg.group(horizontal=True):
                dpg.add_spacer(width=17)
                bs = dpg.add_text("outputs neutral", tag="txt_banner_sub",
                                  color=(232, 236, 242, 190))
                _use_font(bs, F_SMALL)
        dpg.bind_item_theme("banner_child", _BANNER["disarmed"])

        dpg.add_spacer(height=2)

        with dpg.group(horizontal=True):

            # ── Left card: safety controls + drive ────────────────────────────
            with dpg.child_window(width=LEFT_W, border=True, tag="w_left"):
                _section("SAFETY")
                dpg.add_button(label="ARM", tag="ind_armed",
                               height=50, width=-1, callback=cb_arm_click)
                dpg.add_button(label="UNLOCK WEAPON", tag="ind_wpn_lock",
                               height=36, width=-1, callback=cb_lock_click)
                dpg.add_button(label="KILL ROBOT", tag="btn_kill",
                               height=36, width=-1, callback=cb_kill_click)
                dpg.add_button(label="RESET KILLSWITCH", tag="btn_kill_reset",
                               height=36, width=-1, show=False,
                               callback=cb_kill_reset)
                with dpg.table(header_row=False, policy=dpg.mvTable_SizingStretchSame,
                               pad_outerX=False, borders_outerH=False,
                               borders_outerV=False, borders_innerV=False,
                               borders_innerH=False):
                    dpg.add_table_column()
                    dpg.add_table_column()
                    dpg.add_table_column()
                    with dpg.table_row():
                        with dpg.table_cell():
                            dpg.add_button(label="WEAPON SAFE", tag="ind_weapon",
                                           height=26, width=-1)
                        with dpg.table_cell():
                            dpg.add_button(label="DRIVE NORMAL", tag="ind_drive",
                                           height=26, width=-1)
                        with dpg.table_cell():
                            dpg.add_button(label="KILL OFF", tag="ind_kill",
                                           height=26, width=-1)

                _section("DRIVE")
                dpg.add_combo(tag="cmb_mode", width=-1, items=MODE_NAMES,
                              default_value=DRIVE_MODES[_mode_idx]["name"],
                              callback=cb_mode_select)
                th = dpg.add_text(DRIVE_MODES[_mode_idx]["hint"], tag="txt_hint",
                                  color=C_DIM[:3], wrap=LEFT_W - 32)
                _use_font(th, F_SMALL)
                dpg.add_spacer(height=4)
                # Stretch columns centre the bars without spacer arithmetic.
                with dpg.table(header_row=False, policy=dpg.mvTable_SizingFixedFit,
                               pad_outerX=False, borders_outerH=False,
                               borders_outerV=False, borders_innerV=False,
                               borders_innerH=False):
                    dpg.add_table_column(width_stretch=True)
                    dpg.add_table_column(width_fixed=True, init_width_or_weight=BAR_W)
                    dpg.add_table_column(width_fixed=True, init_width_or_weight=BAR_W)
                    dpg.add_table_column(width_stretch=True)
                    with dpg.table_row():
                        with dpg.table_cell():
                            dpg.add_spacer(width=1)
                        with dpg.table_cell():
                            _make_bar("L")
                        with dpg.table_cell():
                            _make_bar("R")
                        with dpg.table_cell():
                            dpg.add_spacer(width=1)

            # ── Right card: setup + event log ─────────────────────────────────
            with dpg.child_window(border=True, tag="w_right"):
                _section("TRIM")
                _trim_row("L", "L", cb_trim_L, cb_trim_L_inc, cb_trim_L_dec, cb_trim_L_inp)
                _trim_row("R", "R", cb_trim_R, cb_trim_R_inc, cb_trim_R_dec, cb_trim_R_inp)
                dpg.add_button(label="Save trim to robot", tag="btn_save_trim",
                               callback=cb_save_trim, width=240, height=30)

                _section("OUTPUT MULTIPLIER")
                _mult_row("L", "L", cb_mult_L, cb_mult_L_inc, cb_mult_L_dec, cb_mult_L_inp)
                _mult_row("R", "R", cb_mult_R, cb_mult_R_inc, cb_mult_R_dec, cb_mult_R_inp)

                with dpg.collapsing_header(label="WEAPON TEST (BENCH)",
                                           tag="hdr_wtest", default_open=False):
                    wt = dpg.add_text(
                        "Spins the weapon at a set % with the wheels held "
                        "neutral. Hold the deadman: SPIN must be re-pressed "
                        "every 5 s or it stops. Killswitch stops it.",
                        color=C_DIM[:3], wrap=0)
                    _use_font(wt, F_SMALL)
                    with dpg.group(horizontal=True):
                        mt = dpg.add_text("%", color=C_DIM[:3])
                        _use_font(mt, F_SMALL)
                        dpg.add_slider_int(tag="sl_test_mag", min_value=0,
                                           max_value=WPN_TEST_MAX, default_value=40,
                                           width=150, format="%d", callback=cb_test_mag)
                        dpg.add_input_int(tag="inp_test_mag", default_value=40,
                                          min_value=0, max_value=WPN_TEST_MAX,
                                          min_clamped=True, max_clamped=True,
                                          width=64, step=0, on_enter=True,
                                          callback=cb_test_mag_inp)
                        dpg.add_radio_button(("Forward", "Reverse"), tag="rad_test_dir",
                                             horizontal=True, callback=cb_test_dir)
                    dpg.add_button(label="SPIN 40% FWD", tag="btn_test_spin",
                                   height=40, width=-1, callback=cb_test_spin)
                    dpg.add_button(label="STOP TEST", tag="btn_test_stop",
                                   height=30, width=-1, callback=cb_test_stop)
                    ts = dpg.add_text("", tag="txt_test_status", color=C_DIM[:3], wrap=0)
                    _use_font(ts, F_SMALL)
                with dpg.theme() as t_wt:
                    with dpg.theme_component(dpg.mvCollapsingHeader):
                        dpg.add_theme_color(dpg.mvThemeCol_Header,        (58, 40, 26))
                        dpg.add_theme_color(dpg.mvThemeCol_HeaderHovered, (72, 50, 32))
                        dpg.add_theme_color(dpg.mvThemeCol_HeaderActive,  (72, 50, 32))
                        dpg.add_theme_color(dpg.mvThemeCol_Text,          C_WARN[:3])
                dpg.bind_item_theme("hdr_wtest", t_wt)

                dpg.add_spacer(height=6)
                # Collapsed by default so it doesn't squeeze the event log.
                with dpg.collapsing_header(label="KEYBINDS", tag="hdr_keys",
                                           default_open=False):
                    tc = dpg.add_text("", tag="txt_controls", color=C_DIM[:3], wrap=0)
                    _use_font(tc, F_MONO)
                with dpg.theme() as t_hdr:
                    with dpg.theme_component(dpg.mvCollapsingHeader):
                        dpg.add_theme_color(dpg.mvThemeCol_Header,        (40, 43, 53))
                        dpg.add_theme_color(dpg.mvThemeCol_HeaderHovered, (50, 54, 66))
                        dpg.add_theme_color(dpg.mvThemeCol_HeaderActive,  (50, 54, 66))
                        dpg.add_theme_color(dpg.mvThemeCol_Text,          C_DIM[:3])
                dpg.bind_item_theme("hdr_keys", t_hdr)

                _section("EVENT LOG")
                with dpg.child_window(tag="w_log", height=-1, border=False,
                                      horizontal_scrollbar=False):
                    for i in range(LOG_SLOTS):
                        lt = dpg.add_text("", tag=f"log_{i}", color=C_DIM[:3], show=False)
                        _use_font(lt, F_MONO)
                with dpg.theme() as t_log:
                    with dpg.theme_component(dpg.mvAll):
                        dpg.add_theme_color(dpg.mvThemeCol_ChildBg, C_WELL[:3])
                dpg.bind_item_theme("w_log", t_log)

        _set_ind("ind_armed",    "ARM",           "arm_ready")
        _set_ind("ind_wpn_lock", "UNLOCK WEAPON", "lock_locked")
        _set_ind("btn_kill",     "KILL ROBOT",    "kill_ready")
        _set_ind("btn_kill_reset", "RESET KILLSWITCH", "kill_reset")
        _set_ind("btn_test_spin", "SPIN 40% FWD", "test_ready")
        dpg.set_value("rad_test_dir", "Forward")
        _set_ind("ind_weapon",   "WEAPON SAFE",   "panel")
        _set_ind("ind_drive",    "DRIVE NORMAL",  "panel")
        _set_ind("ind_kill",     "KILL OFF",      "panel")

        with dpg.tooltip("ind_armed"):
            dpg.add_text("Click (or press the arm key) to toggle arm state.")
            dpg.add_text("Robot ignores drive while DISARMED.")
        with dpg.tooltip("ind_weapon"):
            dpg.add_text("SAFE   = weapon off         (byte 127)")
            dpg.add_text("IDLE   = spinning low fwd   (byte 160)")
            dpg.add_text("ATTACK = full speed fwd     (byte 255)")
            dpg.add_text("SPINUP = held fwd ramp      (byte 95)")
            dpg.add_text("Atk key: hold in IDLE=attack, hold in SAFE=slow spin-up "
                         "(5 s to 100%, release stops).")
        with dpg.tooltip("ind_wpn_lock"):
            dpg.add_text("Unlocking asks for the weapon password.")
            dpg.add_text("Arm first: unlock is refused while disarmed.")
            dpg.add_text("While unlocked the button pulses orange; clicking")
            dpg.add_text("it again re-locks instantly, no password.")
            dpg.add_text("While LOCKED the weapon is forced safe no matter")
            dpg.add_text("what the gamepad or keyboard does.")
            dpg.add_text("Re-locks automatically on disarm and on killswitch.")
            dpg.add_text("This guards against accidental activation. It is not")
            dpg.add_text("access control.")
        with dpg.tooltip("ind_kill"):
            dpg.add_text("Sends failsafe byte=255.")
            dpg.add_text("Robot enters deep sleep - power cycle to recover.")
        with dpg.tooltip("btn_kill"):
            dpg.add_text("Latches the killswitch: failsafe byte 255 goes out")
            dpg.add_text("immediately and with every packet after. The robot")
            dpg.add_text("deep sleeps until it is power cycled.")
        with dpg.tooltip("btn_kill_reset"):
            dpg.add_text("Clears the STATION side of the killswitch, after you")
            dpg.add_text("have power cycled the robot. The link is one-way, so")
            dpg.add_text("the station cannot detect the power cycle itself.")
            dpg.add_text("You come back disarmed with the weapon locked.")

    # autosize + no_scrollbar: a fixed height that's too small clips the buttons.
    with dpg.window(tag="wpn_pw_modal", label="Unlock weapon", modal=True,
                    show=False, no_resize=True, no_scrollbar=True,
                    no_collapse=True, autosize=True):
        dpg.add_text("Enter the weapon password.", tag="txt_pw_prompt")
        dpg.add_spacer(height=4)
        dpg.add_input_text(tag="inp_wpn_pw", password=True, width=PW_MODAL_W,
                           on_enter=True, callback=cb_lock_confirm)
        # Always one line, so an error doesn't shift the buttons.
        dpg.add_text(" ", tag="txt_wpn_pw_err", color=C_DANGER[:3])
        dpg.add_spacer(height=4)
        with dpg.group(horizontal=True):
            dpg.add_button(label="Unlock", width=PW_MODAL_W // 2 - 4,
                           callback=cb_lock_confirm)
            dpg.add_button(label="Cancel", width=PW_MODAL_W // 2 - 4,
                           callback=cb_lock_cancel)

    # Primary window, else the HUD floats inset with dead space around it.
    dpg.set_primary_window("primary", True)


# ─── Per-frame UI update ──────────────────────────────────────────────────────

def _update_ui(link: SerialLink, mapper: InputMapper,
               ml: int, mr: int) -> None:
    global _log_shown_rev

    if link.state == "connected":
        dpg.set_value("txt_serial", f"SERIAL OK ({link.port_name})")
        dpg.configure_item("txt_serial", color=C_GOOD[:3])
    elif link.state == "searching":
        dpg.set_value("txt_serial", "SEARCHING...")
        dpg.configure_item("txt_serial", color=C_WARN[:3])
    else:
        dpg.set_value("txt_serial", "SERIAL LOST")
        dpg.configure_item("txt_serial", color=C_DANGER[:3])

    if mapper.joystick_name:
        dpg.set_value("txt_gamepad", f"{mapper.joystick_name}")
        dpg.configure_item("txt_gamepad", color=C_GOOD[:3])
    else:
        dpg.set_value("txt_gamepad", "KEYBOARD ONLY")
        dpg.configure_item("txt_gamepad", color=C_WARN[:3])

    idle = "-" if not link.last_ok else str(link.idle_ms)
    dpg.set_value("txt_stats", f"{link.current_hz:.1f} Hz | {idle} ms")

    _update_bar("L", ml)
    _update_bar("R", mr)

    # Re-lock whenever the weapon can't run, so unlocking is always deliberate.
    if _relock_on_disarm and not _gs["armed"]:
        _gs["weapon_locked"] = True
    if _gs["killswitch"]:
        _gs["weapon_locked"] = True

    locked = _gs["weapon_locked"]
    armed  = _gs["armed"]
    ws     = _gs["weapon_state"]
    inv    = _gs["drive_inverted"]
    kill   = _gs["killswitch"]

    mode = DRIVE_MODES[_mode_idx]
    keys = mode["keys"]
    btns = mode["buttons"]
    arm_key  = key_display(keys.get("arm", ""))
    kill_key = key_display(keys.get("killswitch", ""))

    # Buttons carry the ACTION a click performs; the banner carries the state.
    _set_ind("ind_armed",
             f"DISARM  [{arm_key}]" if armed else f"ARM  [{arm_key}]",
             "arm_live"             if armed else "arm_ready")
    if locked:
        _set_ind("ind_wpn_lock", "UNLOCK WEAPON", "lock_locked")
    else:
        # Pulse at 1 Hz while live so the unlocked state is obvious.
        pulse = "lock_hot" if int(time.time() * 2) % 2 else "lock_live"
        _set_ind("ind_wpn_lock", "LOCK WEAPON", pulse)
    _set_ind("btn_kill", f"KILL ROBOT  [{kill_key}]", "kill_ready")
    dpg.configure_item("btn_kill", show=not kill)
    dpg.configure_item("btn_kill_reset", show=kill)
    _set_ind("ind_weapon",
             {"safe": "WEAPON SAFE", "idle": "WEAPON IDLE", "attack": "WEAPON ATTACK", "spinup": "WEAPON SPIN-UP"}[ws],
             {"safe": "panel",       "idle": "warn",        "attack": "attack",         "spinup": "warn"}[ws])
    _set_ind("ind_drive",
             "DRIVE INVERTED" if inv  else "DRIVE NORMAL",
             "warn"           if inv  else "panel")
    _set_ind("ind_kill",
             "KILLSWITCH!"    if kill else "KILL OFF",
             "danger"         if kill else "panel")

    now = time.time()
    dname = "FWD" if _test["dir"] > 0 else "REV"
    remaining = max(0.0, _test["deadline"] - now)
    test_live = _test["enabled"] and remaining > 0.0
    if test_live:
        pulse = "test_hot" if int(now * 2) % 2 else "test_live"
        _set_ind("btn_test_spin", f"KEEP SPINNING  {remaining:0.1f}s", pulse)
        dpg.set_value("txt_test_status",
                      f"LIVE: {_test['mag']}% {dname} - re-press within {remaining:0.1f}s")
        dpg.configure_item("txt_test_status", color=C_WARN[:3])
    elif _test["enabled"]:
        _set_ind("btn_test_spin", f"RESUME {_test['mag']}% {dname}", "test_ready")
        dpg.set_value("txt_test_status", "Paused - press SPIN to resume (no password)")
        dpg.configure_item("txt_test_status", color=C_DIM[:3])
    else:
        _set_ind("btn_test_spin", f"SPIN {_test['mag']}% {dname}", "test_ready")
        dpg.set_value("txt_test_status",
                      "Idle. SPIN needs the password once, then re-press every 5 s.")
        dpg.configure_item("txt_test_status", color=C_DIM[:3])

    if kill:
        _set_banner("KILLSWITCH LATCHED",
                    "failsafe sent - power cycle the robot to recover", "kill")
    elif test_live:
        _set_banner(f"WEAPON TEST  {_test['mag']}% {dname}",
                    f"bench test live - re-press SPIN within {remaining:0.1f}s", "test")
    elif _test["enabled"]:
        _set_banner("WEAPON TEST PAUSED", "press SPIN to resume", "test")
    elif armed and not locked:
        _set_banner("ARMED - WEAPON LIVE", "weapon controls enabled", "live")
    elif armed:
        _set_banner("ARMED", "drive live - weapon locked", "armed")
    else:
        _set_banner("DISARMED",
                    f"outputs neutral - press [{arm_key}] or click ARM to go live",
                    "disarmed")

    if _log_shown_rev != _log_rev:
        _log_shown_rev = _log_rev
        lines = list(_log)
        for i in range(LOG_SLOTS):
            idx = len(lines) - 1 - i
            if idx >= 0:
                s = lines[idx]
                dpg.set_value(f"log_{i}", s)
                dpg.configure_item(f"log_{i}", color=_log_color(s, i == 0), show=True)
            else:
                dpg.configure_item(f"log_{i}", show=False)

    def _fmt(label: str, action: str) -> str:
        k = key_display(keys.get(action, ""))
        g = gp_display(btns.get(action))
        return f"{label:<10}{k:<10}{g}"

    rows = [
        _fmt("Weapon",   "weapon"),
        _fmt("W.Atk/Rv", "weapon_rev"),
        _fmt("Kill",     "killswitch"),
        _fmt("Arm",      "arm"),
        _fmt("Invert",   "drive_invert"),
    ]
    dpg.set_value("txt_controls", "\n".join(rows))

    vw = dpg.get_viewport_width()
    vh = dpg.get_viewport_height()
    dpg.set_item_width("primary", vw)
    dpg.set_item_height("primary", vh)


# ─── Entry point ─────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="HCR Mission Control")
    parser.add_argument("--calibrate", action="store_true",
                        help="Show gamepad axis/button numbers")
    parser.add_argument("--set-weapon-password", action="store_true",
                        help="Set the weapon unlock password and exit")
    parser.add_argument("--debug", action="store_true",
                        help="Print every TX packet. Costly: at rate_hz this "
                             "can starve the UI thread on Windows.")
    args = parser.parse_args()

    if args.calibrate:
        calibrate()
        return

    if args.set_weapon_password:
        cfg = json.loads(CONFIG_PATH.read_text())
        pw1 = getpass.getpass("New weapon password (blank to disable): ")
        pw2 = getpass.getpass("Repeat: ")
        if pw1 != pw2:
            print("Passwords did not match. Nothing changed.")
            return
        cfg.setdefault("safety", {})["weapon_password_sha256"] = (
            hashlib.sha256(pw1.encode()).hexdigest() if pw1 else "")
        CONFIG_PATH.write_text(json.dumps(cfg, indent=2) + "\n")
        print("Password disabled." if not pw1 else "Password updated.")
        print("Note: this is an interlock against accidental activation, not")
        print("access control. Anyone who can edit config.json can replace it.")
        return

    cfg  = json.loads(CONFIG_PATH.read_text())
    link = SerialLink(cfg)

    global _weapon_pw_hash, _relock_on_disarm
    _safety = cfg.get("safety", {})
    _weapon_pw_hash   = _safety.get("weapon_password_sha256", "")
    _relock_on_disarm = _safety.get("relock_on_disarm", True)
    global _failsafe_on_dongle_removal
    _failsafe_on_dongle_removal = _safety.get("failsafe_on_dongle_removal", True)
    if not _weapon_pw_hash:
        _log_add("No weapon password set - unlock needs only a confirmation")

    pygame.init()

    dpg.create_context()
    init_keymap()
    dpg.create_viewport(
        title="HCR Mission Control",
        width=cfg["ui"]["width"], height=cfg["ui"]["height"],
        resizable=True, min_width=960, min_height=640,
    )
    dpg.setup_dearpygui()
    dpg.show_viewport()

    mapper = InputMapper(DRIVE_MODES[_mode_idx])
    _build_ui(cfg, link, mapper)

    if link.ensure_connected():
        _log_add(f"Serial connected: {link.port_name}")
    else:
        _log_add("Serial searching...")
    _log_add(f"Gamepad: {mapper.joystick_name}" if mapper.joystick_name
             else "No gamepad - keyboard only")
    _log_add(f"Drive mode: {DRIVE_MODES[_mode_idx]['name']}")

    rate_hz   = cfg["serial"]["rate_hz"]
    last_send = 0.0
    prev_inv = prev_arm = prev_wpn = False
    prev_link_connected = (link.state == "connected")
    prev_test_spin = False

    while dpg.is_dearpygui_running():
        now = time.time()

        for event in pygame.event.get():
            msg = mapper.handle_event(event)
            if msg:
                _log_add(msg)

        mapper.kb_blocked = keyboard_captured()

        inv_raw  = mapper.read_button("drive_invert")
        kill_raw = mapper.read_button("killswitch")
        arm_raw  = mapper.read_button("arm")
        wpn_btn  = mapper.read_button("weapon")
        wpn_rev  = mapper.read_button("weapon_rev")
        axis_a, axis_b = mapper.read_axes()

        if inv_raw and not prev_inv:
            _gs["drive_inverted"] = not _gs["drive_inverted"]
            _log_add(f"Drive invert {'ON' if _gs['drive_inverted'] else 'OFF'}")

        motor_l, motor_r = drive.drive_bytes(
            DRIVE_MODES[_mode_idx]["mix"], axis_a, axis_b,
            mult_l=_mult["L"], mult_r=_mult["R"],
            # Trim is applied by the robot; applying it here too would double it.
            invert=_gs["drive_inverted"],
        )

        if kill_raw:
            trigger_killswitch(link)

        # A deadman lapse pauses (weapon off) but keeps the session armed, so a
        # re-press resumes without the password. STOP or killswitch end it.
        if _gs["killswitch"]:
            _test["enabled"] = False
        test_spinning = test_should_spin(_test["enabled"], now, _test["deadline"],
                                         _gs["killswitch"], link.state == "connected")
        if prev_test_spin and not test_spinning and _test["enabled"] and now >= _test["deadline"]:
            _log_add("Weapon test paused - press SPIN to resume")
        prev_test_spin = test_spinning

        if arm_raw and not prev_arm and not _test["enabled"]:
            _gs["armed"] = not _gs["armed"]
            _log_add(f"Robot {'ARMED' if _gs['armed'] else 'DISARMED'}")

        if outputs_inhibited(_gs["armed"], _gs["killswitch"]):
            motor_l = motor_r = NEUTRAL
            _gs["weapon_state"] = "safe"

        if not weapon_permitted(_gs["armed"], _gs["killswitch"], _gs["weapon_locked"]):
            _gs["weapon_state"] = "safe"
        else:
            if wpn_btn and not prev_wpn:
                # Toggle weapon on (fwd idle) / off — also exits soft spin-up
                _gs["weapon_state"] = "idle" if _gs["weapon_state"] in ("safe", "spinup") else "safe"
            elif _gs["weapon_state"] == "idle" and wpn_rev:
                _gs["weapon_state"] = "attack"       # hold to escalate fwd
            elif _gs["weapon_state"] == "attack" and not wpn_rev:
                _gs["weapon_state"] = "idle"
            elif _gs["weapon_state"] == "safe" and wpn_rev:
                _gs["weapon_state"] = "spinup"       # hold in safe = slow spin-up
            elif _gs["weapon_state"] == "spinup" and not wpn_rev:
                _gs["weapon_state"] = "safe"

        weapon_byte = WEAPON_BYTES[_gs["weapon_state"]]
        fs_byte     = failsafe_byte(kill_raw, _gs["killswitch"])

        prev_inv     = inv_raw
        prev_arm     = arm_raw
        prev_wpn     = wpn_btn

        if now - last_send >= 1.0 / rate_hz:
            if test_spinning:
                pkt = weapon_test_packet(_test["mag"] * _test["dir"])
            else:
                pkt = _hex_packet(motor_l, motor_r, weapon_byte, fs_byte)
            was_searching = link.state == "searching"
            if link.ensure_connected():
                if was_searching:
                    _log_add(f"Serial connected: {link.port_name}")
                if link.send(pkt):
                    if args.debug:
                        print(f"[TX] {pkt.strip().decode()}  "
                              f"motors=({motor_l},{motor_r}) "
                              f"weapon={weapon_byte} fs={fs_byte}")
                else:
                    _log_add("Serial write failed")
            last_send = now

        now_connected = (link.state == "connected")
        if dongle_pull_kills(prev_link_connected, now_connected,
                             _failsafe_on_dongle_removal, _gs["killswitch"]):
            _gs["killswitch"] = True
            _test["enabled"] = False
            _log_add("Dongle disconnected - failsafe latched, robot killed on reconnect")
        prev_link_connected = now_connected

        _update_ui(link, mapper, motor_l, motor_r)

        dpg.render_dearpygui_frame()

    dpg.destroy_context()
    pygame.quit()
    print("Ground station shut down.")


if __name__ == "__main__":
    main()
