# Build and Flash Guide

## Quick Reference

```bash
# Interactive menu  recommended for most cases
python scripts/flash.py

# Direct commands
python scripts/flash.py --robot              # flash ESP32 robot + open monitor
python scripts/flash.py --dongle             # build + flash nRF52840 dongle
python scripts/flash.py --both               # flash both + open monitor
python scripts/flash.py --weapon-calibrate   # flash weapon ESC calibration
python scripts/flash.py --weapon-test        # flash weapon ESC test
python scripts/flash.py --build-robot        # build robot only (no flash)
python scripts/flash.py --robot --no-monitor # flash robot without opening monitor

# Port detection
python scripts/find-ports.py
```

---

## Prerequisites by Device

### ESP32 (`robot/` and `weapon-motor/`)

1. Install ESP-IDF at `~/esp/esp-idf` (exact path required by flash script)
2. Follow [ESP-IDF Setup](../onboarding/esp-idf-setup.md)
3. ESP32 DevKit connected via USB

### nRF52840 Dongle (`radio-dongle/`)

1. Install nRF Connect SDK (NCS) with `west` and `nrfutil` in PATH
2. Follow [Zephyr Setup](../onboarding/zephyr-setup.md)
3. Dongle in USB bootloader mode (hold reset while plugging in)

### Python station (`driver/`)

1. Python 3.10+
2. `pip install pygame pyserial`
3. No flashing required  runs on laptop

---

## Flashing the ESP32 Robot (`robot/`)

### Via flash script

```bash
python scripts/flash.py --robot
```

The script:
1. Auto-detects the ESP32 serial port (CP210x/CH340 USB-UART chip)
2. Checks the port is not in use by another process
3. Sources `~/esp/esp-idf/export.sh` (sets up IDF environment)
4. Runs `idf.py -B build flash`
5. Opens `idf.py monitor` (Ctrl+] to exit)

### Manually

```bash
cd robot
source ~/esp/esp-idf/export.sh
idf.py -p /dev/cu.usbserial-XXXX flash monitor
```

Replace `/dev/cu.usbserial-XXXX` with your port. Find it with:
```bash
python scripts/find-ports.py
```

### Build only (no flash)

```bash
python scripts/flash.py --build-robot
# or manually:
cd robot && idf.py -B build build
```

---

## Flashing the nRF52840 Dongle (`radio-dongle/`)

### Put the dongle in bootloader mode

Press the **small reset button** (the small white sideways attached button). The dongle enters Nordic Bootloader DFU mode  a red LED should fade in/out or the device should enumerate as a DFU device.

On macOS you should see a new `JLINK` mass-storage drive or a DFU serial port appear.

### Via flash script

```bash
python scripts/flash.py --dongle
```

This runs `scripts/build-dongle.py flash`, which:
1. Runs `west build` for the nRF52840 dongle board
2. Packages firmware into a DFU zip with `nrfutil nrf5sdk-tools pkg generate`
3. Programs via `nrfutil device program`

### Via build-dongle.py directly

```bash
python scripts/build-dongle.py           # build only
python scripts/build-dongle.py flash     # build + flash
python scripts/build-dongle.py clean     # clean build directory
```
### Via NRF Connect App and VSCode extension (Manually)

1. Add build configuration in the NRF Connect SDK VSCode extension, select the ```nrf52840dongle/nrf52840 ``` board and generate
2. Open the Programmer in the NRF Connect App and select the device(Should show up as DFU Bootloader if put into bootloader mode using the white sideways button)
3. Add the hex file from path  ``` ~\TimeCrunchSoftware\radio-dongle\build\radio-dongle\zephyr\zephyr.hex ``` and doublecheck it does not overwrite the bootloader section of the memory then press write to flash the dongle
   
### Environment configuration

If `west` is not in your PATH, copy the example environment file and fill in your SDK path:

```bash
cp radio-dongle/local/ncs.env.example radio-dongle/local/ncs.env
# Edit ncs.env and set NCS_TOOLCHAIN and NCS_SDK paths
```

---

## Flashing Weapon Motor Utility (`weapon-motor/`)

```bash
# Calibration mode
python scripts/flash.py --weapon-calibrate

# Test mode
python scripts/flash.py --weapon-test
```

Both flash the weapon-motor project with different build directories (`build_calibrate`, `build_test`). See [Weapon Motor Utility](weapon-motor-utility.md) for usage.

---

## Port Auto-Detection

`scripts/find-ports.py` lists all detected serial ports categorised by device type:

```
=== Detected serial ports ===
ESP32 (robot):
  /dev/cu.usbserial-0001   CP2102 USB to UART Bridge Controller
nRF52840 dongle:
  /dev/cu.usbmodem1201     USB-CDC
  /dev/cu.usbmodem1203     USB-CDC

FIRST_ESP32=/dev/cu.usbserial-0001
FIRST_DONGLE=/dev/cu.usbmodem1203
```

The `FIRST_DONGLE` value is the data port (highest-numbered `usbmodem`). The lower-numbered port is the Zephyr log console.

---

## IDF Monitor

After flashing, the monitor (`idf.py monitor`) streams the ESP32's serial output in real time. Key shortcuts:

| Key | Action |
|---|---|
| Ctrl+] | Exit monitor |
| Ctrl+T Ctrl+R | Reset ESP32 |
| Ctrl+T Ctrl+F | Flash again (without quitting monitor) |
| Ctrl+T Ctrl+A | Toggle timestamps |

Log output format:
```
I (1234) MAIN: Initializing motor driver...
I (1250) MOTOR: MCPWM init OK: 3 motors on group 0
I (1280) NRF24: nRF24 configured: channel=40 payload=4 @ 8 MHz SPI
I (1290) MAIN: STATUS = 0x0E
I (1290) MAIN: RF_CH = 40 (0x28)
D (1305) MAIN: RX: L=127 R=127 W=  0 F=  0
```

- `I` = INFO, `W` = WARNING, `E` = ERROR, `D` = DEBUG
- `(1234)` = milliseconds since boot
- `MAIN`, `MOTOR`, `NRF24`, `ENCODER`, `TEMP` = log tags

---

## Troubleshooting Flash Issues

| Symptom | Cause | Fix |
|---|---|---|
| `ESP-IDF not found at ~/esp/esp-idf` | IDF installed elsewhere | Set `IDF_PATH` env var, or reinstall to `~/esp/esp-idf` |
| `No module named serial` | pyserial not installed | `pip install pyserial` |
| `Cannot open port  busy` | IDF monitor is running | Close monitor: Ctrl+], or `pkill -f monitor` |
| `west not found` | NCS not in PATH, no ncs.env | Copy ncs.env.example, fill in paths |
| Dongle not detected as DFU | Not in bootloader mode | Hold reset button while plugging in |
| Flash succeeds but robot unresponsive | Wrong firmware, bad wiring | Check serial output, verify pin connections |

---

## See Also

- [ESP-IDF Setup](../onboarding/esp-idf-setup.md)
- [Zephyr Setup](../onboarding/zephyr-setup.md)
- [First Bringup](../onboarding/first-bringup.md)
- [Debugging Workflow](../onboarding/debugging-workflow.md)
