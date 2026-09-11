"""Control bindings, defined in code (no runtime editor). Edit and restart.

Find axis/button numbers with `python station.py --calibrate`. SDL/Xbox axis
order: 0 left X, 1 left Y, 2 right X, 3 right Y, 4/5 triggers (rest -1, press +1).
"""
from __future__ import annotations

# Shared across modes: safety controls don't move when steering changes.
# Button indices measured with --calibrate on the team's Xbox pad (Windows
# XInput order): 1 = B, 4 = LB, 5 = RB, 6 = View.
_COMMON_BUTTONS: dict = {
    "weapon":       {"button": 5},   # RB
    "killswitch":   {"button": 1},   # B
    "arm":          {"button": 6},   # View
    "drive_invert": {"button": 4},   # LB
}

_COMMON_KEYS: dict = {
    "weapon":       "space",
    "weapon_rev":   "lshift",
    "killswitch":   "f",
    "arm":          "a",
    "drive_invert": "i",
}

# Right trigger doubles as weapon attack/reverse.
_TRIGGER_WEAPON: dict = {"weapon_rev": {"axis": 5, "threshold": 0.5}}

DEADZONE = 0.15
KB_RATE = 8          # motor bytes per frame while a key is held
EXPO = 0.0           # 0.0 linear, 1.0 fully cubic


TANK = {
    "name":    "Tank Drive",
    "mix":     "tank",
    "hint":    "L stick = left track, R stick = right track",
    "axis_a":  {"axis": 1, "invert": True,  "deadzone": DEADZONE},   # left Y
    "axis_b":  {"axis": 3, "invert": True,  "deadzone": DEADZONE},   # right Y
    "buttons": {**_COMMON_BUTTONS, **_TRIGGER_WEAPON},
    "keys":    {**_COMMON_KEYS,
                "a_pos": "w", "a_neg": "s",
                "b_pos": "up", "b_neg": "down"},
}

ARCADE = {
    "name":    "Arcade Drive",
    "mix":     "arcade",
    "hint":    "L stick = forward/back, R stick = steer left/right",
    "axis_a":  {"axis": 1, "invert": True,  "deadzone": DEADZONE},   # left Y
    "axis_b":  {"axis": 2, "invert": False, "deadzone": DEADZONE},   # right X
    "buttons": {**_COMMON_BUTTONS, **_TRIGGER_WEAPON},
    "keys":    {**_COMMON_KEYS,
                "a_pos": "w", "a_neg": "s",
                "b_pos": "right", "b_neg": "left"},
}

DRIVE_MODES: list[dict] = [TANK, ARCADE]
MODE_NAMES: list[str] = [m["name"] for m in DRIVE_MODES]


def by_name(name: str) -> dict:
    for m in DRIVE_MODES:
        if m["name"] == name:
            return m
    return TANK


def index_of(name: str) -> int:
    for i, m in enumerate(DRIVE_MODES):
        if m["name"] == name:
            return i
    return 0
