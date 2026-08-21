# Closing the weapon speed loop

The weapon PI controller has always shipped with `WEAPON_KP = 0` and
`WEAPON_KI = 0`, running on a fixed 50% feed-forward baseline. This document is
the procedure for replacing those zeros with measured values.

Do not skip to the end and guess gains. A weapon rotor at 5000 RPM stores enough
energy to be a mechanical hazard, and an untuned proportional gain on a loop that
can command full throttle is the specific way that hazard gets realised.

---

## Why the gains could not be tuned before

The loop was not left open through neglect. It was not tunable.

The Hall driver used to count edges inside a fixed 20 ms window, so the RPM it
reported was quantised to

```
60 / 0.020 / 2 pulses-per-rev = 1500 RPM per count
```

The only measurable values were 0, 1500, 3000, 4500, 6000. The attack target of
5000 RPM is not on that grid at all: the sensor reported 4500 or 6000 and
dithered between them. Any non-zero `KP` multiplies an error carrying +/-1500 RPM
of quantisation noise, which slams the throttle between its limits.

`hall_sensor.c` now times the interval between edges instead. At 5000 RPM the
edges are 6000 us apart and the sensitivity is

```
d(RPM)/d(period) = 60e6 / (2 * 6000^2) = 0.83 RPM per microsecond
```

so a 1 us timer resolves better than 1 RPM. `robot/test` measures this directly
and reports it as roughly 1800x the old resolution. That is the change that makes
everything below possible.

---

## Before you start

Work through this list in order. Steps 1 to 3 do not involve a spinning weapon.

**1. Safety setup.**
- Rotor restrained or replaced with a mass-equivalent dummy for the first runs.
- Nobody in the plane of rotation. Ever, including the person holding the laptop.
- Killswitch within reach of a second person, tested before the motor is armed.
- Robot mechanically secured. It will try to move under weapon torque reaction.

**2. Confirm `HALL_SENSOR_PULSES_PER_REV` matches the hardware.**
It is currently `2`, correct for one diametrically magnetised magnet. If the
rotor carries a different pole count, every RPM figure below is wrong by that
ratio. Turn the rotor by hand exactly ten revolutions and check that
`hall_sensor_get_edge_count()` advances by `10 * PULSES_PER_REV`.

**3. Confirm the sensor reports sanely under power.**
Arm the weapon at the 50% feed-forward baseline and watch the logged RPM. It
should be steady, not jumping between widely separated values. If it is noisy,
fix that first: `HALL_MIN_EDGE_INTERVAL_US` rejects edges closer than 200 us, and
`HALL_EMA_SHIFT` controls smoothing.

**4. Confirm the feedback fault path works, before you rely on it.**
With the weapon armed and spinning, disconnect the Hall signal. Within
`WEAPON_FEEDBACK_FAULT_MS` you should see:

```
E SAFETY: WEAPON FEEDBACK FAULT: commanded ..% for 1500 ms with no Hall edge.
          Holding integrator, running open-loop feed-forward.
```

and the weapon should continue at the feed-forward baseline rather than
accelerating. If it accelerates, stop and fix that before tuning anything: with
a closed loop and no fault detection, a disconnected sensor reads 0 RPM, the
error becomes the full target, and the controller commands full throttle.

---

## The step test

With the loop still open (`KP = KI = 0`), record a throttle step and the RPM
response.

1. Arm the weapon and let it settle at the feed-forward baseline. Record the
   steady RPM as `rpm_1` and the throttle as `u_1` (50%).
2. Step the throttle to a second value `u_2` (70% is a reasonable step; stay
   well inside the mechanical limits of the rotor).
3. Log RPM at 100 Hz until it settles. Record the new steady value `rpm_2`.
4. Repeat at least three times and average. One run is not a measurement.

From the averaged response, extract two numbers:

**Process gain** `K`, in RPM per percent of throttle:

```
K = (rpm_2 - rpm_1) / (u_2 - u_1)
```

**Time constant** `tau`, in seconds: the time taken to cover 63.2% of the change
from `rpm_1` to `rpm_2`.

---

## Computing the gains

The weapon behaves as a first-order system, `G(s) = K / (tau*s + 1)`. Placing the
PI zero on the plant pole cancels it and leaves a first-order closed loop with
time constant `lambda`:

```
KI / KP = 1 / tau            (pole cancellation)
KP      = tau / (K * lambda)
KI      = 1   / (K * lambda)
```

Choose `lambda`, the closed-loop time constant you are asking for:

| `lambda` | Behaviour |
|---|---|
| `tau` | No speed-up. Adds steady-state accuracy and disturbance rejection at the response speed the weapon already has. **Start here.** |
| `tau / 2` | Roughly twice as responsive. Reasonable second step once `lambda = tau` is proven stable. |
| `tau / 5` or faster | Will saturate the ESC on every command change and hammer the drivetrain. Not appropriate for a weapon with this inertia. |

Starting at `lambda = tau` simplifies to:

```
KP = 1 / K
KI = 1 / (K * tau)
```

**Worked example, with invented numbers.** If the step test gave
`K = 100 RPM/%` and `tau = 1.5 s`, then `KP = 0.010` and `KI = 0.0067`. These are
an illustration of the arithmetic, not values to type in.

---

## Verify before you flash

Put your candidate gains through the host tests first. They compile the real
controller natively, so this costs seconds and no hardware:

```sh
cd robot/test
make TEST_GAINS="-DWEAPON_KP=0.010f -DWEAPON_KI=0.0067f"
```

`test_windup` exercises the saturated path and checks that the integral parks at
the edge of the actuator range rather than running through it, and that the
controller backs off within a step or two once the error changes sign. If your
gains fail those, they will misbehave on the robot too.

---

## Commissioning on the robot

Set the gains in `robot/main/include/weapon_controller.h`, or override them at
build time without editing the file:

```sh
idf.py build -DWEAPON_KP=0.010f -DWEAPON_KI=0.0067f
```

Then, in this order:

1. **Idle target only.** Command idle (3000 RPM) and confirm it settles without
   oscillation and without hunting. Watch the logged `output` and `integral`.
2. **Step between idle and attack.** Confirm the transition is monotonic. Some
   overshoot is acceptable; sustained oscillation is not, and means `lambda` was
   set too aggressively. Increase `lambda` and recompute.
3. **Disturbance test.** Load the rotor briefly against something soft and
   confirm the controller restores speed and then settles, rather than
   oscillating around the target afterwards.
4. **Fault test again, closed loop.** Repeat step 4 from the preconditions with
   non-zero gains. This is the run that matters: it proves the fault path
   protects a loop that is actually closed.
5. **Soak.** Run the weapon through repeated arm and disarm cycles for several
   minutes and confirm no watchdog resets appear in the log.

---

## Recording the result

Whatever you land on, write down alongside the gains:

- `K` and `tau`, the runs they came from, and the spread across runs
- the `lambda` chosen and why
- the overshoot and settling time actually measured on the robot
- how RPM accuracy was measured, over how many runs

Not for its own sake. A tuned gain with no recorded step response is a number
you cannot defend when someone asks where it came from, and the whole reason
this loop is worth closing is that it is defensible.

---

## What this does not fix

The CV describes the robot as split across "three MCUs ... two ESP32s on FreeRTOS
for drive and weapon". The firmware in this repository runs drive, weapon and
all failsafes on a single dual-core ESP32, with the nRF52840 acting as a USB
radio bridge on the driver-station side rather than as a robot MCU. See
`docs/architecture.md`. Closing the weapon loop does not change that, and no
firmware change can: it is either a hardware decision or a wording correction.
