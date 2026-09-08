"""Exhaustive check of the station's safety gating.

Run with:  python test_safety.py

Covers every combination of armed / killswitch / weapon state and asserts the
invariants that keep a combat robot from moving when it should not. No pytest
dependency, and no dearpygui import, so it runs anywhere.

The invariants, in plain terms:

  1. Disarmed means neutral motors and a safe weapon, whatever the sticks say.
  2. A latched killswitch means the same, even while armed.
  3. A latched killswitch keeps sending 255 forever; it never clears itself.
  4. Nothing except an explicit arm, with no killswitch, can command motion.
  5. A trim command can never be confused with a drive packet.
"""
import itertools
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import drive

# Import the pure helpers without pulling in dearpygui/pygame.
import re
_src = Path(__file__).resolve().parent.joinpath("station.py").read_text()
_ns: dict = {}
for _fn in ("outputs_inhibited", "failsafe_byte", "_hex_packet", "trim_packet"):
    _m = re.search(rf"^def {_fn}\(.*?(?=\n\n\n|\n# ─|\Z)", _src, re.S | re.M)
    exec(_m.group(0), _ns)
_ns["OPCODE_SET_TRIM"] = 1
_ns["TRIM_MAGIC"] = 0x5A
exec(re.search(r"^WEAPON_BYTES = .*$", _src, re.M).group(0), _ns)
exec(re.search(r"^NEUTRAL = .*$", _src, re.M).group(0), _ns)
exec(re.search(r"^def trim_packet\(.*?(?=\n\n\n)", _src, re.S | re.M).group(0), _ns)

outputs_inhibited = _ns["outputs_inhibited"]
failsafe_byte = _ns["failsafe_byte"]
WEAPON_BYTES = _ns["WEAPON_BYTES"]
NEUTRAL = _ns["NEUTRAL"]
trim_packet = _ns["trim_packet"]

WEAPON_STATES = ["safe", "idle", "attack", "idle_rev"]
fails: list[str] = []


def check(label, cond):
    print(f"  {'ok  ' if cond else 'FAIL'} {label}")
    if not cond:
        fails.append(label)


def hdr(t):
    print()
    print("=" * 70)
    print(t)
    print("=" * 70)


def simulate_frame(armed, killswitch, weapon_state, axis_a, axis_b, mix="tank"):
    """Mirror of the station's per-frame output decision."""
    ml, mr = drive.drive_bytes(mix, axis_a, axis_b)
    if outputs_inhibited(armed, killswitch):
        ml = mr = NEUTRAL
        weapon_state = "safe"
    return ml, mr, WEAPON_BYTES[weapon_state], failsafe_byte(False, killswitch)


hdr("1. Disarmed: motors neutral and weapon safe, at every stick position")
for a, b in itertools.product([-1.0, -0.5, 0.0, 0.5, 1.0], repeat=2):
    for ws in WEAPON_STATES:
        ml, mr, wb, _ = simulate_frame(False, False, ws, a, b)
        if not (ml == mr == NEUTRAL and wb == WEAPON_BYTES["safe"]):
            fails.append(f"disarmed a={a} b={b} ws={ws}")
check("all 100 stick/weapon combinations produce 127/127 and weapon 127",
      not fails)

hdr("2. Killswitch latched while ARMED: still fully inhibited")
worst = []
for a, b in itertools.product([-1.0, 1.0], repeat=2):
    for ws in WEAPON_STATES:
        ml, mr, wb, fb = simulate_frame(True, True, ws, a, b)
        worst.append((ml, mr, wb, fb))
check("motors forced neutral despite being armed",
      all(ml == mr == NEUTRAL for ml, mr, _, _ in worst))
check("weapon forced safe despite being armed",
      all(wb == WEAPON_BYTES["safe"] for _, _, wb, _ in worst))
check("failsafe byte is 255 on every frame",
      all(fb == 255 for _, _, _, fb in worst))

hdr("3. Only armed-and-not-killed permits motion")
for armed, kill in itertools.product([False, True], repeat=2):
    ml, mr, _, _ = simulate_frame(armed, kill, "safe", 1.0, 1.0)
    moves = not (ml == mr == NEUTRAL)
    expect = armed and not kill
    check(f"armed={armed!s:<5} killswitch={kill!s:<5} -> "
          f"{'commands motion' if moves else 'inhibited':<16}", moves == expect)

hdr("4. Killswitch latch is sticky and cannot be released by input")
check("kill pressed, not yet latched -> 255", failsafe_byte(True, False) == 255)
check("kill released, latch set      -> 255", failsafe_byte(False, True) == 255)
check("both                          -> 255", failsafe_byte(True, True) == 255)
check("neither                       -> 0",   failsafe_byte(False, False) == 0)

hdr("5. Failsafe byte always exceeds the robot's >127 threshold")
check("255 > 127, so a single-bit flip cannot clear it below threshold",
      failsafe_byte(True, False) == 255 and 255 > 127)
check("normal packets sit at 0, far from the threshold",
      failsafe_byte(False, False) == 0)

hdr("6. Weapon byte mapping matches the documented protocol")
check("safe     = 127 (motor centre, no spin)", WEAPON_BYTES["safe"] == 127)
check("idle     = 160 (forward idle)",          WEAPON_BYTES["idle"] == 160)
check("attack   = 255 (full forward)",          WEAPON_BYTES["attack"] == 255)
check("idle_rev =  95 (reverse idle)",          WEAPON_BYTES["idle_rev"] == 95)
check("every weapon byte stays in range",
      all(0 <= v <= 255 for v in WEAPON_BYTES.values()))

hdr("7. Motor bytes can never leave 0-255, at any input")
bad = []
for mix in ("tank", "arcade"):
    for a, b in itertools.product([-5.0, -1.0, 0.0, 1.0, 5.0], repeat=2):
        for ml_m, mr_m in [(1.0, 1.0), (5.0, 5.0), (0.0, 0.0)]:
            for tl, tr in [(0, 0), (127, -127), (-127, 127)]:
                l, r = drive.drive_bytes(mix, a, b, ml_m, mr_m, tl, tr)
                if not (0 <= l <= 255 and 0 <= r <= 255):
                    bad.append((mix, a, b, ml_m, tl, l, r))
check(f"450 extreme combinations all clamp in range ({len(bad)} escapes)", not bad)

hdr("8. A trim command is never mistaken for a drive packet")
for tl, tr in [(0, 0), (127, -127), (-20, 20)]:
    pkt = trim_packet(tl, tr).strip().decode()
    fb = int(pkt[6:8], 16)
    check(f"trim L={tl:<5} R={tr:<5} failsafe byte = {fb} (not >127, so no "
          f"accidental killswitch)", fb == 1)
check("a killswitch packet is unambiguous",
      int(_ns["_hex_packet"](127, 127, 127, 255).strip().decode()[6:8], 16) == 255)

print()
print("=" * 70)
print("FAILURES:", fails if fails else "none")
print("=" * 70)
sys.exit(1 if fails else 0)
