"""Joystick (pygame) + keyboard (DPG) input mapper.

Pygame is initialised with SDL_VIDEODRIVER=dummy so it never creates its own
window. The joystick subsystem works fine; DPG owns the actual window and
handles keyboard via dpg.is_key_down().
"""
from __future__ import annotations
import pygame
import dearpygui.dearpygui as dpg
from keymap import resolve_key


class InputMapper:
    def __init__(self, profile: dict):
        self.profile = profile
        self.joystick: pygame.joystick.JoystickType | None = None
        self.joystick_name: str | None = None
        self._fwd_f   = 0.0
        self._right_f = 0.0
        if pygame.joystick.get_count() > 0:
            self._attach(0)

    def set_profile(self, profile: dict) -> None:
        self.profile  = profile
        self._fwd_f   = 0.0
        self._right_f = 0.0

    # ── Joystick lifecycle ────────────────────────────────────────────────────

    def _attach(self, idx: int) -> None:
        try:
            js = pygame.joystick.Joystick(idx)
            js.init()
            self.joystick      = js
            self.joystick_name = js.get_name()
        except pygame.error:
            self.joystick      = None
            self.joystick_name = None

    def _detach(self) -> None:
        self.joystick      = None
        self.joystick_name = None

    def handle_event(self, event) -> str | None:
        """Process a pygame event (joystick only). Returns a log string or None."""
        if event.type == pygame.JOYDEVICEADDED:
            self._attach(event.device_index)
            return f"Gamepad connected: {self.joystick_name}"
        if event.type == pygame.JOYDEVICEREMOVED:
            name = self.joystick_name or "?"
            self._detach()
            return f"Gamepad disconnected: {name}"
        return None

    # ── Gamepad axis / button ─────────────────────────────────────────────────

    def _gp_axis(self, gp_cfg: dict) -> float:
        try:
            raw = self.joystick.get_axis(gp_cfg["axis"])  # type: ignore[union-attr]
        except pygame.error:
            self._detach()
            return 0.0
        if gp_cfg.get("invert", False):
            raw = -raw
        dz = gp_cfg.get("deadzone", 0.15)
        if abs(raw) < dz:
            return 0.0
        sign = 1.0 if raw > 0 else -1.0
        raw  = (abs(raw) - dz) / (1.0 - dz) * sign
        expo = self.profile.get("expo", 0.0)
        if expo:
            raw = raw * (1.0 - expo) + (raw ** 3) * expo
        return raw

    def _gp_btn(self, gp_cfg: dict) -> bool:
        try:
            if "button" in gp_cfg:
                return bool(self.joystick.get_button(gp_cfg["button"]))  # type: ignore[union-attr]
            if "axis" in gp_cfg:
                return self.joystick.get_axis(gp_cfg["axis"]) > gp_cfg.get("threshold", 0.5)  # type: ignore[union-attr]
        except pygame.error:
            self._detach()
        return False

    # ── Keyboard (DPG) ────────────────────────────────────────────────────────

    def _kb_step(self, state: float, pos_k: int | None, neg_k: int | None, rate: float) -> float:
        pos = pos_k is not None and dpg.is_key_down(pos_k)
        neg = neg_k is not None and dpg.is_key_down(neg_k)
        if pos:
            return min(state + rate, 1.0)
        if neg:
            return max(state - rate, -1.0)
        if state > 0:
            return max(state - rate, 0.0)
        if state < 0:
            return min(state + rate, 0.0)
        return 0.0

    # ── Public read interface ─────────────────────────────────────────────────

    def read_drive(self) -> tuple[float, float]:
        p    = self.profile
        gp   = p.get("gamepad", {})
        kb   = p.get("keybinds", {})
        rate = p.get("kb_rate", 8) / 127.0

        if self.joystick and "fwd" in gp:
            fwd = self._gp_axis(gp["fwd"])
        else:
            self._fwd_f = self._kb_step(
                self._fwd_f,
                resolve_key(kb.get("fwd_pos")),
                resolve_key(kb.get("fwd_neg")),
                rate,
            )
            fwd = self._fwd_f

        if self.joystick:
            gp_key = "steer" if p.get("drive_mode") == "arcade" else "right"
            right  = self._gp_axis(gp[gp_key]) if gp_key in gp else 0.0
        else:
            self._right_f = self._kb_step(
                self._right_f,
                resolve_key(kb.get("right_pos")),
                resolve_key(kb.get("right_neg")),
                rate,
            )
            right = self._right_f

        return fwd, right

    def read_button(self, action: str) -> bool:
        p  = self.profile
        gp = p.get("gamepad", {})
        kb = p.get("keybinds", {})
        if self.joystick and action in gp:
            if self._gp_btn(gp[action]):
                return True
        k = resolve_key(kb.get(action, ""))
        return bool(k is not None and dpg.is_key_down(k))
