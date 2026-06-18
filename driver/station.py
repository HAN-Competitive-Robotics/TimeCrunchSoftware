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

from profiles    import ProfileManager, BINDABLE_ACTIONS, _DEFAULT_KEYBINDS
from keymap      import init_keymap, resolve_key, dpg_key_to_name, key_display, gp_display
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

_cap: dict = {"active": False, "row": 0, "col": 0, "step": 0}
_IND: dict[str, int] = {}
_trim: dict = {"L": 0, "R": 0}    # raw offset −127…+127
_mult: dict = {"L": 1.0, "R": 1.0}  # output multiplier 0.0…5.0


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _log_add(msg: str) -> None:
    _log.append(f"[{time.strftime('%H:%M:%S')}] {msg}")


def _hex_packet(ml: int, mr: int, wb: int, fb: int) -> bytes:
    return f"{ml:02x}{mr:02x}{wb:02x}{fb:02x}\n".encode()


# ─── Font loading ─────────────────────────────────────────────────────────────

def _try_load_font() -> None:
    candidates = [
        Path.home() / "Library/Fonts/JetBrainsMono-Regular.ttf",
        Path("/Library/Fonts/JetBrainsMono-Regular.ttf"),
        Path.home() / "Library/Fonts/JetBrainsMonoNL-Regular.ttf",
        Path("/Library/Fonts/Hack-Regular.ttf"),
        Path("/Library/Fonts/FiraCode-Regular.ttf"),
    ]
    for path in candidates:
        if path.exists():
            try:
                with dpg.font_registry():
                    with dpg.font(str(path), 14) as fnt:
                        pass
                dpg.bind_font(fnt)
                return
            except Exception:
                pass


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


# ─── Keybind table ────────────────────────────────────────────────────────────

def _refresh_kb_table(profiles: ProfileManager) -> None:
    kb = profiles.active.get("keybinds", {})
    gp = profiles.active.get("gamepad", {})
    for i, (_, _, is_axis, kb_pos, kb_neg, gp_key) in enumerate(BINDABLE_ACTIONS):
        if _cap["active"] and _cap["row"] == i and _cap["col"] == 0:
            lbl = ("PRESS + KEY…" if _cap["step"] == 0 else "PRESS − KEY…") if is_axis else "PRESS KEY…"
            dpg.configure_item(f"kk_{i}", label=lbl)
            dpg.bind_item_theme(f"kk_{i}", _IND["warn"])
        else:
            lbl = (f"{key_display(kb.get(kb_pos))} / {key_display(kb.get(kb_neg))}"
                   if is_axis else key_display(kb.get(kb_pos, "")))
            dpg.configure_item(f"kk_{i}", label=lbl or "—")
            dpg.bind_item_theme(f"kk_{i}", 0)

        if _cap["active"] and _cap["row"] == i and _cap["col"] == 1:
            dpg.configure_item(f"gp_{i}", label="MOVE / PRESS…")
            dpg.bind_item_theme(f"gp_{i}", _IND["warn"])
        else:
            dpg.configure_item(f"gp_{i}", label=gp_display(gp.get(gp_key)) or "—")
            dpg.bind_item_theme(f"gp_{i}", 0)


def _handle_joy_capture(event, profiles: ProfileManager, mapper: InputMapper) -> None:
    if not _cap["active"] or _cap["col"] != 1:
        return
    _, _, is_axis, _, _, gp_key = BINDABLE_ACTIONS[_cap["row"]]
    if event.type == pygame.JOYBUTTONDOWN:
        cfg = {"button": event.button}
        profiles.set_gamepad_bind(gp_key, cfg)
        mapper.set_profile(profiles.active)
        _cap["active"] = False
        _log_add(f"Bound {gp_key}: B{event.button}")
    elif event.type == pygame.JOYAXISMOTION and abs(event.value) > 0.5:
        cfg = ({"axis": event.axis, "invert": event.value < 0, "deadzone": 0.15}
               if is_axis else {"axis": event.axis, "threshold": 0.5})
        profiles.set_gamepad_bind(gp_key, cfg)
        mapper.set_profile(profiles.active)
        _cap["active"] = False
        _log_add(f"Bound {gp_key}: {gp_display(cfg)}")


# ─── DPG key-press handler ────────────────────────────────────────────────────

def _on_key_press(sender, key_code, user_data) -> None:
    profiles: ProfileManager
    mapper: InputMapper
    profiles, mapper = user_data

    if key_code == dpg.mvKey_F2 and not _cap["active"]:
        if dpg.is_item_shown("kb_win"):
            _cap["active"] = False
            dpg.hide_item("kb_win")
        else:
            _refresh_kb_table(profiles)
            dpg.show_item("kb_win")
        return

    if key_code == dpg.mvKey_Escape:
        if _cap["active"]:
            _cap["active"] = False
        elif dpg.is_item_shown("kb_win"):
            dpg.hide_item("kb_win")
        return

    if not _cap["active"] or _cap["col"] != 0:
        return

    name = dpg_key_to_name(key_code)
    if name is None or name in ("escape", "f2"):
        return

    _, _, is_axis, kb_pos, kb_neg, _ = BINDABLE_ACTIONS[_cap["row"]]
    if is_axis:
        if _cap["step"] == 0:
            profiles.set_keybind(kb_pos, name)
            mapper.set_profile(profiles.active)
            _cap["step"] = 1
        else:
            profiles.set_keybind(kb_neg, name)
            mapper.set_profile(profiles.active)
            _cap["active"] = False
            _log_add(f"Bound {kb_pos}/{kb_neg}")
    else:
        profiles.set_keybind(kb_pos, name)
        mapper.set_profile(profiles.active)
        _cap["active"] = False
        _log_add(f"Bound {kb_pos}: {key_display(name)}")


# ─── UI construction ──────────────────────────────────────────────────────────

def _build_ui(cfg: dict, profiles: ProfileManager,
              link: SerialLink, mapper: InputMapper) -> None:

    _try_load_font()

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
    def cb_drive(s, a, u):
        profiles.toggle_drive_mode()
        mapper.set_profile(profiles.active)
        _gs["drive_inverted"] = False
        dpg.configure_item("btn_drive", label=f"T: {profiles.active['drive_mode'].upper()}")
        _log_add(f"Drive mode: {profiles.active['drive_mode'].upper()}")

    def cb_profile(s, val, u):
        idx = next(i for i, p in enumerate(profiles.profiles) if p["name"] == val)
        profiles.select(idx)
        mapper.set_profile(profiles.active)
        _gs["drive_inverted"] = False
        _gs["weapon_state"]   = "safe"
        dpg.configure_item("btn_drive", label=f"T: {profiles.active['drive_mode'].upper()}")
        if dpg.does_item_exist("inp_profile_name"):
            dpg.set_value("inp_profile_name", profiles.active["name"])
        if dpg.does_item_exist("sl_expo"):
            dpg.set_value("sl_expo", profiles.active.get("expo", 0.0))
        _log_add(f"Profile: {profiles.active['name']}")

    def cb_new(s, a, u):
        profiles.new_named("")
        mapper.set_profile(profiles.active)
        _gs["drive_inverted"] = False
        _gs["weapon_state"]   = "safe"
        dpg.configure_item("cmb_profile",
                           items=[p["name"] for p in profiles.profiles],
                           default_value=profiles.active["name"])
        dpg.configure_item("btn_drive", label=f"T: {profiles.active['drive_mode'].upper()}")
        _log_add(f"Created: {profiles.active['name']}")

    def cb_keybinds(s, a, u):
        _refresh_kb_table(profiles)
        dpg.set_value("inp_profile_name", profiles.active["name"])
        dpg.set_value("sl_expo", profiles.active.get("expo", 0.0))
        dpg.show_item("kb_win")

    def cb_del_profile(s, a, u):
        name = profiles.active["name"]
        if profiles.delete(profiles.active_idx):
            mapper.set_profile(profiles.active)
            _gs["drive_inverted"] = False
            _gs["weapon_state"]   = "safe"
            dpg.configure_item("cmb_profile",
                               items=[p["name"] for p in profiles.profiles],
                               default_value=profiles.active["name"])
            dpg.configure_item("btn_drive",
                               label=f"T: {profiles.active['drive_mode'].upper()}")
            dpg.hide_item("kb_win")
            _log_add(f"Deleted '{name}'")
        else:
            _log_add("Can't delete the last profile")

    def cb_close_kb(s, a, u):
        _cap["active"] = False
        dpg.hide_item("kb_win")

    def cb_kb_cell(s, a, u):
        row, col = u
        _cap.update(active=True, row=row, col=col, step=0)

    def cb_arm_click(s, a, u):
        _gs["armed"] = not _gs["armed"]
        _log_add(f"Robot {'ARMED' if _gs['armed'] else 'DISARMED'}")

    def cb_rename_profile(s, a, u):
        new_name = dpg.get_value("inp_profile_name").strip()
        if not new_name:
            return
        profiles.active["name"] = new_name
        profiles.save()
        dpg.configure_item("cmb_profile",
                           items=[p["name"] for p in profiles.profiles],
                           default_value=new_name)
        dpg.configure_item("kb_win", label="Keybinds — " + new_name)
        _log_add(f"Profile renamed: '{new_name}'")

    def cb_expo(s, val, u):
        profiles.active["expo"] = val
        profiles.save()
        mapper.set_profile(profiles.active)

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
                                  user_data=(profiles, mapper))

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
                            label=f"T: {profiles.active['drive_mode'].upper()}",
                            tag="btn_drive", callback=cb_drive, width=90)
                        dpg.add_combo(
                            tag="cmb_profile", width=170,
                            items=[p["name"] for p in profiles.profiles],
                            default_value=profiles.active["name"],
                            callback=cb_profile)
                        dpg.add_button(label="+", tag="btn_new",
                                       callback=cb_new, width=28)
                        dpg.add_button(label="F2: Keybinds", tag="btn_kb",
                                       callback=cb_keybinds, width=112)

        with dpg.group(horizontal=True):
            dpg.add_text("○ SEARCHING…",    tag="txt_serial",  color=C_WARN[:3])
            dpg.add_text("  │  ",            color=C_DIM[:3])
            dpg.add_text("○ NO GAMEPAD",    tag="txt_gamepad", color=C_WARN[:3])
            dpg.add_text("  │  ",            color=C_DIM[:3])
            dpg.add_text("0.0 Hz  │  — ms", tag="txt_stats",   color=C_DIM[:3])

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
                    dpg.add_text("SAFE = weapon off  (byte 127)")
                    dpg.add_text("IDLE = spinning low  (byte 160)")
                    dpg.add_text("ATTACK = full speed  (byte 255)")
                with dpg.tooltip("ind_kill"):
                    dpg.add_text("Sends failsafe byte=255.")
                    dpg.add_text("Robot enters deep sleep — power cycle to recover.")

                dpg.add_separator()

                dpg.add_text("EVENT LOG", color=C_ACCENT[:3])
                with dpg.child_window(tag="w_log", height=-1,
                                      border=False, horizontal_scrollbar=False):
                    for i in range(LOG_N):
                        dpg.add_text("", tag=f"log_{i}", color=C_DIM[:3])

    # ── Keybind editor ────────────────────────────────────────────────────────
    with dpg.window(tag="kb_win", label="Keybinds — " + profiles.active["name"],
                    show=False, modal=True,
                    width=680, height=580, no_collapse=True, pos=[50, 20]):

        with dpg.group(horizontal=True):
            dpg.add_text("Name:", color=C_DIM[:3])
            dpg.add_input_text(tag="inp_profile_name",
                               default_value=profiles.active["name"],
                               width=180)
            dpg.add_button(label="Rename", callback=cb_rename_profile, width=72)
            dpg.add_spacer(width=12)
            dpg.add_text("Expo:", color=C_DIM[:3])
            dpg.add_slider_float(tag="sl_expo",
                                 min_value=0.0, max_value=1.0,
                                 default_value=profiles.active.get("expo", 0.0),
                                 width=120, callback=cb_expo)

        dpg.add_text("Click a cell to capture.  ESC cancels.  F2 / close to exit.",
                     color=C_DIM[:3])
        dpg.add_separator()

        with dpg.table(header_row=True, tag="kb_tbl",
                       borders_innerH=True, borders_innerV=True,
                       borders_outerH=True, borders_outerV=True,
                       row_background=True, scrollY=True, height=-60):
            dpg.add_table_column(label="Action",   width_fixed=True, init_width_or_weight=185)
            dpg.add_table_column(label="Keyboard", width_fixed=True, init_width_or_weight=230)
            dpg.add_table_column(label="Gamepad",  width_stretch=True)
            for i, (_, label, _, _, _, _) in enumerate(BINDABLE_ACTIONS):
                with dpg.table_row():
                    dpg.add_text(f"  {label}")
                    dpg.add_button(label="—", tag=f"kk_{i}",
                                   width=-1, height=26,
                                   callback=cb_kb_cell, user_data=(i, 0))
                    dpg.add_button(label="—", tag=f"gp_{i}",
                                   width=-1, height=26,
                                   callback=cb_kb_cell, user_data=(i, 1))

        dpg.add_separator()
        with dpg.group(horizontal=True):
            dpg.add_button(label="Delete Profile", tag="kb_del",
                           callback=cb_del_profile, width=140)
            dpg.add_spacer(width=8)
            dpg.add_button(label="Close", callback=cb_close_kb, width=80)

    dpg.set_primary_window("primary", True)


# ─── Per-frame UI update ──────────────────────────────────────────────────────

def _update_ui(link: SerialLink, mapper: InputMapper,
               profiles: ProfileManager, ml: int, mr: int) -> None:

    if link.state == "connected":
        dpg.set_value("txt_serial", f"● SERIAL OK  ({link.port_name})")
        dpg.configure_item("txt_serial", color=C_GOOD[:3])
    elif link.state == "searching":
        dpg.set_value("txt_serial", "○ SEARCHING…")
        dpg.configure_item("txt_serial", color=C_WARN[:3])
    else:
        dpg.set_value("txt_serial", "✕ SERIAL LOST")
        dpg.configure_item("txt_serial", color=C_DANGER[:3])

    if mapper.joystick_name:
        dpg.set_value("txt_gamepad", f"● {mapper.joystick_name}")
        dpg.configure_item("txt_gamepad", color=C_GOOD[:3])
    else:
        dpg.set_value("txt_gamepad", "○ KEYBOARD ONLY")
        dpg.configure_item("txt_gamepad", color=C_WARN[:3])

    dpg.set_value("txt_stats",  f"{link.current_hz:.1f} Hz  │  {link.idle_ms} ms")
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
             {"safe": "WEAPON SAFE", "idle": "WEAPON IDLE", "attack": "WEAPON ATTACK"}[ws],
             {"safe": "panel",       "idle": "warn",        "attack": "attack"}[ws])
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

    p  = profiles.active
    dm = p.get("drive_mode", "tank")
    kb = p.get("keybinds", _DEFAULT_KEYBINDS)
    gp = p.get("gamepad", {})

    def _fmt(label, kb_pos, kb_neg=None, gp_key=None):
        k = (f"{key_display(kb.get(kb_pos))} / {key_display(kb.get(kb_neg))}"
             if kb_neg else key_display(kb.get(kb_pos, "")))
        g = gp_display(gp.get(gp_key)) if gp_key else ""
        return f"{label:<8}{k:<16}{g}"

    rows = (
        [_fmt("Fwd",   "fwd_pos",    "fwd_neg",   "fwd"),
         _fmt("Steer", "right_pos",  "right_neg", "steer")]
        if dm == "arcade" else
        [_fmt("L-Fwd", "fwd_pos",    "fwd_neg",   "fwd"),
         _fmt("R-Fwd", "right_pos",  "right_neg", "right")]
    ) + [
        _fmt("Weapon",  "weapon",       None, "weapon"),
        _fmt("W.Rev",   "weapon_rev",   None, "weapon_rev"),
        _fmt("Kill",    "killswitch",   None, "killswitch"),
        _fmt("Arm",     "arm",          None, "arm"),
        _fmt("Invert",  "drive_invert", None, "drive_invert"),
    ]
    dpg.set_value("txt_controls", "\n".join(rows))

    if dpg.is_item_shown("kb_win"):
        _refresh_kb_table(profiles)
        dpg.configure_item("kb_win", label="Keybinds — " + profiles.active["name"])

    vw = dpg.get_viewport_width()
    vh = dpg.get_viewport_height()
    dpg.set_item_width("primary", vw)
    dpg.set_item_height("primary", vh)


# ─── Entry point ─────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="HCR Mission Control")
    parser.add_argument("--calibrate", action="store_true",
                        help="Show gamepad axis/button numbers")
    args = parser.parse_args()

    if args.calibrate:
        calibrate()
        return

    cfg      = json.loads(CONFIG_PATH.read_text())
    profiles = ProfileManager()
    link     = SerialLink(cfg)

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

    mapper = InputMapper(profiles.active)
    _build_ui(cfg, profiles, link, mapper)

    if link.ensure_connected():
        _log_add(f"Serial connected: {link.port_name}")
    else:
        _log_add("Serial searching…")
    _log_add(f"Gamepad: {mapper.joystick_name}" if mapper.joystick_name
             else "No gamepad — keyboard only")
    _log_add(f"Profile: {profiles.active['name']}")

    rate_hz   = cfg["serial"]["rate_hz"]
    last_send = 0.0
    prev_inv = prev_arm = prev_wpn = False

    while dpg.is_dearpygui_running():
        now = time.time()

        for event in pygame.event.get():
            msg = mapper.handle_event(event)
            if msg:
                _log_add(msg)
            _handle_joy_capture(event, profiles, mapper)

        overlay = dpg.is_item_shown("kb_win")

        inv_raw  = mapper.read_button("drive_invert")
        kill_raw = mapper.read_button("killswitch")
        arm_raw  = mapper.read_button("arm")
        wpn_btn  = mapper.read_button("weapon")
        wpn_rev  = mapper.read_button("weapon_rev")
        fwd, right = mapper.read_drive()

        if not overlay:
            dm = profiles.active.get("drive_mode")
            if dm == "arcade":
                motor_l = int(max(0, min(255, 127 + (fwd + right) * 128)))
                motor_r = int(max(0, min(255, 127 + (fwd - right) * 128)))
            else:
                motor_l = int(max(0, min(255, 127 + fwd   * 128)))
                motor_r = int(max(0, min(255, 127 + right * 128)))

            motor_l = int(max(0, min(255, 127 + (motor_l - 127) * _mult["L"] + _trim["L"])))
            motor_r = int(max(0, min(255, 127 + (motor_r - 127) * _mult["R"] + _trim["R"])))

            if inv_raw and not prev_inv:
                _gs["drive_inverted"] = not _gs["drive_inverted"]
                _log_add(f"Drive invert {'ON' if _gs['drive_inverted'] else 'OFF'}")
            if _gs["drive_inverted"]:
                motor_l, motor_r = motor_r, motor_l

            if kill_raw and not _gs["killswitch"]:
                _gs["killswitch"] = True
                _log_add("KILLSWITCH — robot latched until power cycle")
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
                    _gs["weapon_state"] = "safe" if _gs["weapon_state"] != "safe" else "idle"
                elif _gs["weapon_state"] == "idle" and wpn_rev:
                    _gs["weapon_state"] = "attack"
                elif _gs["weapon_state"] == "attack" and not wpn_rev:
                    _gs["weapon_state"] = "idle"

            weapon_byte = {"safe": 127, "idle": 160, "attack": 255}[_gs["weapon_state"]]
        else:
            motor_l = motor_r = weapon_byte = 127

        failsafe_byte = 255 if (kill_raw or _gs["killswitch"]) else 0

        prev_inv = inv_raw
        prev_arm = arm_raw
        prev_wpn = wpn_btn

        if now - last_send >= 1.0 / rate_hz:
            pkt = _hex_packet(motor_l, motor_r, weapon_byte, failsafe_byte)
            was_searching = link.state == "searching"
            if link.ensure_connected():
                if was_searching:
                    _log_add(f"Serial connected: {link.port_name}")
                if link.send(pkt):
                    print(f"[TX] {pkt.strip().decode()}  "
                          f"motors=({motor_l},{motor_r}) "
                          f"weapon={weapon_byte} fs={failsafe_byte}")
                else:
                    _log_add("Serial write failed")
            last_send = now

        _update_ui(link, mapper, profiles,
                   motor_l if not overlay else 127,
                   motor_r if not overlay else 127)

        dpg.render_dearpygui_frame()

    dpg.destroy_context()
    pygame.quit()
    print("Ground station shut down.")


if __name__ == "__main__":
    main()
