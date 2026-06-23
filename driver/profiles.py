from __future__ import annotations
import json
from pathlib import Path

PROFILES_PATH = Path(__file__).resolve().parent / "profiles.json"

# (id, label, is_axis, kb_pos_action, kb_neg_action, gp_config_key)
BINDABLE_ACTIONS: list[tuple] = [
    ("fwd",          "Forward",        True,  "fwd_pos",      "fwd_neg",  "fwd"),
    ("right",        "Right (tank)",   True,  "right_pos",    "right_neg","right"),
    ("steer",        "Steer (arcade)", True,  "right_pos",    "right_neg","steer"),
    ("weapon",       "Weapon Toggle",  False, "weapon",       None,       "weapon"),
    ("weapon_rev",   "Weapon Atk/Rev", False, "weapon_rev",   None,       "weapon_rev"),
    ("killswitch",   "Killswitch",     False, "killswitch",   None,       "killswitch"),
    ("arm",          "Arm Toggle",     False, "arm",          None,       "arm"),
    ("drive_invert", "Drive Invert",   False, "drive_invert", None,       "drive_invert"),
]

_DEFAULT_KEYBINDS: dict[str, str] = {
    "fwd_pos":      "w",
    "fwd_neg":      "s",
    "right_pos":    "up",
    "right_neg":    "down",
    "weapon":       "space",
    "weapon_rev":   "lshift",
    "killswitch":   "f",
    "arm":          "a",
    "drive_invert": "i",
}

_DEFAULT_GAMEPAD: dict = {
    "fwd":          {"axis": 1, "invert": True,  "deadzone": 0.15},
    "right":        {"axis": 3, "invert": True,  "deadzone": 0.15},
    "steer":        {"axis": 0, "invert": False, "deadzone": 0.15},
    "weapon":       {"button": 10},
    "weapon_rev":   {"axis": 5, "threshold": 0.5},
    "killswitch":   {"button": 1},
    "drive_invert": {"button": 9},
    "arm":          {"button": 6},
}


def _make_profile(name: str, drive_mode: str = "tank") -> dict:
    return {
        "name":       name,
        "drive_mode": drive_mode,
        "keybinds":   dict(_DEFAULT_KEYBINDS),
        "gamepad":    dict(_DEFAULT_GAMEPAD),
        "expo":       0.0,
        "kb_rate":    8,
    }


class ProfileManager:
    def __init__(self, path: Path = PROFILES_PATH):
        self.path       = path
        self.profiles:  list[dict] = []
        self.active_idx = 0
        self._load()

    def _load(self) -> None:
        if self.path.exists():
            try:
                data = json.loads(self.path.read_text())
                self.profiles = data.get("profiles", [])
                active_name   = data.get("active", "")
                for i, p in enumerate(self.profiles):
                    if p["name"] == active_name:
                        self.active_idx = i
                        break
                if self.profiles:
                    return
            except Exception:
                pass
        self._init_defaults()

    def _init_defaults(self) -> None:
        self.profiles   = [_make_profile("Tank Drive", "tank"),
                           _make_profile("Arcade Drive", "arcade")]
        self.active_idx = 0
        self.save()

    def save(self) -> None:
        self.path.write_text(json.dumps(
            {"active": self.active["name"], "profiles": self.profiles},
            indent=2,
        ))

    @property
    def active(self) -> dict:
        return self.profiles[self.active_idx]

    def select(self, idx: int) -> None:
        self.active_idx = idx % len(self.profiles)
        self.save()

    def new_named(self, name: str) -> None:
        name     = name.strip() or f"Profile {len(self.profiles) + 1}"
        existing = {p["name"] for p in self.profiles}
        base, n  = name, 1
        while name in existing:
            name = f"{base} {n}"
            n   += 1
        p = json.loads(json.dumps(self.active))
        p["name"] = name
        self.profiles.append(p)
        self.active_idx = len(self.profiles) - 1
        self.save()

    def delete(self, idx: int) -> bool:
        if len(self.profiles) <= 1:
            return False
        self.profiles.pop(idx)
        self.active_idx = min(self.active_idx, len(self.profiles) - 1)
        self.save()
        return True

    def toggle_drive_mode(self, idx: int | None = None) -> None:
        p = self.profiles[idx if idx is not None else self.active_idx]
        p["drive_mode"] = "arcade" if p["drive_mode"] == "tank" else "tank"
        self.save()

    def set_keybind(self, kb_action: str, key_name: str) -> None:
        self.active.setdefault("keybinds", {})[kb_action] = key_name
        self.save()

    def set_gamepad_bind(self, gp_key: str, gp_cfg: dict) -> None:
        self.active.setdefault("gamepad", {})[gp_key] = gp_cfg
        self.save()
