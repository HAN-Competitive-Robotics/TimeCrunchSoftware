try:
    import pygame
except ImportError:
    import sys
    print("ERROR: pygame required. pip install pygame")
    sys.exit(1)

from keymap import resolve_key


class InputMapper:
    def __init__(self, profile: dict):
        self.profile  = profile
        self.joystick = None
        self.joystick_name = None
        self._fwd_f   = 0.0
        self._right_f = 0.0
        pygame.joystick.init()
        if pygame.joystick.get_count() > 0:
            self._attach(0)

    def set_profile(self, profile: dict):
        self.profile  = profile
        self._fwd_f   = 0.0
        self._right_f = 0.0

    def _attach(self, idx: int):
        try:
            self.joystick = pygame.joystick.Joystick(idx)
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
        if event.type == pygame.JOYDEVICEREMOVED:
            name = self.joystick_name or "?"
            self._detach()
            return f"Gamepad disconnected: {name}"
        return None

    def _gp_axis(self, gp_cfg: dict) -> float:
        try:
            raw = self.joystick.get_axis(gp_cfg["axis"])
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
                return bool(self.joystick.get_button(gp_cfg["button"]))
            if "axis" in gp_cfg:
                return self.joystick.get_axis(gp_cfg["axis"]) > gp_cfg.get("threshold", 0.5)
        except pygame.error:
            self._detach()
        return False

    def _kb_step(self, state: float, pos_k, neg_k, keys, rate: float) -> float:
        if pos_k and keys[pos_k]:
            return min(state + rate, 1.0)
        if neg_k and keys[neg_k]:
            return max(state - rate, -1.0)
        if state > 0:
            return max(state - rate, 0.0)
        if state < 0:
            return min(state + rate, 0.0)
        return 0.0

    def read_drive(self, keys):
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
                keys, rate,
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
                keys, rate,
            )
            right = self._right_f

        return fwd, right

    def read_button(self, action: str, keys) -> bool:
        p  = self.profile
        gp = p.get("gamepad", {})
        kb = p.get("keybinds", {})
        if self.joystick and action in gp:
            if self._gp_btn(gp[action]):
                return True
        k = resolve_key(kb.get(action, ""))
        return bool(k and keys[k])
