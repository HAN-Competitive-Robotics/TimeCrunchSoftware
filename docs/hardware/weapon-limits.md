# Weapon Limits — Tip Speed and Kinetic Energy

Worked calculation for the drum, against the two limits it has to satisfy.
**Both pass at full throttle.** The margins are not large, so the inputs below
are load-bearing: changing any one of them invalidates this page.

Last checked: 2026-09-08.

## Limits

| Limit | Value |
|---|---|
| Max theoretical tip speed | 250 mph |
| Max rotational kinetic energy | 2000 J |

> Confirm these against the rulebook for the specific event. Tip-speed
> calculators in circulation quote **200 J** for Robodojo Featherweight
> Sportsman, which is a factor of ten different and would make this weapon
> roughly 8x over. Do not assume the limit; look it up.

## Inputs

| Quantity | Value | Where it came from |
|---|---|---|
| Motor | Hobbywing QUICRUN 4268 G2 | part |
| Motor kV | **2600 kV** | printed on the box |
| Battery | **4S** LiPo, 4.2 V/cell charged | build |
| Pulley ratio | **2:1** output:motor | build |
| Drum diameter | **85 mm** | measured |
| Drum mass | 1081 g | SolidWorks |
| Inertia about spin axis | **621,722 g·mm²** | SolidWorks, at centre of mass |

The ESC (QUICRUN WP 8BL150 G2) permits kV ≤ 3000 on 4S, so 2600 is within
spec. See `weapon-motor/8BL150-manual.pdf`.

## Tip speed

kV is rpm per volt with no load. It is a hard ceiling: at that speed the
motor's back-EMF equals the supply voltage, so nothing remains to accelerate
it. A more powerful motor of the same kV reaches the ceiling sooner; it does
not exceed it.

```
pack voltage    V = 4 × 4.2 V          = 16.8 V     (full charge, worst case)
motor speed     N = 2600 × 16.8        = 43,680 rpm
drum speed      N = 43,680 ÷ 2         = 21,840 rpm (2:1 reduction)
revs per second f = 21,840 ÷ 60        = 364 rev/s
circumference   C = π × 0.085 m        = 0.2670 m
tip speed       v = 364 × 0.2670       = 97.2 m/s
                  = 97.2 × 2.23694     = 217 mph
```

**217 mph against 250 mph. Passes, 13% margin.**

Every term is a linear multiplier. Double the voltage, or the diameter, or
halve the reduction, and tip speed doubles.

## Kinetic energy

```
angular velocity  ω = 21,840 × 2π/60           = 2,287 rad/s
inertia in SI     I = 621,722 g·mm² × 10⁻⁹     = 6.217 × 10⁻⁴ kg·m²
energy           KE = ½ I ω²
                    = ½ × 6.217×10⁻⁴ × 5,230,735
                    = 1,626 J
```

**1,626 J against 2,000 J. Passes, 19% margin.**

Energy scales with the **square** of speed, so it is far more sensitive than
tip speed and is the binding constraint here:

```
speed multiple to reach 2000 J = √(2000 / 1626) = 1.11
```

Reaching the energy limit would need **111%** throttle, and the tip-speed
limit **115%**. Neither exists, so compliance is enforced by the hardware
rather than by firmware being correct. That is deliberate and worth keeping.

## Two ways to get the inertia wrong

**Use the value taken at the CENTRE OF MASS, not at the output coordinate
system.** SolidWorks prints both. The output-coordinate-system figure includes
a parallel-axis term for the distance from the CAD origin, which for this
assembly is about 1.6 m:

```
at centre of mass         Lzz =       621,722 g·mm²   ← correct
at output coordinate sys  Izz = 2,526,314,847 g·mm²   ← 4000x too large
```

Using the wrong one gives 6.6 MJ. An object on its own shaft rotates about its
own centre, not about wherever the CAD origin happens to sit.

**For a drum, take the SMALLEST principal moment, not the largest.** Several
online calculators advise "take the axis with the largest value", which is
correct for bars and discs, where the spin axis has the largest moment. A drum
spinning about its long axis is the opposite:

```
Px = 621,722    axis (0,0,1)   ← the spin axis. Smallest.
Py = 2,291,856
Pz = 2,620,169
```

Taking the largest, or summing all three, overstates the energy by 4x to 9x
and has already produced a false failure on this robot.

Check that the principal axis direction matches the shaft. Here `Px` has axis
`(0,0,1)`, and `Lzz` is the same number, which confirms the drum spins about
the model's Z axis.

## What invalidates this page

| Change | Tip speed | Energy |
|---|---|---|
| 5S instead of 4S | 272 mph — fails | 2,540 J — fails |
| 1:1 pulleys | 435 mph — fails | 6,504 J — fails |
| 100 mm drum | 256 mph — fails | recompute |
| Heavier or more rim-weighted drum | unchanged | recompute |

At this gearing the largest legal drum is about **98 mm**. The pack is not
just a choice, it is part of compliance: 5S fails both limits.

## Still to verify

- **Pulley ratio: confirmed 2:1 by the builder (2026-09-08).** It is a linear
  multiplier on both results, so it was the highest-risk input; with it
  confirmed, the calculation stands on measured/known figures.
- **Check the material density.** 1081 g ÷ 158,873 mm³ = 6.80 g/cm³, which is
  not a common single material. Plausible for a mixed assembly, but if any
  component is on SolidWorks' default the mass and the energy are wrong.

## Relationship to firmware

`WEAPON_MAX_OUTPUT_PCT` in `robot/main/include/weapon_controller.h` caps
throttle. It is now set to **100%** (full), with open-loop attack
(`WEAPON_OL_ATTACK_PCT`) at **100%** and idle (`WEAPON_OL_IDLE_PCT`) at **50%**,
because the calculation above shows 100% is inside both limits with margin, so
holding it lower only costs weapon performance.

The ceiling is **not** what keeps this weapon legal — the hardware and the
physics do that — so at 100% there is no firmware margin standing between a
wrong input and an illegal weapon. The pulley ratio, the highest-risk input, is
confirmed 2:1, so the calculation rests on measured/known figures. The one
remaining gap is that with no Hall sensor fitted there is **no RPM readback**:
the theoretical table below is the only evidence of the real speed, and the
wireless bench test commands a percentage without measuring the resulting rpm.

Full throttle is also the highest current draw, hardest at spin-up. The
QUICRUN WP 8BL150 G2 is rated 150 A continuous / 950 A peak.

Throttle maps roughly linearly to rpm at no load, so:

| Throttle | Tip speed | Energy |
|---|---|---|
| 40% | 87 mph | 260 J |
| 60% | 130 mph | 585 J |
| 80% | 174 mph | 1,041 J |
| 100% | 217 mph | 1,626 J |

Under load real rpm is lower, so this table over-estimates, which is the safe
direction.
