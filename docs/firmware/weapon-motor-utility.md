# Weapon Motor Utility (`weapon-motor/`)

## Purpose

This is a **standalone ESP-IDF firmware** for the weapon ESC that provides two utilities:

1. **CALIBRATE**  step-by-step guided throttle range calibration for the 8BL150 ESC
2. **TEST**  interactive serial-controlled motor test (type 0–100 to set throttle)

This firmware is only needed:
- On first use of a new ESC or after an ESC factory reset
- When verifying ESC behaviour before installing in the robot

**This firmware must not be left on the robot.** Flash the robot firmware before field use.

---

## Build Modes

The firmware uses a compile-time define to select the mode:

```bash
# Via flash script (recommended):
python scripts/flash.py --weapon-calibrate   # builds with MODE_CALIBRATE
python scripts/flash.py --weapon-test        # builds with MODE_TEST

# Manually with idf.py:
idf.py -B build_calibrate -DWEAPON_MODE=MODE_CALIBRATE flash monitor
idf.py -B build_test      -DWEAPON_MODE=MODE_TEST      flash monitor
```

If neither `MODE_CALIBRATE` nor `MODE_TEST` is defined, compilation fails with a `#error` message. This prevents accidental flashing of an unconfigured firmware.

---

## Calibration Procedure (MODE_CALIBRATE)

The 8BL150 ESC requires a one-time throttle range calibration so it knows the minimum, neutral, and maximum pulse widths your controller will send. Run this on a new ESC or after resetting the ESC.

```
STEP 1  Hold the SET button on the ESC.
        Press ON/OFF to power it on.
        RED LED flashes → release SET immediately.
        Press Enter when RED LED is flashing...

STEP 2  Signal → NEUTRAL (1500 µs)
        Press SET on ESC → GREEN flashes 1×, 1 beep.

STEP 3  Signal → FULL THROTTLE (2000 µs)
        Press SET on ESC → GREEN flashes 2×, 2 beeps.
        (Motor will NOT spin  ESC is in calibration mode.)

STEP 4  Signal → FULL BRAKE (1000 µs)
        Press SET on ESC → GREEN flashes 3×, 3 beeps.

✓  CALIBRATION COMPLETE
```

The ESP32 automatically drives the correct pulse width at each step. All you do is follow the prompts and press Enter.

**Important:** Do NOT have the motor's propeller/weapon disc attached during calibration. The ESC does not drive the motor during calibration, but verify this is the case for your specific ESC before proceeding.

---

## Test Mode (MODE_TEST)

Test mode displays a prompt and accepts 0–100 values over serial:

```
╔══════════════════════════════╗
║   WEAPON ESC TEST            ║
╚══════════════════════════════╝

Connect battery to ESC. Wait for arming beep.
Type 0-100 and press Enter to set throttle %.
0 = stopped (neutral), 100 = full speed.

> 50
Throttle:  50%  (1750 µs)
```

**Safety note:** 0 means the neutral pulse (1500 µs), not full brake (1000 µs). The throttle range is mapped as neutral-to-full-forward only:

```c
uint32_t us = PWM_NEUTRAL + pct * (PWM_FULL_FWD - PWM_NEUTRAL) / 100;
// pct=0   → 1500 µs (neutral)
// pct=50  → 1750 µs
// pct=100 → 2000 µs
```

This matches the robot firmware's weapon control convention  the weapon ESC is never commanded to brake or reverse.

---

## Hardware Requirements

- ESP32 DevKit with GPIO 21 connected to ESC signal input
- ESC connected to weapon motor
- Battery connected to ESC (for test mode) or just ESC power (for calibrate mode)
- USB cable from ESP32 to laptop for serial monitoring

The GPIO pin and PWM parameters are defined at the top of `weapon-motor/main/main.c`:
```c
#define WEAPON_GPIO     21
#define PWM_NEUTRAL     1500
#define PWM_FULL_FWD    2000
#define PWM_FULL_BRK    1000
```

These match the robot firmware's weapon motor pin and timing, so calibration here is valid for the robot.

---

## When to Re-Calibrate

Re-calibrate if:
- The weapon motor does not spin when commanded in test mode (ESC not armed)
- The weapon spins at unexpected speeds relative to commanded throttle
- The ESC was factory reset
- You replace the ESC with a different model

Do not re-calibrate unnecessarily  ESC calibration is stored in the ESC's non-volatile memory and is persistent across power cycles.

---

## See Also

- [Robot Firmware](robot-firmware.md)
- [Build and Flash](build-and-flash.md)
- [Architecture](../architecture.md)
