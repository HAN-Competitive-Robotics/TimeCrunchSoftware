# Weapon-motor

Standalone ESP-IDF utility firmware for the **Hobbywing QUICRUN 8BL150 G2** ESC + **4268** brushless motor.

Flash this instead of the main robot firmware when you need to calibrate the ESC or test the motor. It has no radio dependency  everything is controlled over USB serial.

## Wiring

Connect the ESC signal lead (3-pin Dupont) to the ESP32:

| ESC wire | ESP32 |
|---|---|
| White (signal) | GPIO 21 |
| Black (ground) | GND |
| Red (+5V BEC) | Leave disconnected (or 5V/VIN if powering ESP32 from it) |

Connect the 3 motor phase wires (bullet connectors) to the motor in any order. If the disc spins the wrong direction after first run, swap any two phase wires.

Battery connects directly to the ESC power leads (XT30/XT60).

## Modes

Open [main/main.c](main/main.c) and set **one** define at the top:

```c
#define MODE_CALIBRATE   // throttle range calibration (first use)
// #define MODE_TEST     // interactive serial throttle control
```

## MODE_CALIBRATE  First use

Must be done once before the ESC will arm correctly. The ESC stores the calibration permanently.

1. Set `#define MODE_CALIBRATE` and flash
2. Open serial monitor (`idf.py monitor`)
3. Follow the prompts  the firmware walks through each step

What it does:
- Sets neutral (1500 µs) → you press SET on the ESC
- Sets full throttle (2000 µs) → you press SET
- Sets full brake (1000 µs) → you press SET

The motor **will not spin** during calibration  the ESC is only reading signal endpoints, not running.

## MODE_TEST  Spin the motor

After calibration is done.

1. Set `#define MODE_TEST` and flash
2. Open serial monitor
3. Connect battery to ESC, wait for arming beep
4. Type a number (0–100) and press Enter

```
Throttle:   0%  (1500 µs)   ← stopped
Throttle:  50%  (1750 µs)
Throttle: 100%  (2000 µs)   ← full speed
```

## Deadman timeout (MODE_TEST only)

While the throttle is non-zero, any keypress resets a 3 second timer. If
nothing arrives for 3 seconds the firmware ramps to neutral over 500 ms and
prints:

```
*** DEADMAN: no input for 3000 ms - ramping to neutral ***
```

This exists because the ESP32 **cannot** detect that USB was unplugged. UART0
sits behind the CP2102 bridge, whose DTR/RTS lines are wired to EN/BOOT for
auto-reset and are not readable from application code. A pulled cable, a
closed terminal, and an unattended bench all look identical from the
firmware's side, so rather than detect the cable it requires proof that
somebody is still present.

Tap a key every couple of seconds to hold a speed. Adjust `DEADMAN_TIMEOUT_MS`
at the top of `main/main.c` if 3 seconds proves awkward.

Calibration mode has no deadman: the motor does not spin during calibration.

## ESC LED codes

Transcribed from section 07 of `8BL150-manual.pdf`, which is in this directory
but is 11 MB and not something you want to scroll on a phone at an event.

### Normal running

| LED | Meaning |
|---|---|
| Both off | Throttle at neutral |
| Red solid | Running forward |
| Red solid + green solid | Full throttle |
| Red solid, reversing | Reverse. Green also lights at maximum reverse, if reverse force is set to 100% |

### Protection codes

**Count the green flashes.** One, three and five are three different faults.

| Pattern | Protection |
|---|---|
| Red, single flash, repeating | Low voltage cutoff |
| Green, single flash, repeating | ESC overheat |
| Green, three flashes, repeating | Current protection |
| Green, five flashes, repeating | Capacitor overheat |

What each one means for a weapon:

**Green x3, current protection.** Most likely on spin-up or after an impact.
The 8BL150 is rated 150 A continuous and 950 A peak, and accelerating a
kilogram of drum from a standstill is exactly when that gets tested.

**Green x1, ESC overheat.** Repeated spin-ups without cooling. The manual's
advice is to let it cool and reduce the load rather than to keep going.

**Red x1, low voltage.** The default cutoff is **3.0 V per cell**, so **12.0 V
on a 4S pack**. A drum spinning up sags a LiPo hard and briefly, so this can
fire mid-match on a pack that is not actually flat. Adjustable to 2.6 / 2.8 /
3.0 / 3.2 / 3.4 V per cell, or disabled, using the program card.

### Red flashing rapidly right after power-on

No throttle signal detected, or the neutral point is not calibrated. This is
the normal state when the ESC is powered before the ESP32 is producing PWM, so
expect it during bringup. If it persists once the robot is running, check that
the signal wire is on GPIO 21 and that the ESC has been calibrated.

### Power-on beeps

The ESC beeps once per detected cell, then a long beep when self-check
completes. Four beeps then a long beep on a 4S pack. Free confirmation that
the battery is the one you think it is.

The motor beeps and the LED flashes at the same time, so if the motor beeps
are too quiet to hear you can watch the LED instead.

## Flashing

```bash
source ../venv/bin/activate
idf.py -B build -p /dev/cu.usbserial-XXXX flash monitor
```

Or use the top-level flash script and select option 6 (build only) first to check for errors.

## After testing

Flash the normal robot firmware from the `robot/` directory to restore competition behaviour.
