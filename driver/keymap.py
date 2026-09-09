"""Key-name (drive_modes.py) to DPG key-constant mapping.

Display strings are ASCII: DPG only loads basic Latin, so arrows render as "?".
"""
from __future__ import annotations
import dearpygui.dearpygui as dpg

_NAME_TO_DPG: dict[str, int] = {}
_DPG_TO_NAME: dict[int, str] = {}

_DISPLAY: dict[str, str] = {
    "lshift": "LShift", "rshift": "RShift",
    "lctrl":  "LCtrl",  "rctrl":  "RCtrl",
    "lalt":   "LAlt",   "ralt":   "RAlt",
    "space":  "Space",  "return": "Enter",
    "escape": "Esc",    "tab":    "Tab",
    "backspace": "Bksp","delete": "Del",
    "up": "Up", "down": "Down", "left": "Left", "right": "Right",
    **{f"f{i}": f"F{i}" for i in range(1, 13)},
}


def init_keymap() -> None:
    """Populate the name↔constant maps. Call once after dpg.create_context()."""
    global _NAME_TO_DPG, _DPG_TO_NAME
    pairs: list[tuple[str, int]] = []

    for c in "abcdefghijklmnopqrstuvwxyz":
        attr = f"mvKey_{c.upper()}"
        if hasattr(dpg, attr):
            pairs.append((c, getattr(dpg, attr)))

    for d in "0123456789":
        attr = f"mvKey_{d}"
        if hasattr(dpg, attr):
            pairs.append((d, getattr(dpg, attr)))

    specials = [
        ("space",     "mvKey_Spacebar"),
        ("return",    "mvKey_Return"),
        ("escape",    "mvKey_Escape"),
        ("tab",       "mvKey_Tab"),
        ("backspace", "mvKey_Back"),
        ("delete",    "mvKey_Delete"),
        ("up",        "mvKey_Up"),
        ("down",      "mvKey_Down"),
        ("left",      "mvKey_Left"),
        ("right",     "mvKey_Right"),
        ("lshift",    "mvKey_LShift"),
        ("rshift",    "mvKey_RShift"),
        ("lctrl",     "mvKey_LControl"),
        ("rctrl",     "mvKey_RControl"),
        ("lalt",      "mvKey_LAlt"),
        ("ralt",      "mvKey_RAlt"),
        *[(f"f{i}", f"mvKey_F{i}") for i in range(1, 13)],
    ]
    for name, attr in specials:
        if hasattr(dpg, attr):
            pairs.append((name, getattr(dpg, attr)))

    _NAME_TO_DPG = {name: key for name, key in pairs}
    _DPG_TO_NAME = {key: name for name, key in pairs}


def resolve_key(name: str | None) -> int | None:
    """Profile key name → DPG key constant, or None if unmapped."""
    if not name:
        return None
    return _NAME_TO_DPG.get(name.lower())


def key_display(name: str | None) -> str:
    if not name:
        return "-"
    return _DISPLAY.get(name, name.upper() if len(name) == 1 else name.capitalize())


def gp_display(gp_cfg: dict | None) -> str:
    if not gp_cfg:
        return "-"
    if "button" in gp_cfg:
        return f"B{gp_cfg['button']}"
    if "axis" in gp_cfg:
        n = gp_cfg["axis"]
        if "threshold" in gp_cfg:
            return f"Axis{n} trig"
        return f"Axis{n}{' inv' if gp_cfg.get('invert') else ''}"
    return "-"
