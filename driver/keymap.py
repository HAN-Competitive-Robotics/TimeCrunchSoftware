try:
    import pygame
except ImportError:
    import sys
    print("ERROR: pygame required. pip install pygame")
    sys.exit(1)

_KEY_NAME_OVERRIDES: dict = {}
_NAME_TO_KEY: dict = {}

def _init_key_maps():
    global _KEY_NAME_OVERRIDES, _NAME_TO_KEY
    pairs = [
        (pygame.K_LSHIFT,    "lshift"),
        (pygame.K_RSHIFT,    "rshift"),
        (pygame.K_LCTRL,     "lctrl"),
        (pygame.K_RCTRL,     "rctrl"),
        (pygame.K_LALT,      "lalt"),
        (pygame.K_RALT,      "ralt"),
        (pygame.K_SPACE,     "space"),
        (pygame.K_RETURN,    "return"),
        (pygame.K_ESCAPE,    "escape"),
        (pygame.K_TAB,       "tab"),
        (pygame.K_BACKSPACE, "backspace"),
        (pygame.K_DELETE,    "delete"),
        (pygame.K_UP,        "up"),
        (pygame.K_DOWN,      "down"),
        (pygame.K_LEFT,      "left"),
        (pygame.K_RIGHT,     "right"),
        (pygame.K_F2,        "f2"),
    ]
    _KEY_NAME_OVERRIDES = dict(pairs)
    _NAME_TO_KEY = {name: k for k, name in pairs}

_KEY_DISPLAY = {
    "lshift": "LShift", "rshift": "RShift",
    "lctrl":  "LCtrl",  "rctrl":  "RCtrl",
    "lalt":   "LAlt",   "ralt":   "RAlt",
    "space":  "Space",  "return": "Enter",
    "escape": "Esc",    "tab":    "Tab",
    "backspace": "Bksp","delete": "Del",
    "up": "Up", "down": "Down", "left": "Left", "right": "Right",
    "f2": "F2",
}

def key_to_name(k: int) -> str:
    return _KEY_NAME_OVERRIDES.get(k, pygame.key.name(k).lower())

def key_display(name: str) -> str:
    if not name:
        return "-"
    return _KEY_DISPLAY.get(name, name.upper() if len(name) == 1 else name.capitalize())

def gp_display(gp_cfg) -> str:
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

def resolve_key(name: str):
    if not name:
        return None
    lo = name.lower()
    k = _NAME_TO_KEY.get(lo)
    if k is not None:
        return k
    return getattr(pygame, f"K_{lo.upper()}", None)
