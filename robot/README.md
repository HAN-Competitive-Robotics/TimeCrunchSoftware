# Robot

ESP32 receiver that drives the battlebot over radio.

## Hardware

- **ESP32 DevKit**
- **nRF24L01+** 2.4 GHz radio (SPI3)
- **Motor drivers**  3× RC-style ESCs (left wheel, right wheel, weapon)
- **BMP280 temperature sensors**  3× (one per motor)
- **Optical encoder**  20-hole wheel on weapon motor

## Pinout

### nRF24L01+ (SPI3)

| Signal | GPIO |
|--------|------|
| CLK    | 18   |
| MISO   | 19   |
| MOSI   | 23   |
| CSN    | 5    |
| CE     | 4    |
| IRQ    | 27   |

### Motors (MCPWM, 50 Hz servo PWM)

| Motor | GPIO |
|-------|------|
| Right wheel | 13 |
| Left wheel  | 14 |
| Weapon      | 21 |

### I2C (BMP280 temperature sensors)

| Bus | SDA | SCL | Devices |
|-----|-----|-----|---------|
| I2C_NUM_0 | 22 | 33 | Left wheel (0x76), Right wheel (0x77) |
| I2C_NUM_1 | 25 | 26 | Weapon (0x76) |

### Encoder

| Signal | GPIO |
|--------|------|
| Optical sensor | 15 |

## Build & Flash

```bash
cd robot
source ~/esp/esp-idf/export.sh
idf.py -p /dev/cu.usbserial-0001 flash monitor
```

Or auto-detect the port:

```bash
source ~/esp/esp-idf/export.sh
idf.py -p $(python ../scripts/find-ports.py | grep FIRST_ESP32 | cut -d= -f2) flash monitor
```

## Radio Config

Receives on the same ESB parameters as the dongle:

| Parameter | Value |
|-----------|-------|
| Mode | PRX (Primary Receiver) |
| Channel | 40 |
| Bitrate | 2 Mbps |
| Address | `1NODE` |
| Payload | 4 bytes |
| CRC | 2 bytes |

## Packet Format

```
[0] motor_left   (0-255, 127 = center)
[1] motor_right  (0-255, 127 = center)
[2] weapon       (0 = off, 1-127 = idle, 128-255 = attack)
[3] failsafe     (0 = normal, 255 = emergency stop)
```

## Safety Behaviors

1. **Packet timeout (500 ms)**  If no valid packet is received for 500 ms, all motors are stopped.
2. **Failsafe trigger**  When `failsafe > 127`, all motors stop immediately.
3. **Thermal cutoff**  If any motor temperature exceeds 100 °C, or if a temperature sensor fails (returns NAN), that motor's throttle is set to 0.
4. **Weapon PI control**  The weapon motor runs closed-loop to a target of 5000 RPM. Tune `WEAPON_KP` and `WEAPON_KI` in `main/include/weapon_controller.h` after a step-response test.

## Tasks

| Task | Core | Priority | Rate | Purpose |
|------|------|----------|------|---------|
| `task_core0` | 0 | 3 | Event-driven (IRQ) | Radio receive, drive motor control, failsafe |
| `task_core1` | 1 | 2 | 100 Hz | Weapon PI controller, thermal safety (1 Hz) |

### Why this split?

- **Core 0** waits on the nRF24 IRQ pin (GPIO 27) instead of polling, so packet latency drops from worst-case ~50 ms to microseconds.
- **Core 1** runs the weapon PID at a fixed 100 Hz with no jitter from SPI / I2C / radio, giving stable closed-loop control. Temperature checks are decoupled to 1 Hz so an I2C timeout never stalls the PID loop.
- A single-item FreeRTOS queue (`state_queue`) passes throttle / arm / failsafe flags from Core 0 to Core 1. The overhead is negligible.

## Tuning the Weapon Controller

1. Set `WEAPON_KP` and `WEAPON_KI` to `0.0f` in `main/include/weapon_controller.h`
2. Flash and run with the weapon spinning open-loop
3. Log `encoder_get_rpm()` values to determine system response
4. Tune `WEAPON_KP` first for responsiveness, then add `WEAPON_KI` to eliminate steady-state error
5. Re-flash and verify no oscillation
