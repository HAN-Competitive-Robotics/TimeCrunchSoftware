try:
    import pygame
except ImportError:
    import sys
    print("ERROR: pygame required. pip install pygame")
    sys.exit(1)

import time
from collections import deque

from profiles import BINDABLE_ACTIONS, _DEFAULT_KEYBINDS
from keymap import key_display, gp_display


SCREEN_MAIN     = "main"
SCREEN_KEYBINDS = "keybinds"


class DropdownWidget:
    """Simple profile selector — names only."""

    _ITEM_H = 34

    def __init__(self):
        self.x = self.y = self.w = self.h = 0
        self.open = False
        self._item_rects = []

    def set_rect(self, x, y, w, h):
        self.x, self.y, self.w, self.h = x, y, w, h

    def draw(self, surface, profiles, font, theme: dict):
        c = theme
        btn = pygame.Rect(self.x, self.y, self.w, self.h)

        # Main button
        pygame.draw.rect(surface, c.get("panel", (45, 45, 55)), btn, border_radius=4)
        border_c = c.get("accent", (0, 200, 255)) if self.open else c.get("panel", (45, 45, 55))
        pygame.draw.rect(surface, border_c, btn, 1, border_radius=4)
        lbl = f"  {profiles.active['name']}  ▾"
        s = font.render(lbl, True, c.get("text", (220, 220, 220)))
        surface.blit(s, (btn.x + 4, btn.y + (btn.h - s.get_height()) // 2))

        if not self.open:
            self._item_rects = []
            return

        # Dropdown panel
        n = len(profiles.profiles)
        panel_h = n * (self._ITEM_H + 2) + 6
        panel = pygame.Rect(self.x, self.y + self.h + 2, self.w, panel_h)
        pygame.draw.rect(surface, c.get("bg", (30, 30, 35)), panel, border_radius=6)
        pygame.draw.rect(surface, c.get("accent", (0, 200, 255)), panel, 1, border_radius=6)

        self._item_rects = []
        iy = panel.y + 3
        for i, p in enumerate(profiles.profiles):
            active = (i == profiles.active_idx)
            row_bg = c.get("accent", (0, 200, 255)) if active else c.get("panel", (45, 45, 55))
            row_r = pygame.Rect(panel.x + 3, iy, self.w - 6, self._ITEM_H)
            pygame.draw.rect(surface, row_bg, row_r, border_radius=4)

            ns = font.render(f"  {p['name']}", True, c.get("text", (220, 220, 220)))
            surface.blit(ns, (row_r.x + 4, iy + (self._ITEM_H - ns.get_height()) // 2))

            self._item_rects.append(row_r)
            iy += self._ITEM_H + 2

    def handle_click(self, pos):
        btn = pygame.Rect(self.x, self.y, self.w, self.h)
        if btn.collidepoint(pos):
            self.open = not self.open
            return None
        if not self.open:
            return None
        for i, rect in enumerate(self._item_rects):
            if rect.collidepoint(pos):
                self.open = False
                return ("select", i)
        self.open = False
        return None


class GUI:
    def __init__(self, cfg: dict):
        pygame.display.set_caption("HCR Mission Control")
        self.screen = pygame.display.set_mode(
            (cfg["ui"]["width"], cfg["ui"]["height"]), pygame.RESIZABLE
        )
        self.clock      = pygame.time.Clock()
        self.font       = pygame.font.SysFont("monospace", 16)
        self.font_big   = pygame.font.SysFont("monospace", 24)
        self.font_small = pygame.font.SysFont("monospace", 12)
        self.theme      = cfg["ui"]["theme"]
        self.log        = deque(maxlen=6)

        self.current_screen = SCREEN_MAIN

        # Dropdown widget
        self.dropdown   = DropdownWidget()

        # Keybind editor state
        self.keybind_cursor = 0
        self.keybind_col    = 0   # 0 = KB, 1 = GP
        self.capturing      = False
        self.capture_row    = 0
        self.capture_col    = 0
        self.capture_step   = 0   # KB axis: 0=pos, 1=neg

        # Clickable rects set during draw
        self._keybind_row_rects = []  # [(kb_rect, gp_rect)]
        self.keybinds_btn       = None
        self.drive_btn          = None
        self.new_btn            = None
        self.del_btn            = None

    def _c(self, name):
        return self.theme.get(name, [255, 255, 255])

    def _txt(self, text, color, pos, big=False, small=False):
        f = self.font_big if big else (self.font_small if small else self.font)
        c = color if isinstance(color, (list, tuple)) else self._c(color)
        self.screen.blit(f.render(str(text), True, c), pos)

    def _rect(self, color, rect, width=0):
        c = color if isinstance(color, (list, tuple)) else self._c(color)
        pygame.draw.rect(self.screen, c, rect, width, border_radius=4)

    def _hline(self, y, color="panel"):
        sw = self.screen.get_width()
        lm = int(0.025 * sw)
        pygame.draw.line(self.screen, self._c(color), (lm, y), (sw - lm, y), 1)

    def _ind(self, color, rect, text):
        self._rect(color, rect)
        x, y, w, h = rect
        surf = self.font.render(text, True, self._c("text"))
        tw, th = surf.get_size()
        self.screen.blit(surf, (x + (w - tw) // 2, y + (h - th) // 2))

    def _vbar(self, x, y, w, h, value, center, rmin, rmax, label):
        self._rect("panel", (x, y, w, h))
        cy = int(y + h * (rmax - center) / (rmax - rmin))
        pygame.draw.line(self.screen, self._c("text"), (x, cy), (x + w, cy), 2)
        if value != center:
            vy = int(y + h * (rmax - value) / (rmax - rmin))
            fy, fh = (vy, cy - vy) if value > center else (cy, vy - cy)
            pygame.draw.rect(self.screen, self._c("accent"),
                             (x + 4, fy, w - 8, max(2, fh)), border_radius=2)
        hsurf = self.font_small.render(f"{label}: {value}", True, self._c("text"))
        self.screen.blit(hsurf, (x + (w - hsurf.get_width()) // 2, y - 15))

    def add_log(self, msg: str):
        self.log.append(f"[{time.strftime('%H:%M:%S')}] {msg}")

    @property
    def overlay_active(self) -> bool:
        return self.dropdown.open

    # ── Main screen ───────────────────────────────────────────────────────────

    def draw_main(self, link, mapper, profiles, motor_l, motor_r,
                  drive_inverted, armed, weapon_state, killswitch_on, runtime_ms):
        sw, sh = self.screen.get_size()
        self.screen.fill(self._c("bg"))
        lm = int(0.025 * sw)
        dm = profiles.active.get("drive_mode", "tank").upper()

        # ── Header ────────────────────────────────────────────────────────────
        hdr_h = max(32, int(0.07 * sh))

        # Title
        self._txt("HCR MISSION CONTROL", "accent", (lm, (hdr_h - 24) // 2), big=True)

        # Right-side header buttons: [Drive] [Keybinds] [Dropdown▾] [+]
        btn_h  = max(26, int(0.055 * sh))
        btn_y  = (hdr_h - btn_h) // 2
        dd_w   = min(240, max(160, int(0.26 * sw)))
        new_w  = max(28, btn_h)
        kb_w   = max(90,  int(0.12 * sw))
        dr_w   = max(90,  int(0.12 * sw))
        gap    = max(4, int(0.006 * sw))

        new_x = sw - lm - new_w
        dd_x  = new_x - gap - dd_w
        kb_x  = dd_x - gap - kb_w
        dr_x  = kb_x - gap - dr_w

        self.dropdown.set_rect(dd_x, btn_y, dd_w, btn_h)

        self.new_btn = pygame.Rect(new_x, btn_y, new_w, btn_h)
        self._ind("panel", self.new_btn, "+")
        pygame.draw.rect(self.screen, self._c("accent"), self.new_btn, 1, border_radius=4)

        self.keybinds_btn = pygame.Rect(kb_x, btn_y, kb_w, btn_h)
        self._ind("panel", self.keybinds_btn, "F2: Keybinds")
        pygame.draw.rect(self.screen, self._c("accent"), self.keybinds_btn, 1, border_radius=4)

        self.drive_btn = pygame.Rect(dr_x, btn_y, dr_w, btn_h)
        self._ind("panel", self.drive_btn, f"T: {dm}")
        pygame.draw.rect(self.screen, self._c("warning"), self.drive_btn, 1, border_radius=4)

        # ── Status row ────────────────────────────────────────────────────────
        sy = hdr_h + 4
        if link.state == "connected":
            self._txt(f"SERIAL OK  ({link.port_name})", "good", (lm, sy))
        elif link.state == "searching":
            self._txt("SERIAL SEARCHING...", "warning", (lm, sy))
        else:
            self._txt("SERIAL LOST", "danger", (lm, sy))

        if mapper.joystick_name:
            self._txt(f"GAMEPAD: {mapper.joystick_name}", "good", (sw // 2, sy))
        else:
            self._txt("KEYBOARD ONLY", "warning", (sw // 2, sy))

        sep1 = sy + max(18, int(0.04 * sh))
        self._hline(sep1)

        # ── Motor bars ────────────────────────────────────────────────────────
        bw  = max(40, int(0.08 * sw))
        bh  = max(80, int(0.22 * sh))
        bgp = max(12, int(0.025 * sw))
        bx1 = int(0.10 * sw)
        bx2 = bx1 + bw + bgp
        by  = sep1 + max(14, int(0.03 * sh))
        self._vbar(bx1, by, bw, bh, motor_l, 127, 0, 255, "LEFT")
        self._vbar(bx2, by, bw, bh, motor_r, 127, 0, 255, "RIGHT")

        # ── Status indicators ─────────────────────────────────────────────────
        px  = int(0.525 * sw)
        iw  = int(0.21 * sw)
        ix2 = int(0.755 * sw)
        ih  = max(26, int(0.055 * sh))
        gap2 = max(8, int(0.018 * sh))
        iy1 = by
        iy2 = iy1 + ih + gap2
        iy3 = iy2 + ih + gap2

        self._ind("warning" if drive_inverted else "panel",
                  (px, iy1, iw, ih),
                  "DRIVE INVERTED" if drive_inverted else "DRIVE NORMAL")
        w_col = {"safe": "panel", "idle": "warning", "attack": "danger"}[weapon_state]
        w_lbl = {"safe": "WEAPON SAFE", "idle": "WEAPON IDLE", "attack": "WEAPON ATTACK"}[weapon_state]
        self._ind(w_col, (ix2, iy1, iw, ih), w_lbl)
        self._ind("good" if armed else "danger",
                  (px, iy2, iw, ih), "ARMED" if armed else "DISARMED")
        self._ind("danger" if killswitch_on else "panel",
                  (ix2, iy2, iw, ih),
                  "KILLSWITCH!" if killswitch_on else "KILLSWITCH OFF")

        # ── Stats ─────────────────────────────────────────────────────────────
        stats_y = max(by + bh + gap2, iy3 + gap2)
        hz = link.current_hz
        self._txt(f"Pkts: {link.packet_count}  |  {hz:.1f} Hz  |  Idle: {link.idle_ms} ms",
                  "text", (lm, stats_y), small=True)

        # ── Log + controls ────────────────────────────────────────────────────
        sep2  = stats_y + max(16, int(0.04 * sh))
        mid_x = sw // 2
        self._hline(sep2)
        pygame.draw.line(self.screen, self._c("panel"), (mid_x, sep2), (mid_x, sh - lm), 1)
        ty  = sep2 + max(6, int(0.018 * sh))
        lh  = max(13, int(0.034 * sh))
        cx2 = mid_x + lm
        kb  = profiles.active.get("keybinds", _DEFAULT_KEYBINDS)

        self._txt("EVENT LOG", "accent", (lm, ty))
        self.screen.set_clip(pygame.Rect(lm, ty + lh, mid_x - lm * 2, sh - ty - lh))
        ely = ty + lh
        for entry in self.log:
            self._txt(entry, "text", (lm, ely), small=True)
            ely += lh
        self.screen.set_clip(None)

        self._txt("CONTROLS", "accent", (cx2, ty))
        if dm == "ARCADE":
            lines = [
                f"Fwd:    {key_display(kb.get('fwd_pos'))} / {key_display(kb.get('fwd_neg'))}",
                f"Steer:  {key_display(kb.get('right_pos'))} / {key_display(kb.get('right_neg'))}",
            ]
        else:
            lines = [
                f"L-Fwd:  {key_display(kb.get('fwd_pos'))} / {key_display(kb.get('fwd_neg'))}",
                f"R-Fwd:  {key_display(kb.get('right_pos'))} / {key_display(kb.get('right_neg'))}",
            ]
        lines += [
            f"Weapon: {key_display(kb.get('weapon'))}  (toggle idle)",
            f"W.Rev:  {key_display(kb.get('weapon_rev'))}  (hold = attack)",
            f"Kill:   {key_display(kb.get('killswitch'))}",
            f"Arm:    {key_display(kb.get('arm'))}",
            f"Invert: {key_display(kb.get('drive_invert'))}",
        ]
        cly = ty + lh
        for line in lines:
            self._txt(line, "text", (cx2, cly), small=True)
            cly += lh

        # Draw dropdown on top of everything (it may overlap)
        self.dropdown.draw(self.screen, profiles, self.font, self.theme)

        pygame.display.flip()

    # ── Keybind screen ────────────────────────────────────────────────────────

    def draw_keybinds(self, profiles):
        sw, sh = self.screen.get_size()
        self.screen.fill(self._c("bg"))
        lm = int(0.025 * sw)
        profile = profiles.active

        self._txt(f"KEYBINDS  —  {profile['name']}", "accent", (lm, int(0.02 * sh)), big=True)
        self._txt("Click a cell to select   Enter / click again to rebind   F2 / ESC: back",
                  "text", (lm, int(0.09 * sh)), small=True)

        col_kb  = int(0.45 * sw)
        col_gp  = int(0.68 * sw)
        hdr_y   = int(0.14 * sh)
        self._hline(hdr_y)
        self._txt("Action",   "accent", (lm + 8,      hdr_y + 4), small=True)
        self._txt("Keyboard", "accent", (col_kb + 4,  hdr_y + 4), small=True)
        self._txt("Gamepad",  "accent", (col_gp + 4,  hdr_y + 4), small=True)
        pygame.draw.line(self.screen, self._c("panel"), (col_kb, hdr_y), (col_kb, sh - lm), 1)
        pygame.draw.line(self.screen, self._c("panel"), (col_gp, hdr_y), (col_gp, sh - lm), 1)

        row_h   = max(26, int(0.058 * sh))
        start_y = hdr_y + row_h + 2
        kb_dict = profile.get("keybinds", {})
        gp_dict = profile.get("gamepad", {})
        self._keybind_row_rects = []

        for i, (action_id, label, is_axis, kb_pos, kb_neg, gp_key) in enumerate(BINDABLE_ACTIONS):
            ry      = start_y + i * (row_h + 3)
            row_bg  = pygame.Rect(lm, ry, sw - lm * 2, row_h)
            kb_rect = pygame.Rect(col_kb, ry, col_gp - col_kb, row_h)
            gp_rect = pygame.Rect(col_gp, ry, sw - lm - col_gp, row_h)
            self._keybind_row_rects.append((kb_rect, gp_rect))

            sel_row = (i == self.keybind_cursor)
            self._rect("panel" if sel_row else "bg", row_bg)

            if sel_row and self.keybind_col == 0:
                pygame.draw.rect(self.screen, self._c("accent"), kb_rect, 2, border_radius=2)
            elif sel_row and self.keybind_col == 1:
                pygame.draw.rect(self.screen, self._c("accent"), gp_rect, 2, border_radius=2)

            marker = "> " if sel_row else "  "
            self._txt(f"  {marker}{label}", "text", (lm + 8, ry + (row_h - 16) // 2))

            # KB cell
            cap_kb = self.capturing and self.capture_row == i and self.capture_col == 0
            if cap_kb:
                prompt = ("PRESS + KEY..." if self.capture_step == 0 else "PRESS - KEY...") if is_axis else "PRESS KEY..."
                self._txt(prompt, "warning", (col_kb + 6, ry + (row_h - 16) // 2))
            else:
                if is_axis:
                    kb_text = f"{key_display(kb_dict.get(kb_pos))} / {key_display(kb_dict.get(kb_neg))}"
                else:
                    kb_text = key_display(kb_dict.get(kb_pos, ""))
                self._txt(kb_text, "text", (col_kb + 6, ry + (row_h - 16) // 2))

            # GP cell
            cap_gp = self.capturing and self.capture_row == i and self.capture_col == 1
            if cap_gp:
                self._txt("MOVE STICK / PRESS BTN...", "warning", (col_gp + 6, ry + (row_h - 16) // 2))
            else:
                self._txt(gp_display(gp_dict.get(gp_key)), "good",
                           (col_gp + 6, ry + (row_h - 16) // 2))

        # Delete profile button
        del_w = 120
        del_h = 28
        del_x = sw - lm - del_w
        del_y = sh - lm - del_h
        self.del_btn = pygame.Rect(del_x, del_y, del_w, del_h)
        can_del = len(profiles.profiles) > 1
        self._ind("danger" if can_del else "panel", self.del_btn, "Delete Profile")
        if can_del:
            pygame.draw.rect(self.screen, self._c("danger"), self.del_btn, 1, border_radius=4)

        pygame.display.flip()

    # ── Dispatch ───────────────────────────────────────────────────────────────

    def draw(self, link, mapper, profiles, motor_l, motor_r,
             drive_inverted, armed, weapon_state, killswitch_on, runtime_ms):
        if self.current_screen == SCREEN_KEYBINDS:
            self.draw_keybinds(profiles)
        else:
            self.draw_main(link, mapper, profiles, motor_l, motor_r,
                           drive_inverted, armed, weapon_state, killswitch_on, runtime_ms)

    # ── Mouse ─────────────────────────────────────────────────────────────────

    def handle_click(self, pos, profiles, mapper, gs: dict):
        if self.current_screen == SCREEN_KEYBINDS:
            self._click_keybinds(pos, profiles, mapper, gs)
            return

        action = self.dropdown.handle_click(pos)
        if action is not None:
            if action[0] == "select":
                profiles.select(action[1])
                mapper.set_profile(profiles.active)
                gs["drive_inverted"] = False
                gs["weapon_state"]   = "safe"
                self.add_log(f"Profile: {profiles.active['name']}")
            return

        if self.new_btn and self.new_btn.collidepoint(pos):
            profiles.new_named("")
            mapper.set_profile(profiles.active)
            gs["drive_inverted"] = False
            gs["weapon_state"]   = "safe"
            self.add_log(f"Created: {profiles.active['name']}")
            return

        if self.keybinds_btn and self.keybinds_btn.collidepoint(pos):
            self.current_screen = SCREEN_KEYBINDS
            self.keybind_cursor = 0
            self.keybind_col    = 0
        elif self.drive_btn and self.drive_btn.collidepoint(pos):
            profiles.toggle_drive_mode()
            mapper.set_profile(profiles.active)
            gs["drive_inverted"] = False
            self.add_log(f"Drive mode: {profiles.active['drive_mode'].upper()}")

    def _click_keybinds(self, pos, profiles, mapper, gs):
        if self.capturing:
            return
        if self.del_btn and self.del_btn.collidepoint(pos):
            name = profiles.active["name"]
            if profiles.delete(profiles.active_idx):
                mapper.set_profile(profiles.active)
                gs["drive_inverted"] = False
                gs["weapon_state"]   = "safe"
                self.add_log(f"Deleted '{name}'. Now: {profiles.active['name']}")
                self.current_screen = SCREEN_MAIN
            else:
                self.add_log("Can't delete the last profile")
            return
        for i, (kb_rect, gp_rect) in enumerate(self._keybind_row_rects):
            if kb_rect.collidepoint(pos):
                if self.keybind_cursor == i and self.keybind_col == 0:
                    self._start_capture(i, 0)
                else:
                    self.keybind_cursor = i
                    self.keybind_col    = 0
                return
            if gp_rect.collidepoint(pos):
                if self.keybind_cursor == i and self.keybind_col == 1:
                    self._start_capture(i, 1)
                else:
                    self.keybind_cursor = i
                    self.keybind_col    = 1
                return

    def _start_capture(self, row: int, col: int):
        self.capturing    = True
        self.capture_row  = row
        self.capture_col  = col
        self.capture_step = 0
