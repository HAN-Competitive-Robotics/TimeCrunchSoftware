"""Control bindings, defined in code on purpose.

There is no runtime keybind editor. To change a binding, edit this file and
restart. That trade is deliberate: a rebindable UI meant every machine drifted
to a different layout, and nobody could answer "what does B6 do on this robot"
without opening someone's profiles.json.

Finding numbers: run `python station.py --calibrate`, move every stick and
press every button, and it prints the axis and button indices for your pad.

Axis indices below follow SDL's game-controller order, which is what pygame
reports for an Xbox pad:

    0 = left X    1 = left Y    2 = right X
    3 = right Y   4 = left trigger  5 = right trigger

Triggers rest at -1.0 and read +1.0 fully pressed.
"""
from __future__ import annotations

# Shared across every mode. Weapon and safety controls should not move when
# you change how the robot steers.
_COMMON_BUTTONS: dict = {
    "weapon":       {"button": 10},
    "killswitch":   {"button": 1},
    "arm":          {"button": 6},
    "drive_invert": {"button": 9},
}

_COMMON_KEYS: dict = {
    "weapon":       "space",
    "weapon_rev":   "lshift",
    "killswitch":   "f",
    "arm":          "a",
    "drive_invert": "i",
}

# Right trigger doubles as weapon attack in the stick-driven modes. Rocket
# League mode needs both triggers for throttle, so it cannot share that.
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
    "hint":    "L stick Y = throttle, L stick X = steer",
    "axis_a":  {"axis": 1, "invert": True,  "deadzone": DEADZONE},   # left Y
    "axis_b":  {"axis": 0, "invert": False, "deadzone": DEADZONE},   # left X
    "buttons": {**_COMMON_BUTTONS, **_TRIGGER_WEAPON},
    "keys":    {**_COMMON_KEYS,
                "a_pos": "w", "a_neg": "s",
                "b_pos": "right", "b_neg": "left"},
}

ROCKET_LEAGUE = {
    "name":    "Rocket League",
    "mix":     "rocket",
    "hint":    "RT = forward, LT = reverse, L stick X = steer",
    # axis_a is synthesised from the two triggers, not read directly.
    "axis_a":  {"trigger_pos": 5, "trigger_neg": 4},
    "axis_b":  {"axis": 0, "invert": False, "deadzone": DEADZONE},   # left X
    # No _TRIGGER_WEAPON here: the triggers are the throttle. Weapon attack is
    # keyboard-only on the pad until you pick a free button for it, which you
    # can find with --calibrate.
    "buttons": dict(_COMMON_BUTTONS),
    "keys":    {**_COMMON_KEYS,
                "a_pos": "w", "a_neg": "s",
                "b_pos": "right", "b_neg": "left"},
}

DRIVE_MODES: list[dict] = [TANK, ARCADE, ROCKET_LEAGUE]
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
