# Onboarding

## What You Need

| Component | Tool |
|---|---|
| Robot firmware (ESP32) | ESP-IDF v5.x |
| Radio dongle (nRF52840) | nRF Connect SDK v2.7+ + west + nrfutil |
| Ground station (Python) | Python 3.10+, pygame, pyserial |
| Flashing | Python 3.10+ (flash scripts) |

---

## Python Setup (All Platforms)

### macOS
```bash
brew install python3
pip3 install pygame pyserial
```

### Linux (Ubuntu/Debian)
```bash
sudo apt install python3 python3-pip
pip3 install pygame pyserial
```

### Windows
Download Python 3.10+ from python.org. Check **"Add Python to PATH"** during install, then:
```cmd
pip install pygame pyserial
```

---

## ESP-IDF Setup

The flash script expects ESP-IDF at `~/esp/esp-idf`. Install there exactly.

### macOS / Linux
```bash
# Prerequisites (macOS)
brew install cmake ninja dfu-util

# Prerequisites (Ubuntu/Debian)
sudo apt install git cmake ninja-build python3 python3-pip libffi-dev libssl-dev dfu-util

# Clone and install
mkdir -p ~/esp && cd ~/esp
git clone --recursive https://github.com/espressif/esp-idf.git
cd esp-idf
./install.sh esp32        # downloads ~1.5 GB toolchain

# Activate (required in every new terminal)
source ~/esp/esp-idf/export.sh
```

### Windows
Use the [Espressif offline installer](https://docs.espressif.com/projects/esp-idf/en/latest/esp32/get-started/windows-setup.html). It places ESP-IDF at `C:\esp\esp-idf`. Use the "ESP-IDF PowerShell" shortcut to activate.

### Verify
```bash
source ~/esp/esp-idf/export.sh
idf.py --version    # ESP-IDF v5.x.x
```

This project requires **ESP-IDF v5.x**. v4.x will fail — `mcpwm_prelude.h` was introduced in v5.0.

---

## Zephyr / nRF Connect SDK Setup

### Option A — nRF Connect for Desktop (Recommended)

1. Download [nRF Connect for Desktop](https://www.nordicsemi.com/Products/Development-tools/nRF-Connect-for-Desktop)
2. Install the **Toolchain Manager** plugin
3. Use it to install NCS v2.7
4. Note the installation path (e.g. `/opt/nordic/ncs/v2.7.0`)
5. Configure your local environment file:
   ```bash
   cp radio-dongle/local/ncs.env.example radio-dongle/local/ncs.env
   ```
   Edit `radio-dongle/local/ncs.env`:
   ```bash
   NCS_TOOLCHAIN=/opt/nordic/ncs/v2.7.0/toolchain
   NCS_SDK=/opt/nordic/ncs/v2.7.0
   ```

### Option B — Manual (Linux/macOS)
```bash
pip3 install west
mkdir -p ~/ncs && cd ~/ncs
west init -m https://github.com/nrfconnect/sdk-nrf --mr v2.7.0
west update    # ~3 GB
```

### nrfutil

Used to package firmware into a DFU zip and flash the dongle. The repo includes a local copy in `radio-dongle/local/nrfutil-home/` (may not work on all machines). If it doesn't:
```bash
pip install nrfutil
```

### Dongle Bootloader Mode

To flash the dongle it must be in DFU mode:
1. Hold the reset button on the PCA10059
2. While holding, plug into USB
3. Release the button
4. The dongle should enumerate as a DFU device

If it doesn't enter bootloader mode: try a different USB port, preferably USB 2.0.

### ESP-IDF vs Zephyr Concepts

| ESP-IDF / FreeRTOS | Zephyr |
|---|---|
| `xTaskCreate` | `k_thread_create` |
| `vTaskDelay` | `k_sleep` |
| `xSemaphoreCreateBinary` | `k_sem_init` |
| `ESP_LOGI` | `LOG_INF` |
| `idf.py build flash` | `west build && west flash` |
| `sdkconfig` / `menuconfig` | `prj.conf` / `Kconfig` |

---

## Flashing

The flash script handles everything interactively:
```bash
python scripts/flash.py                    # interactive menu
```

Or with flags:
```bash
python scripts/flash.py --robot            # flash ESP32 + open monitor
python scripts/flash.py --dongle           # build + flash nRF52840
python scripts/flash.py --both             # flash both + open monitor
python scripts/flash.py --weapon-calibrate # weapon ESC calibration firmware
python scripts/flash.py --weapon-test      # weapon ESC test firmware
python scripts/flash.py --find-ports       # list detected serial ports
```

For manual `idf.py` use (ESP32):
```bash
source ~/esp/esp-idf/export.sh
cd robot
idf.py -p /dev/cu.usbserial-XXXX flash monitor
```

Press **Ctrl+]** to exit `idf.py monitor`.

See [Build and Flash](firmware/build-and-flash.md) for full build system details.

---

## First Bringup Checklist

Follow in order on a newly assembled robot or after reflashing.

### Phase 1 — Hardware Verification (No Power)

- [ ] nRF24L01+ wired to ESP32 (VCC = 3.3 V, NOT 5 V)
- [ ] Decoupling capacitor (10–100 µF) on nRF24 VCC/GND
- [ ] ESC signal wires: left=GPIO 14, right=GPIO 13, weapon=GPIO 21
- [ ] ESC ground wires connected to ESP32 GND
- [ ] All three BMP280 sensors on their I²C buses
- [ ] Optical encoder on GPIO 15
- [ ] ESP32 powered from 5 V BEC (not from weapon ESC BEC)

### Phase 2 — Weapon ESC Calibration (Once Per New ESC)

```bash
python scripts/flash.py --weapon-calibrate
```
Follow the on-screen prompts. Skip if the ESC was previously calibrated.

### Phase 3 — Flash Robot Firmware

```bash
python scripts/flash.py --robot
```

Expected boot output:
```
I (xxx) MAIN: Initializing motor driver...
I (xxx) MOTOR: MCPWM init OK: 3 motors on group 0
I (xxx) MAIN: Initializing temperature sensors...
I (xxx) TEMP: Temp sensors init OK
I (xxx) MAIN: Initializing encoder...
I (xxx) ENCODER: Encoder init OK: GPIO 15, 20 holes
I (xxx) MAIN: Initializing nRF24...
I (xxx) NRF24: nRF24 configured: channel=40 payload=4 @ 8 MHz SPI
I (xxx) MAIN: STATUS = 0x0E
I (xxx) MAIN: RF_CH = 40 (0x28)
```

`STATUS = 0xFF` → SPI connection to nRF24 is broken. Check wiring.  
`I2C read failed` → BMP280 wiring issue.

### Phase 4 — Flash nRF52840 Dongle

```bash
python scripts/flash.py --dongle
```
Unplug and re-plug after flashing. Verify two serial ports appear.

### Phase 5 — Radio Link Test

```bash
cd driver && python station.py
```
HUD should show `● SERIAL OK`. Dongle LED should blink. In robot serial monitor (with DEBUG logging):
```
D (xxxx) MAIN: RX: L=127 R=127 W=  0 F=  0
```

### Phase 6 — Motor Test (No Drive Belt / No Weapon Disc)

1. Arm in ground station (press `A` or gamepad Start)
2. Left stick forward → left motor spins
3. Right stick forward → right motor spins
4. If swapped, swap `MOTOR_PIN_LEFT_WHEEL` and `MOTOR_PIN_RIGHT_WHEEL` in `motor_driver.h`

### Phase 7 — Weapon Test (No Disc)

1. Arm the robot
2. Press Space / RB → weapon spins to ~3000 RPM idle
3. Hold LShift / RT → weapon targets 5000 RPM attack
4. Press Space / RB → weapon stops
5. Press F / gamepad B → robot enters deep sleep (power cycle to recover)

### Phase 8 — Failsafe Test

Unplug the dongle while the robot is moving. Motors should stop within 500–550 ms. Plug dongle back in, re-arm — robot resumes normally.

### Common Bringup Failures

| Symptom | Likely Cause |
|---|---|
| STATUS = 0xFF | nRF24 not connected or 5 V on VCC |
| No packets in monitor | Channel mismatch, wrong dongle port, or dongle not flashed |
| Motors don't respond | ESC not armed, signal wire disconnected, wrong GPIO |
| Motor spins wrong direction | Swap motor leads or update pin define |
| Sensors return NaN | I²C bus wiring issue |
| Robot stops after 500 ms | Expected — packet timeout working correctly |

---

## Debugging

### Enable Debug Logging (ESP32)

Default log level is INFO. For DEBUG output (packet receive logs, temperature every second):
```bash
cd robot
idf.py menuconfig
# Component config → Log output → Default log verbosity → Debug
idf.py build flash monitor
```

Or add to `robot/sdkconfig.defaults`: `CONFIG_LOG_DEFAULT_LEVEL_DEBUG=y`

### Serial Log Reference

```
I (1234) MAIN: RX: L=127 R=127 W=  0 F=  0   ← packet received, all neutral
D (2000) MAIN: TEMP: L=23.4°C R=24.1°C W=22.8°C  RPM=0
W (5500) MAIN: Packet timeout — stopping motors
W (6000) MAIN: KILLSWITCH — entering deep sleep
```

### nRF24 Status Check

After boot:
```
I (xxx) MAIN: STATUS = 0x0E   ← good: RX idle state
I (xxx) MAIN: RF_CH = 40
```
`STATUS = 0xFF` → SPI broken. Check VCC = 3.3 V and all SPI wires.

### Packet Flow Verification

1. **Is serial link working?** Send a raw packet to the dongle's data port:
   ```bash
   python3 -c "
   import serial
   s = serial.Serial('/dev/cu.usbmodem1203', 115200)
   s.write(b'\x7f\x7f\x00\x00\n')
   s.close()
   "
   ```
   If the robot log shows `RX: L=127 R=127 W=0 F=0`, the link is working.

2. **Is the dongle transmitting?** The dongle LED toggles on every queued ESB packet. No toggle = serial link broken.

3. **Address mismatch?** Verify: dongle uses base `{0x4E, 0x4F, 0x44, 0x45}` + prefix `0x31`; robot uses `{'1','N','O','D','E'}`. Both produce `0x31 0x4E 0x4F 0x44 0x45`.

### Dongle Log Port

The Zephyr log is on the **lower-numbered** CDC ACM port:
```bash
python -m serial.tools.miniterm /dev/cu.usbmodem1201 115200
```
Expected: `ESB TX success` lines when the station is running.

### Gamepad Not Detected

```bash
cd driver && python station.py --calibrate
```
Move all sticks and press all buttons. Note axis numbers and update `driver/config.json`.

### Common Crashes

**Stack overflow:**
```
Guru Meditation Error: Core 0 panic'ed (Stack canary watchpoint triggered on 'task_core0')
```
Increase the stack size in `app_main` for the affected task.

**Watchdog timeout:**
```
task_wdt: Task watchdog got triggered
```
A task is blocked too long — most commonly I²C stuck during `tempsensor_driver_init()`. Power cycle the sensors to clear a stuck I²C bus.
