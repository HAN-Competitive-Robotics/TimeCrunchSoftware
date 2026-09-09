# Wireless Weapon Test - Setup Guide

Spin the weapon at a set percentage from the driver station, over the radio,
with every failsafe in place. This replaces having to tether the weapon board
to a laptop over USB.

**This is not the `--weapon-test` flag.** That flag flashes the standalone
`weapon-motor/` firmware, which is the *old USB-tethered* test with no radio.
The wireless test lives in the normal **robot** firmware and is driven from the
station's `WEAPON TEST (BENCH)` panel. So you flash `--robot`, not
`--weapon-test`.

---

## What you need

- The robot's main ESP32, its nRF24 radio, and the weapon ESC + motor wired up.
  Drive wheels do **not** need to be connected.
- The nRF52840 dongle in the driver laptop.
- The weapon on a stand or the bot clamped down, weapon area clear. Treat it as
  live - it stores ~1.6 kJ.
- The weapon ESC already calibrated (one-time). If it has never been calibrated,
  do that first with `python scripts/flash.py --weapon-calibrate` (that is the
  `weapon-motor` calibrate firmware), then come back and flash the robot
  firmware per step 2.

## Step 1 - Get the merged code (do not skip)

The wireless test was merged in PR #15. If your checkout predates that, you will
flash firmware without it and wonder why the panel does nothing.

```bash
git checkout main
git pull
```

Confirm you have it:

```bash
grep -c "WEAPON TEST (BENCH)" driver/station.py    # expect 1
grep -c "PACKET_OPCODE_WEAPON_TEST" robot/main/include/robot_config.h   # expect >=1
```

## Step 2 - Flash the robot firmware

This is the firmware that drives the weapon ESC (GPIO 21) and understands the
wireless test command.

```bash
python scripts/flash.py --robot
```

It builds and flashes the ESP32, then opens the serial monitor. On the monitor,
confirm the radio came up: `STATUS = 0x0E` and `RF_CH = 40`. If you see
`STATUS = 0xFF`, the nRF24 SPI is not wired right (check 3.3 V, not 5 V) - stop
and fix it before testing.

**On WSL:** attach the ESP32 to WSL first with `usbipd` (bind + attach the
ESP32's busid), then run the flash. See `scripts/setup-wsl.sh` and the WSL notes
the script prints. Flash the ESP32, not the dongle - `flash.py` auto-detects and
skips the dongle when flashing `--robot`.

## Step 3 - Flash the dongle (only if it is not already flashed)

The dongle usually only needs flashing once. If it is already running, skip this.

```bash
python scripts/flash.py --dongle
```

## Step 4 - Wiring sanity check

- Weapon ESC signal on **GPIO 21**, ground to GND.
- nRF24: **VCC = 3.3 V (never 5 V)**, SPI seated, antenna attached.
- Battery: **4S**, charged, secured.

## Step 5 - Station config for TESTING

Open `driver/config.json`:

- `safety.failsafe_on_dongle_removal` → **`true`** for bench testing. Unplugging
  the dongle then becomes a guaranteed kill, which is what you want on the
  bench. (Remember to set it back to `false` for competition matches - during a
  match a USB glitch would otherwise permanently kill the bot.)
- The weapon unlock password must be set and you must know it.

## Step 6 - Launch the station

```bash
cd driver
python station.py
```

Confirm **SERIAL OK** in the top strip. A gamepad is optional for the weapon
test - everything is on-screen buttons, and the keyboard `F` and the on-screen
`KILL ROBOT` button both work without one.

## Step 7 - Run the test

1. Open the **WEAPON TEST (BENCH)** section (right-hand card).
2. Set the **percentage** and **direction** (Forward / Reverse).
3. Call it out loud, make sure everyone is clear, then press **SPIN**.
   - The first press asks for the weapon password.
   - The weapon spins at your set percent. The wheels are forced neutral, so the
     bot cannot drive off the stand.
4. **SPIN is a deadman: re-press it within 5 seconds or the weapon stops.** The
   button shows a live countdown. **STOP** ends it immediately.

The banner reads `WEAPON TEST  <n>% <dir>` while it runs.

## Stopping it

Any of these stops the weapon:

- Stop pressing SPIN (deadman lapses after 5 s).
- **STOP TEST** button.
- **KILL ROBOT** (on-screen), keyboard **F**, or gamepad **B** - these latch a
  killswitch and deep-sleep the robot; power-cycle and RESET KILLSWITCH to
  recover.
- Unplug the dongle (with the step-5 flag on, this latches a kill too).
- Link loss on its own cuts the weapon within 500 ms.

## A note on numbers

The percent is throttle, not speed. With no Hall sensor fitted there is no RPM
readback, so the panel commands a percentage and cannot measure the resulting
rpm. The legality figures come from calculation, not measurement - see
`docs/hardware/weapon-limits.md`. At 100% on a 4S pack with the 2:1 pulley this
is 217 mph / 1.6 kJ, inside the limits, but treat every spin-up as dangerous.
