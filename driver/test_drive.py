"""Verify the drive mixing maths.

Run with:  python test_drive.py

No pytest dependency on purpose: students already have enough to install, and
this needs to stay runnable on a laptop with nothing but the driver deps.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import drive

fails = []


def check(label, got, want):
    ok = got == want
    print(f"  {'ok ' if ok else 'FAIL'}  {label}: got {got}, want {want}")
    if not ok:
        fails.append(label)


print("=" * 66)
print("to_byte: centre and saturation")
print("=" * 66)
check("neutral", drive.to_byte(0.0), 127)
check("full fwd", drive.to_byte(1.0), 255)
check("full rev", drive.to_byte(-1.0), 0)
check("over-range clamps high", drive.to_byte(4.0), 255)
check("over-range clamps low", drive.to_byte(-4.0), 0)

print()
print("=" * 66)
print("tank: sticks map straight through, no cross-talk")
print("=" * 66)
check("both fwd", drive.drive_bytes("tank", 1.0, 1.0), (255, 255))
check("left only", drive.drive_bytes("tank", 1.0, 0.0), (255, 127))
check("right only", drive.drive_bytes("tank", 0.0, 1.0), (127, 255))
check("spin", drive.drive_bytes("tank", 1.0, -1.0), (255, 0))

print()
print("=" * 66)
print("arcade: Y drives both, X biases apart")
print("=" * 66)
check("straight fwd", drive.drive_bytes("arcade", 1.0, 0.0), (255, 255))
check("spin in place", drive.drive_bytes("arcade", 0.0, 1.0), (255, 0))
# full forward + full right: left saturates, right drops to a stop (not
# reverse), which is a pivot turn while still moving forward.
check("fwd+steer pivots", drive.drive_bytes("arcade", 1.0, 1.0), (255, 127))
check("neutral", drive.drive_bytes("arcade", 0.0, 0.0), (127, 127))

print()
print("=" * 66)
print("rocket: trigger throttle, stick steer, turns while stationary")
print("=" * 66)
check("RT full", drive.drive_bytes("rocket", 1.0, 0.0), (255, 255))
check("LT full (reverse)", drive.drive_bytes("rocket", -1.0, 0.0), (0, 0))
check("stationary spin", drive.drive_bytes("rocket", 0.0, 1.0), (255, 0))
check("half throttle + steer", drive.drive_bytes("rocket", 0.5, 0.25),
      (drive.to_byte(0.75), drive.to_byte(0.25)))

print()
print("=" * 66)
print("invert swaps sides, keeps forward as forward")
print("=" * 66)
check("tank swapped", drive.drive_bytes("tank", 1.0, 0.0, invert=True), (127, 255))
check("straight ahead unchanged",
      drive.drive_bytes("arcade", 1.0, 0.0, invert=True), (255, 255))

print()
print("=" * 66)
print("trim and mult match the old byte-space formula")
print("=" * 66)


def legacy(fwd, right, mult_l, mult_r, trim_l, trim_r):
    """The exact arithmetic station.py used, for comparison."""
    ml = int(max(0, min(255, 127 + fwd * 128)))
    mr = int(max(0, min(255, 127 + right * 128)))
    ml = int(max(0, min(255, 127 + (ml - 127) * mult_l + trim_l)))
    mr = int(max(0, min(255, 127 + (mr - 127) * mult_r + trim_r)))
    return ml, mr


for fwd, right, ml, mr, tl, tr in [
    (0.0, 0.0, 1.0, 1.0, 0, 0),
    (0.5, -0.5, 1.0, 1.0, 5, -5),
    (1.0, 1.0, 0.5, 0.5, 0, 0),
    (0.0, 0.0, 1.0, 1.0, 10, -10),
    (-0.25, 0.75, 1.2, 0.8, 3, 3),
]:
    want = legacy(fwd, right, ml, mr, tl, tr)
    got = drive.drive_bytes("tank", fwd, right, ml, mr, tl, tr)
    # allow 1 byte of rounding drift between float and int pipelines
    close = all(abs(g - w) <= 1 for g, w in zip(got, want))
    print(f"  {'ok ' if close else 'FAIL'}  fwd={fwd} right={right} "
          f"mult=({ml},{mr}) trim=({tl},{tr}): got {got}, legacy {want}")
    if not close:
        fails.append(f"legacy parity {fwd},{right}")

print()
print("=" * 66)
print("unknown mode falls back rather than raising")
print("=" * 66)
check("bogus mode", drive.drive_bytes("nonsense", 1.0, 0.0), (255, 127))

print()
print("FAILURES:", fails if fails else "none")
sys.exit(1 if fails else 0)
