# Wiring Guide

## nRF24L01+ Module to ESP32

```
nRF24L01+ 8-pin module      ESP32 DevKit
─────────────────────────────────────────
Pin 1: GND          →       GND
Pin 2: VCC (3.3V)   →       3V3  (NOT 5V!)
Pin 3: CE           →       GPIO 4
Pin 4: CSN          →       GPIO 5
Pin 5: SCK          →       GPIO 18
Pin 6: MOSI         →       GPIO 23
Pin 7: MISO         →       GPIO 19
Pin 8: IRQ          →       GPIO 27
```

> **Critical:** The nRF24L01+ module operates at 3.3 V. Connecting VCC to the 5 V pin on the ESP32 DevKit will destroy the module immediately. Most ESP32 DevKit boards label both a 3V3 and a VIN/5V pin.

**Decoupling capacitor (recommended):** Place a 10–100 µF electrolytic capacitor between the nRF24 module's VCC and GND pins, physically as close to the module as possible. This suppresses the voltage spikes caused by the radio's transmit current draw (~11 mA peak) and prevents RF instability.

---

## ESC Connections

Each ESC has three connections: power, ground, and signal.

```
Left wheel ESC:
  Signal    →  GPIO 14
  GND       →  ESP32 GND (signal ground reference)
  Power     →  Battery (via power distribution)

Right wheel ESC:
  Signal    →  GPIO 13
  GND       →  ESP32 GND
  Power     →  Battery

Weapon ESC:
  Signal    →  GPIO 21
  GND       →  ESP32 GND
  Power     →  Battery
```

**Signal level:** ESP32 GPIO outputs are 3.3 V. All standard RC ESCs accept 3.3 V signal levels (they use a comparator input, not a logic gate). No level shifter is required.

**Ground reference:** The ESP32 GND must be connected to the ESC signal ground. Without a common ground, the PWM signal voltage reference is floating and the ESC will not respond correctly. If the ESC has a BEC (Battery Eliminator Circuit) providing 5 V on its red wire, do not connect that 5 V to the ESP32 connect only signal and ground.

---

## BMP280 Temperature Sensor Connections

### I²C Bus 0 (Left and Right Wheel Sensors)

```
BMP280 (left wheel sensor)       ESP32
──────────────────────────────────────
VCC   →  3V3
GND   →  GND
SDA   →  GPIO 33
SCL   →  GPIO 22
SDO   →  GND              (I²C address 0x76)
CSB   →  VCC              (selects I²C mode)

BMP280 (right wheel sensor)      ESP32
──────────────────────────────────────
VCC   →  3V3
GND   →  GND
SDA   →  GPIO 33          (same SDA line)
SCL   →  GPIO 22          (same SCL line)
SDO   →  VCC              (I²C address 0x77)
CSB   →  VCC
```

### I²C Bus 1 (Weapon Motor Sensor)

```
BMP280 (weapon sensor)           ESP32
──────────────────────────────────────
VCC   →  3V3
GND   →  GND
SDA   →  GPIO 25
SCL   →  GPIO 26
SDO   →  GND              (I²C address 0x76)
CSB   →  VCC
```

**SDO pin:** This pin determines the I²C address. SDO=GND → address 0x76, SDO=VCC → 0x77. On the bus 0 left/right pair, one sensor must be 0x76 and the other 0x77 they cannot both share the same address.

**Pull-ups:** The firmware enables ESP32 internal pull-ups on all I²C SDA and SCL pins. For short wiring runs (< 30 cm) this is sufficient. For longer runs or noisy environments, add external 4.7 kΩ pull-ups to 3.3 V.

---

## Hall Sensor Connection

The weapon RPM sensor is an **RS PRO 289-2088** bipolar Hall latch with an NPN open-collector output.

```
RS PRO 289-2088 Hall latch       ESP32 / Power
──────────────────────────────────────────────
Red    (supply, V+)  →  External +V (up to 24 V), NOT the ESP32 pin
Black  (GND)         →  Common GND (shared with ESP32)
White  (output)      →  GPIO 15
```

The output is open-collector: it only sinks to GND and never sources voltage. A pull-up to 3.3 V is required, and the firmware enables the ESP32 internal pull-up on GPIO 15 — no external pull-up is needed for short runs. Because the output only pulls the line down to GND (never up to the sensor's supply voltage), the 3.3 V GPIO sees a clean 0 / 3.3 V signal regardless of the sensor supply voltage. **No level shifter or voltage divider is required**, even when the sensor is powered from a higher voltage rail.

> **Critical:** Connect the sensor's red (V+) wire to its own supply rail only — never to a GPIO pin. The ESP32 pin connects to the white output wire alone. Connecting V+ to the ESP32 would expose the GPIO to the full supply voltage.

The latch toggles its output on each magnetic pole transition. The firmware configures PCNT to count **both edges** (rising and falling). With one diametrically magnetised magnet on the weapon shaft (one N-face + one S-face per turn), this gives 2 counts per revolution (`ENCODER_PULSES_PER_REV = 2`). Adjust the firmware constant to match the actual pole count mounted on the rotor.

---

## Power Distribution

```
Battle pack / LiPo  →  Power distribution board
                            ├─►  Drive ESCs (left, right)
                            ├─►  Weapon ESC
                            └─►  ESP32 power input

ESP32 VIN          ←  5V BEC from drive ESC (or separate 5V UBEC)
ESP32 3V3 (output) →  nRF24L01+ VCC, BMP280 VCC
```

> **Do not power the ESP32 from the weapon ESC BEC** unless you are certain the weapon ESC has a high-current, stable BEC output. Weapon motor stall events can cause voltage transients on an inadequate BEC. Use a separate UBEC (Universal Battery Eliminator Circuit) for the ESP32 if in doubt.

---

## See Also

- [Pinout](pinout.md)
- [Architecture](../architecture.md)
