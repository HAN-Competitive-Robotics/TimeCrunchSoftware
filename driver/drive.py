"""Drive mixing: two normalised axes in, two motor bytes out.

Deliberately free of pygame and dearpygui so it can be tested directly.
Every function takes and returns plain numbers.

Axis convention: both inputs are -1.0 .. +1.0, positive meaning forward or
right. Outputs are 0..255 with 127 as stop, which is the wire format described
in docs/communication.md.
"""
from __future__ import annotations

CENTER = 127
SPAN = 128


def _clamp_unit(v: float) -> float:
    return max(-1.0, min(1.0, v))


def to_byte(v: float) -> int:
    """Normalised -1..+1 to a motor byte, saturating rather than wrapping."""
    return max(0, min(255, int(CENTER + _clamp_unit(v) * SPAN)))


def mix_tank(left_y: float, right_y: float) -> tuple[float, float]:
    """One stick per side. No mixing at all, which is what makes it easy to
    drive badly but impossible to misunderstand."""
    return _clamp_unit(left_y), _clamp_unit(right_y)


def mix_arcade(fwd: float, steer: float) -> tuple[float, float]:
    """One stick: Y drives both sides, X biases them apart."""
    return _clamp_unit(fwd + steer), _clamp_unit(fwd - steer)


def mix_rocket(throttle: float, steer: float) -> tuple[float, float]:
    """Triggers for throttle, stick X for steering.

    Unlike the game, steering is live at zero throttle so the robot can spin
    on the spot. A battlebot that cannot turn while stationary is a liability.
    """
    return _clamp_unit(throttle + steer), _clamp_unit(throttle - steer)


MIXERS = {
    "tank": mix_tank,
    "arcade": mix_arcade,
    "rocket": mix_rocket,
}


def mix(mode: str, a: float, b: float) -> tuple[float, float]:
    """Dispatch to a mixer by name. Unknown modes fall back to tank, because
    losing steering is safer than crashing the control loop mid-match."""
    return MIXERS.get(mode, mix_tank)(a, b)


def apply_trim(value: float, mult: float, trim_bytes: int) -> float:
    """Scale by the per-side multiplier, then offset by trim.

    trim_bytes is in motor-byte units, converted here so callers never have to
    hold both scales in their head at once.
    """
    return _clamp_unit(value * mult + trim_bytes / SPAN)


def drive_bytes(mode: str, a: float, b: float,
                mult_l: float = 1.0, mult_r: float = 1.0,
                trim_l: int = 0, trim_r: int = 0,
                invert: bool = False) -> tuple[int, int]:
    """Full path from raw axes to the two bytes that go on the wire.

    invert swaps the two sides, for driving while upside down. Forward is
    still forward when the robot is inverted; only left and right trade places.
    """
    left, right = mix(mode, a, b)
    left = apply_trim(left, mult_l, trim_l)
    right = apply_trim(right, mult_r, trim_r)
    lb, rb = to_byte(left), to_byte(right)
    return (rb, lb) if invert else (lb, rb)
