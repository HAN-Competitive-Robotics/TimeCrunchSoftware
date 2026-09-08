#!/usr/bin/env python3
"""HCR Mission Control — Dear PyGui driver station."""
from __future__ import annotations

import os, sys, json, time, argparse
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
LEFT_W  = 250
BAR_W   = 62
BAR_H   = 200
BAR_CY  = BAR_H // 2
BAR_PAD = (LEFT_W - BAR_W * 2 - 10) // 2

LOG_N  = 8
LOG_H  = 120

# ─── Palette ─────────────────────────────────────────────────────────────────
C_BG     = [30,  30,  35,  255]
C_PANEL  = [45,  45,  55,  255]
C_BORDER = [65,  65,  78,  255]
C_TEXT   = [220, 220, 220, 255]
C_DIM    = [110, 110, 122, 255]
C_ACCENT = [0,   200, 255, 255]
C_GOOD   = [60,  220, 110, 255]
C_WARN   = [255, 175, 0,   255]
C_DANGER = [255, 60,  60,  255]
C_FWD    = [40,  210, 100, 255]
C_REV    = [210, 70,  70,  255]

# ─── Runtime state ────────────────────────────────────────────────────────────
_log: deque[str] = deque(maxlen=LOG_N)

_gs: dict = {
    "drive_inverted": False,
    "weapon_state":   "safe",
    "armed":          False,
    "killswitch":     False,
}

_mode_idx: int = 0                # index into drive_modes.DRIVE_MODES
_IND: dict[str, int] = {}
_trim: dict = {"L": 0, "R": 0}    # raw offset −127…+127
_mult: dict = {"L": 1.0, "R": 1.0}  # output multiplier 0.0…5.0


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _log_add(msg: str) -> None:
    _log.append(f"[{time.strftime('%H:%M:%S')}] {msg}")


# Must match robot/main/include/robot_config.h. The failsafe byte doubles as
# an opcode so commands fit the existing 4-byte payload.
OPCODE_DRIVE    = 0
OPCODE_SET_TRIM = 1
TRIM_MAGIC      = 0x5A


def _hex_packet(ml: int, mr: int, wb: int, fb: int) -> bytes:
    return f"{ml:02x}{mr:02x}{wb:02x}{fb:02x}\n".encode()


def trim_packet(trim_l: int, trim_r: int) -> bytes:
    """Encode a set-trim command. Trim is offset by 127 so it fits a byte."""
    return _hex_packet(max(0, min(255, 127 + trim_l)),
                       max(0, min(255, 127 + trim_r)),
                       TRIM_MAGIC, OPCODE_SET_TRIM)


# ─── Indicator buttons ────────────────────────────────────────────────────────

def _make_ind_themes() -> None:
    specs: dict[str, tuple] = {
        "panel":  ((50,  50,  62),  (160, 160, 170)),
        "good":   ((40,  160, 80),  (230, 255, 230)),
        "warn":   ((180, 125, 0),   (255, 240, 160)),
        "danger": ((175, 35,  35),  (255, 200, 200)),
        "attack": ((150, 20,  20),  (255, 170, 170)),
    }
    for name, (bg, fg) in specs.items():
        with dpg.theme() as t:
            with dpg.theme_component(dpg.mvButton):
                dpg.add_theme_color(dpg.mvThemeCol_Button,        bg)
                dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered, bg)
                dpg.add_theme_color(dpg.mvThemeCol_ButtonActive,  bg)
                dpg.add_theme_color(dpg.mvThemeCol_Text,          fg)
        _IND[name] = t


def _set_ind(tag: str, label: str, theme: str) -> None:
    dpg.configure_item(tag, label=label)
    dpg.bind_item_theme(tag, _IND[theme])


# ─── Motor bars ───────────────────────────────────────────────────────────────

def _make_bar(side: str) -> None:
    dpg.add_text(side, color=C_DIM[:3], indent=BAR_W // 2 - 4)
    with dpg.drawlist(width=BAR_W, height=BAR_H, tag=f"dl_{side}"):
        dpg.draw_rectangle([0, 0], [BAR_W, BAR_H],
                           fill=C_PANEL[:3], color=[0, 0, 0, 0], tag=f"dr_bg_{side}")
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
    dpg.add_text("127", tag=f"txt_val_{side}", color=C_TEXT[:3],
                 indent=BAR_W // 2 - 8)


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


# ─── Key shortcuts ────────────────────────────────────────────────────────────

def _on_key_press(sender, key_code, user_data) -> None:
    """Only shortcut left: T cycles the drive mode.

    Bindings themselves live in drive_modes.py and are not editable here by
    design, so there is no capture flow and no editor window any more.
    """
    cycle_mode = user_data
    if key_code == getattr(dpg, "mvKey_T", None):
        cycle_mode()


# ─── UI construction ──────────────────────────────────────────────────────────

def _build_ui(cfg: dict, link: SerialLink, mapper: InputMapper):
    """Builds the HUD. Returns the drive-mode cycle callback so main() can
    bind it to the T key."""
    with dpg.theme() as g_theme:
        with dpg.theme_component(dpg.mvAll):
            dpg.add_theme_color(dpg.mvThemeCol_WindowBg,         (30, 30, 35))
            dpg.add_theme_color(dpg.mvThemeCol_ChildBg,          (30, 30, 35))
            dpg.add_theme_color(dpg.mvThemeCol_FrameBg,          (45, 45, 55))
            dpg.add_theme_color(dpg.mvThemeCol_FrameBgHovered,   (55, 55, 67))
            dpg.add_theme_color(dpg.mvThemeCol_Button,           (50, 50, 63))
            dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered,    (65, 65, 80))
            dpg.add_theme_color(dpg.mvThemeCol_ButtonActive,     (0, 155, 205))
            dpg.add_theme_color(dpg.mvThemeCol_Text,             (220, 220, 220))
            dpg.add_theme_color(dpg.mvThemeCol_TitleBg,          (22, 22, 28))
            dpg.add_theme_color(dpg.mvThemeCol_TitleBgActive,    (28, 28, 36))
            dpg.add_theme_color(dpg.mvThemeCol_ScrollbarBg,      (25, 25, 32))
            dpg.add_theme_color(dpg.mvThemeCol_ScrollbarGrab,    (65, 65, 80))
            dpg.add_theme_color(dpg.mvThemeCol_Separator,        (60, 60, 72))
            dpg.add_theme_color(dpg.mvThemeCol_Header,           (0, 140, 190, 150))
            dpg.add_theme_color(dpg.mvThemeCol_HeaderHovered,    (0, 190, 240, 200))
            dpg.add_theme_color(dpg.mvThemeCol_HeaderActive,     (0, 200, 255))
            dpg.add_theme_color(dpg.mvThemeCol_PopupBg,          (28, 28, 38))
            dpg.add_theme_color(dpg.mvThemeCol_TableHeaderBg,    (38, 38, 50))
            dpg.add_theme_color(dpg.mvThemeCol_TableRowBg,       (30, 30, 35))
            dpg.add_theme_color(dpg.mvThemeCol_TableRowBgAlt,    (36, 36, 46))
            dpg.add_theme_color(dpg.mvThemeCol_TableBorderLight, (62, 62, 76))
            dpg.add_theme_color(dpg.mvThemeCol_PlotLines,        (0, 200, 255))
            dpg.add_theme_style(dpg.mvStyleVar_WindowRounding,  0)
            dpg.add_theme_style(dpg.mvStyleVar_FrameRounding,   4)
            dpg.add_theme_style(dpg.mvStyleVar_GrabRounding,    4)
            dpg.add_theme_style(dpg.mvStyleVar_ItemSpacing,     8, 5)
            dpg.add_theme_style(dpg.mvStyleVar_FramePadding,    8, 5)
            dpg.add_theme_style(dpg.mvStyleVar_WindowPadding,   12, 10)
            dpg.add_theme_style(dpg.mvStyleVar_CellPadding,     6, 4)
    dpg.bind_theme(g_theme)
    _make_ind_themes()

    # ── Callbacks ─────────────────────────────────────────────────────────────
    def _apply_mode() -> None:
        """Everything that has to happen when the drive mode changes.

        Weapon is re-safed and invert cleared, because a control layout change
        mid-match should never leave the weapon spun up under a binding the
        driver has not adjusted to yet.
        """
        mode = DRIVE_MODES[_mode_idx]
        mapper.set_mode(mode)
        _gs["drive_inverted"] = False
        _gs["weapon_state"]   = "safe"
        dpg.configure_item("btn_drive", label=f"T: {mode['name'].upper()}")
        dpg.set_value("cmb_mode", mode["name"])
        dpg.set_value("txt_hint", mode["hint"])
        _log_add(f"Drive mode: {mode['name']}")

    def cb_cycle_mode(s=None, a=None, u=None):
        global _mode_idx
        _mode_idx = (_mode_idx + 1) % len(DRIVE_MODES)
        _apply_mode()

    def cb_mode_select(s, val, u):
        global _mode_idx
        _mode_idx = index_of(val)
        _apply_mode()

    def cb_arm_click(s, a, u):
        _gs["armed"] = not _gs["armed"]
        _log_add(f"Robot {'ARMED' if _gs['armed'] else 'DISARMED'}")

    def cb_save_trim(s_, a, u):
        """Push trim to the robot, which stores it in NVS and applies it.

        Refused while armed: the robot cannot tell a trim packet from a drive
        packet being unsafe to act on, so the guard has to live here. Sent
        several times because the link is one-way and lossy, and there is no
        acknowledgement to wait for.
        """
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

    with dpg.handler_registry():
        dpg.add_key_press_handler(callback=_on_key_press,
                                  user_data=cb_cycle_mode)

    # ── Primary window ────────────────────────────────────────────────────────
    with dpg.window(tag="primary", no_title_bar=True, no_move=True,
                    no_resize=True, no_close=True, no_collapse=True,
                    no_scrollbar=True):

        with dpg.table(header_row=False, policy=dpg.mvTable_SizingFixedFit,
                       pad_outerX=False):
            dpg.add_table_column(width_stretch=True)
            dpg.add_table_column(width_fixed=True, init_width_or_weight=420)
            with dpg.table_row():
                with dpg.table_cell():
                    dpg.add_text("HCR MISSION CONTROL", color=C_ACCENT[:3])
                with dpg.table_cell():
                    with dpg.group(horizontal=True):
                        dpg.add_button(
                            label=f"T: {DRIVE_MODES[_mode_idx]['name'].upper()}",
                            tag="btn_drive", callback=cb_cycle_mode, width=150)
                        dpg.add_combo(
                            tag="cmb_mode", width=170,
                            items=MODE_NAMES,
                            default_value=DRIVE_MODES[_mode_idx]["name"],
                            callback=cb_mode_select)

        with dpg.group(horizontal=True):
            dpg.add_text("o SEARCHING...",  tag="txt_serial",  color=C_WARN[:3])
            dpg.add_text("  |  ",           color=C_DIM[:3])
            dpg.add_text("o NO GAMEPAD",    tag="txt_gamepad", color=C_WARN[:3])
            dpg.add_text("  |  ",           color=C_DIM[:3])
            dpg.add_text("0.0 Hz  |  - ms", tag="txt_stats",   color=C_DIM[:3])

        dpg.add_text(DRIVE_MODES[_mode_idx]["hint"], tag="txt_hint", color=C_DIM[:3])

        dpg.add_separator()

        with dpg.group(horizontal=True):

            # ── Left: motor bars + expo curve ─────────────────────────────────
            with dpg.child_window(width=LEFT_W, border=False,
                                  no_scrollbar=True, tag="w_left"):
                with dpg.group(horizontal=True):
                    dpg.add_spacer(width=BAR_PAD)
                    with dpg.group():
                        _make_bar("L")
                    dpg.add_spacer(width=10)
                    with dpg.group():
                        _make_bar("R")

                dpg.add_spacer(height=4)
                dpg.add_text("", tag="txt_stats2", color=C_DIM[:3], wrap=0)

                dpg.add_spacer(height=6)
                dpg.add_text("TRIM", color=C_DIM[:3])
                with dpg.group(horizontal=True):
                    dpg.add_text("L", color=C_DIM[:3])
                    dpg.add_button(label="-", width=22, callback=cb_trim_L_dec)
                    dpg.add_slider_int(tag="sl_trim_L", min_value=-127, max_value=127,
                                       default_value=0, width=90, format="%d",
                                       callback=cb_trim_L)
                    dpg.add_button(label="+", width=22, callback=cb_trim_L_inc)
                    dpg.add_input_int(tag="inp_trim_L", default_value=0,
                                      min_value=-127, max_value=127,
                                      min_clamped=True, max_clamped=True,
                                      width=55, step=0, on_enter=True,
                                      callback=cb_trim_L_inp)
                with dpg.group(horizontal=True):
                    dpg.add_text("R", color=C_DIM[:3])
                    dpg.add_button(label="-", width=22, callback=cb_trim_R_dec)
                    dpg.add_slider_int(tag="sl_trim_R", min_value=-127, max_value=127,
                                       default_value=0, width=90, format="%d",
                                       callback=cb_trim_R)
                    dpg.add_button(label="+", width=22, callback=cb_trim_R_inc)
                    dpg.add_input_int(tag="inp_trim_R", default_value=0,
                                      min_value=-127, max_value=127,
                                      min_clamped=True, max_clamped=True,
                                      width=55, step=0, on_enter=True,
                                      callback=cb_trim_R_inp)
                dpg.add_button(label="Save trim to robot", tag="btn_save_trim",
                               callback=cb_save_trim, width=200)

                dpg.add_spacer(height=6)
                dpg.add_text("MULT", color=C_DIM[:3])
                with dpg.group(horizontal=True):
                    dpg.add_text("L", color=C_DIM[:3])
                    dpg.add_button(label="-", width=22, callback=cb_mult_L_dec)
                    dpg.add_slider_float(tag="sl_mult_L", min_value=0.0, max_value=5.0,
                                         default_value=1.0, width=90, format="%.2f",
                                         callback=cb_mult_L)
                    dpg.add_button(label="+", width=22, callback=cb_mult_L_inc)
                    dpg.add_input_float(tag="inp_mult_L", default_value=1.0,
                                        min_value=0.0, max_value=5.0,
                                        min_clamped=True, max_clamped=True,
                                        width=55, step=0, on_enter=True,
                                        format="%.2f", callback=cb_mult_L_inp)
                with dpg.group(horizontal=True):
                    dpg.add_text("R", color=C_DIM[:3])
                    dpg.add_button(label="-", width=22, callback=cb_mult_R_dec)
                    dpg.add_slider_float(tag="sl_mult_R", min_value=0.0, max_value=5.0,
                                         default_value=1.0, width=90, format="%.2f",
                                         callback=cb_mult_R)
                    dpg.add_button(label="+", width=22, callback=cb_mult_R_inc)
                    dpg.add_input_float(tag="inp_mult_R", default_value=1.0,
                                        min_value=0.0, max_value=5.0,
                                        min_clamped=True, max_clamped=True,
                                        width=55, step=0, on_enter=True,
                                        format="%.2f", callback=cb_mult_R_inp)


            dpg.add_spacer(width=8)

            # ── Right: controls + indicators + log ────────────────────────────
            with dpg.child_window(border=False, no_scrollbar=True, tag="w_right"):

                dpg.add_text("CONTROLS", color=C_ACCENT[:3])
                dpg.add_text("", tag="txt_controls", color=C_TEXT[:3], wrap=0)

                dpg.add_separator()

                with dpg.table(header_row=False, policy=dpg.mvTable_SizingStretchSame,
                               pad_outerX=False, borders_outerH=False,
                               borders_outerV=False, borders_innerV=False):
                    dpg.add_table_column()
                    dpg.add_table_column()
                    with dpg.table_row():
                        with dpg.table_cell():
                            dpg.add_button(label="DISARMED", tag="ind_armed",
                                           height=34, width=-1, callback=cb_arm_click)
                        with dpg.table_cell():
                            dpg.add_button(label="WEAPON SAFE", tag="ind_weapon",
                                           height=34, width=-1)
                    with dpg.table_row():
                        with dpg.table_cell():
                            dpg.add_button(label="DRIVE NORMAL", tag="ind_drive",
                                           height=34, width=-1)
                        with dpg.table_cell():
                            dpg.add_button(label="KILLSWITCH OFF", tag="ind_kill",
                                           height=34, width=-1)

                _set_ind("ind_armed",  "DISARMED",    "danger")
                _set_ind("ind_weapon", "WEAPON SAFE", "panel")
                _set_ind("ind_drive",  "DRIVE NORMAL",   "panel")
                _set_ind("ind_kill",   "KILLSWITCH OFF", "panel")

                with dpg.tooltip("ind_armed"):
                    dpg.add_text("Click (or press arm key) to toggle arm state.")
                    dpg.add_text("Robot ignores drive while DISARMED.")
                with dpg.tooltip("ind_weapon"):
                    dpg.add_text("SAFE   = weapon off         (byte 127)")
                    dpg.add_text("IDLE   = spinning low fwd   (byte 160)")
                    dpg.add_text("ATTACK = full speed fwd     (byte 255)")
                    dpg.add_text("REV    = spinning low rev   (byte 95)")
                    dpg.add_text("Atk/Rev key: hold in IDLE=attack, hold in SAFE=reverse spin.")
                with dpg.tooltip("ind_kill"):
                    dpg.add_text("Sends failsafe byte=255.")
                    dpg.add_text("Robot enters deep sleep — power cycle to recover.")

                dpg.add_separator()

                dpg.add_text("EVENT LOG", color=C_ACCENT[:3])
                with dpg.child_window(tag="w_log", height=-1,
                                      border=False, horizontal_scrollbar=False):
                    for i in range(LOG_N):
                        dpg.add_text("", tag=f"log_{i}", color=C_DIM[:3])

    # Without this the HUD is an ordinary floating window: it renders inset
    # from the top-left with dead space around it and clips on the right.
    dpg.set_primary_window("primary", True)

    return cb_cycle_mode


# ─── Per-frame UI update ──────────────────────────────────────────────────────

def _update_ui(link: SerialLink, mapper: InputMapper,
               ml: int, mr: int) -> None:

    if link.state == "connected":
        dpg.set_value("txt_serial", f"* SERIAL OK  ({link.port_name})")
        dpg.configure_item("txt_serial", color=C_GOOD[:3])
    elif link.state == "searching":
        dpg.set_value("txt_serial", "o SEARCHING...")
        dpg.configure_item("txt_serial", color=C_WARN[:3])
    else:
        dpg.set_value("txt_serial", "x SERIAL LOST")
        dpg.configure_item("txt_serial", color=C_DANGER[:3])

    if mapper.joystick_name:
        dpg.set_value("txt_gamepad", f"* {mapper.joystick_name}")
        dpg.configure_item("txt_gamepad", color=C_GOOD[:3])
    else:
        dpg.set_value("txt_gamepad", "o KEYBOARD ONLY")
        dpg.configure_item("txt_gamepad", color=C_WARN[:3])

    dpg.set_value("txt_stats",  f"{link.current_hz:.1f} Hz  |  {link.idle_ms} ms")
    dpg.set_value("txt_stats2", f"L={ml}  R={mr}")

    _update_bar("L", ml)
    _update_bar("R", mr)

    armed = _gs["armed"]
    ws    = _gs["weapon_state"]
    inv   = _gs["drive_inverted"]
    kill  = _gs["killswitch"]

    _set_ind("ind_armed",
             "ARMED"    if armed else "DISARMED",
             "good"     if armed else "danger")
    _set_ind("ind_weapon",
             {"safe": "WEAPON SAFE", "idle": "WEAPON IDLE", "attack": "WEAPON ATTACK", "idle_rev": "WEAPON REV"}[ws],
             {"safe": "panel",       "idle": "warn",        "attack": "attack",         "idle_rev": "warn"}[ws])
    _set_ind("ind_drive",
             "DRIVE INVERTED" if inv  else "DRIVE NORMAL",
             "warn"           if inv  else "panel")
    _set_ind("ind_kill",
             "KILLSWITCH!"    if kill else "KILLSWITCH OFF",
             "danger"         if kill else "panel")

    lines = list(_log)
    for i in range(LOG_N):
        idx = len(lines) - LOG_N + i
        dpg.set_value(f"log_{i}", lines[idx] if 0 <= idx < len(lines) else "")

    mode = DRIVE_MODES[_mode_idx]
    keys = mode["keys"]
    btns = mode["buttons"]

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
    parser.add_argument("--debug", action="store_true",
                        help="Print every TX packet. Costly: at rate_hz this "
                             "can starve the UI thread on Windows.")
    args = parser.parse_args()

    if args.calibrate:
        calibrate()
        return

    cfg  = json.loads(CONFIG_PATH.read_text())
    link = SerialLink(cfg)

    pygame.init()

    dpg.create_context()
    init_keymap()
    dpg.create_viewport(
        title="HCR Mission Control",
        width=cfg["ui"]["width"], height=cfg["ui"]["height"],
        resizable=True, min_width=640, min_height=400,
    )
    dpg.setup_dearpygui()
    dpg.show_viewport()

    mapper = InputMapper(DRIVE_MODES[_mode_idx])
    cycle_mode = _build_ui(cfg, link, mapper)

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

    while dpg.is_dearpygui_running():
        now = time.time()

        for event in pygame.event.get():
            msg = mapper.handle_event(event)
            if msg:
                _log_add(msg)

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
            # Trim is applied by the robot, from its own saved value. Applying
            # it here as well would double it. See cb_save_trim.
            invert=_gs["drive_inverted"],
        )

        if kill_raw and not _gs["killswitch"]:
            _gs["killswitch"] = True
            _log_add("KILLSWITCH - robot latched until power cycle")
            burst = b"7f7f7fff\n"
            if link.ensure_connected():
                for _ in range(5):
                    link.send(burst)
            else:
                _log_add("WARNING: killswitch sent but serial not connected")

        if arm_raw and not prev_arm:
            _gs["armed"] = not _gs["armed"]
            _log_add(f"Robot {'ARMED' if _gs['armed'] else 'DISARMED'}")

        if not _gs["armed"]:
            motor_l = motor_r = 127
            _gs["weapon_state"] = "safe"

        if _gs["armed"]:
            if wpn_btn and not prev_wpn:
                # Toggle weapon on (fwd idle) / off — also exits reverse spin
                _gs["weapon_state"] = "idle" if _gs["weapon_state"] in ("safe", "idle_rev") else "safe"
            elif _gs["weapon_state"] == "idle" and wpn_rev:
                _gs["weapon_state"] = "attack"       # hold to escalate fwd
            elif _gs["weapon_state"] == "attack" and not wpn_rev:
                _gs["weapon_state"] = "idle"
            elif _gs["weapon_state"] == "safe" and wpn_rev:
                _gs["weapon_state"] = "idle_rev"     # hold in safe = reverse spin
            elif _gs["weapon_state"] == "idle_rev" and not wpn_rev:
                _gs["weapon_state"] = "safe"

        weapon_byte = {"safe": 127, "idle": 160, "attack": 255, "idle_rev": 95}[_gs["weapon_state"]]

        failsafe_byte = 255 if (kill_raw or _gs["killswitch"]) else 0

        prev_inv     = inv_raw
        prev_arm     = arm_raw
        prev_wpn     = wpn_btn

        if now - last_send >= 1.0 / rate_hz:
            pkt = _hex_packet(motor_l, motor_r, weapon_byte, failsafe_byte)
            was_searching = link.state == "searching"
            if link.ensure_connected():
                if was_searching:
                    _log_add(f"Serial connected: {link.port_name}")
                if link.send(pkt):
                    if args.debug:
                        print(f"[TX] {pkt.strip().decode()}  "
                              f"motors=({motor_l},{motor_r}) "
                              f"weapon={weapon_byte} fs={failsafe_byte}")
                else:
                    _log_add("Serial write failed")
            last_send = now

        _update_ui(link, mapper, motor_l, motor_r)

        dpg.render_dearpygui_frame()

    dpg.destroy_context()
    pygame.quit()
    print("Ground station shut down.")


if __name__ == "__main__":
    main()
