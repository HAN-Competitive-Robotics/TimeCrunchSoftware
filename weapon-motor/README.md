# weapon-motor

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

## Flashing

```bash
source ../venv/bin/activate
idf.py -B build -p /dev/cu.usbserial-XXXX flash monitor
```

Or use the top-level flash script and select option 6 (build only) first to check for errors.

## After testing

Flash the normal robot firmware from the `robot/` directory to restore competition behaviour.
