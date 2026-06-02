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

> **Critical:** The nRF24L01+ module operates at 3.3 V. Connecting VCC to the 5 V pin on the ESP32 DevKit is not good for the module. Most ESP32 DevKit boards label both a 3V3 and a VIN/5V pin.

**Decoupling capacitor (optional):** Place a 10–100 µF electrolytic capacitor between the nRF24 module's VCC and GND pins, physically as close to the module as possible. This suppresses the voltage spikes caused by the radio's transmit current draw (~11 mA peak) and prevents RF instability.

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

**Ground reference:** The ESP32 GND must be connected to the ESC signal ground. Without a common ground, the PWM signal voltage reference is floating and the ESC will not respond correctly. If the ESC has a BEC (Battery Eliminator Circuit) providing 5 V on its red wire, do not connect that 5 V to the ESP32  connect only signal and ground.

---

## BMP280 Temperature Sensor Connections

### I²C Bus 0 (Left and Right Wheel Sensors)

```
BMP280 (left wheel sensor)       ESP32
──────────────────────────────────────
VCC   →  3V3
GND   →  GND
SDA   →  GPIO 22
SCL   →  GPIO 33
SDO   →  GND              (I²C address 0x76)
CSB   →  VCC              (selects I²C mode)

BMP280 (right wheel sensor)      ESP32
──────────────────────────────────────
VCC   →  3V3
GND   →  GND
SDA   →  GPIO 22          (same SDA line)
SCL   →  GPIO 33          (same SCL line)
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

**SDO pin:** This pin determines the I²C address. SDO=GND → address 0x76, SDO=VCC → 0x77. On the bus 0 left/right pair, one sensor must be 0x76 and the other 0x77  they cannot both share the same address.

**Pull-ups:** The firmware enables ESP32 internal pull-ups on all I²C SDA and SCL pins. For short wiring runs (< 30 cm) this is sufficient. For longer runs or noisy environments, add external 4.7 kΩ pull-ups to 3.3 V.

---

## Optical Encoder Connection

```
Encoder photointerrupter module    ESP32
───────────────────────────────────────
VCC     →  3V3 or 5V (check module)
GND     →  GND
Signal  →  GPIO 15
```

The encoder module produces a digital HIGH/LOW signal as encoder holes pass through. The firmware configures PCNT to count rising edges. The signal should be clean and digital (0 / 3.3 V).

**If the encoder module outputs 5 V logic:** Use a voltage divider (10 kΩ / 22 kΩ) or level shifter to bring the signal down to 3.3 V before connecting to GPIO 15. The ESP32's maximum input voltage on GPIO pins is 3.3 V + 0.3 V tolerance.

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
