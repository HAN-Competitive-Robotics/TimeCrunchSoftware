"""Joystick (pygame) + keyboard (DPG) input, driven by a fixed drive mode.

Pygame is initialised with SDL_VIDEODRIVER=dummy so it never creates its own
window. The joystick subsystem works fine; DPG owns the window and handles the
keyboard via dpg.is_key_down().

Bindings come from driver/drive_modes.py and are not editable at runtime.
"""
from __future__ import annotations
import pygame
import dearpygui.dearpygui as dpg
from keymap import resolve_key
from drive_modes import EXPO, KB_RATE


class InputMapper:
    def __init__(self, mode: dict):
        self.mode = mode
        self.joystick: pygame.joystick.JoystickType | None = None
        self.joystick_name: str | None = None
        self._a_f = 0.0
        self._b_f = 0.0
        # While True the keyboard half of every binding is ignored (typing in
        # a text field must not drive the robot). Gamepad reads are unaffected.
        # The station sets this each frame from keyboard_captured().
        self.kb_blocked = False
        if pygame.joystick.get_count() > 0:
            self._attach(0)

    def set_mode(self, mode: dict) -> None:
        """Switching modes zeroes the keyboard ramps so a half-held axis from
        the previous mode cannot leak into the new one."""
        self.mode = mode
        self._a_f = 0.0
        self._b_f = 0.0

    # ── Joystick lifecycle ────────────────────────────────────────────────────

    def _attach(self, idx: int) -> None:
        try:
            js = pygame.joystick.Joystick(idx)
            js.init()
            self.joystick = js
            self.joystick_name = js.get_name()
        except pygame.error:
            self.joystick = None
            self.joystick_name = None

    def _detach(self) -> None:
        self.joystick = None
        self.joystick_name = None

    def handle_event(self, event) -> str | None:
        """Process a pygame event (joystick only). Returns a log line or None."""
        if event.type == pygame.JOYDEVICEADDED:
            self._attach(event.device_index)
            return f"Gamepad connected: {self.joystick_name}"
        if event.type == pygame.JOYDEVICEREMOVED:
            name = self.joystick_name or "?"
            self._detach()
            return f"Gamepad disconnected: {name}"
        return None

    # ── Raw gamepad reads ─────────────────────────────────────────────────────

    def _raw_axis(self, idx: int) -> float:
        try:
            return self.joystick.get_axis(idx)  # type: ignore[union-attr]
        except pygame.error:
            self._detach()
            return 0.0

    def _shaped_axis(self, cfg: dict) -> float:
        """Deadzone, inversion and expo applied to one stick axis."""
        raw = self._raw_axis(cfg["axis"])
        if cfg.get("invert", False):
            raw = -raw
        dz = cfg.get("deadzone", 0.15)
        if abs(raw) < dz:
            return 0.0
        sign = 1.0 if raw > 0 else -1.0
        raw = (abs(raw) - dz) / (1.0 - dz) * sign
        if EXPO:
            raw = raw * (1.0 - EXPO) + (raw ** 3) * EXPO
        return raw

    def _trigger_pair(self, cfg: dict) -> float:
        """Two triggers into one signed axis.

        Triggers rest at -1.0 and read +1.0 pressed, so each is rescaled to
        0..1 before subtracting. Pressing both cancels out, which is the same
        thing the game does.
        """
        pos = (self._raw_axis(cfg["trigger_pos"]) + 1.0) / 2.0
        neg = (self._raw_axis(cfg["trigger_neg"]) + 1.0) / 2.0
        return max(-1.0, min(1.0, pos - neg))

    def _gp_btn(self, cfg: dict) -> bool:
        try:
            if "button" in cfg:
                return bool(self.joystick.get_button(cfg["button"]))  # type: ignore[union-attr]
            if "axis" in cfg:
                return self._raw_axis(cfg["axis"]) > cfg.get("threshold", 0.5)
        except pygame.error:
            self._detach()
        return False

    # ── Keyboard ramps ────────────────────────────────────────────────────────

    def _kb_step(self, state: float, pos_k: int | None, neg_k: int | None,
                 rate: float) -> float:
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

    def _axis_value(self, cfg: dict, kb_pos: str, kb_neg: str,
                    ramp: float) -> tuple[float, float]:
        """Returns (value, new_ramp_state). Gamepad wins when one is attached."""
        if self.joystick is not None:
            if "trigger_pos" in cfg:
                return self._trigger_pair(cfg), ramp
            return self._shaped_axis(cfg), ramp
        keys = self.mode["keys"]
        # Blocked keys read as released, so a held ramp decays to zero
        # instead of freezing at its last value.
        ramp = self._kb_step(ramp,
                             None if self.kb_blocked else resolve_key(keys.get(kb_pos)),
                             None if self.kb_blocked else resolve_key(keys.get(kb_neg)),
                             KB_RATE / 127.0)
        return ramp, ramp

    # ── Public interface ──────────────────────────────────────────────────────

    def read_axes(self) -> tuple[float, float]:
        """The two normalised axes this mode's mixer expects.

        Tank: (left stick Y, right stick Y).
        Arcade: (throttle, steer). Rocket League: (trigger throttle, steer).
        """
        a, self._a_f = self._axis_value(self.mode["axis_a"], "a_pos", "a_neg", self._a_f)
        b, self._b_f = self._axis_value(self.mode["axis_b"], "b_pos", "b_neg", self._b_f)
        return a, b

    def read_button(self, action: str) -> bool:
        buttons = self.mode.get("buttons", {})
        if self.joystick is not None and action in buttons:
            if self._gp_btn(buttons[action]):
                return True
        if self.kb_blocked:
            return False
        k = resolve_key(self.mode.get("keys", {}).get(action, ""))
        return bool(k is not None and dpg.is_key_down(k))
