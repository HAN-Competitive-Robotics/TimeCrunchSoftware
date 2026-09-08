# ESP32 Pinout Reference

All GPIO assignments are defined in header files. This table is derived directly from the source code.

## GPIO Assignment Table

| GPIO | Header File | #define | Function | Direction | Notes |
|---|---|---|---|---|---|
| 4 | `nrf24.h` | `NRF24_PIN_CE` | nRF24L01+ Chip Enable | OUT | Active HIGH  enables RX mode |
| 5 | `nrf24.h` | `NRF24_PIN_CSN` | nRF24L01+ SPI CS | OUT | Active LOW  manual toggle in driver |
| 12 | `motor_driver.h` | `MOTOR_PIN_LEFT_WHEEL` | Left wheel ESC PWM | OUT | MCPWM group 0. **Strapping pin** — see note below |
| 13 | `motor_driver.h` | `MOTOR_PIN_RIGHT_WHEEL` | Right wheel ESC PWM | OUT | MCPWM group 0 |
| 15 | `encoder_driver.h` | `ENCODER_GPIO` | Weapon Hall encoder | IN | PCNT, both-edge count, pull-up enabled |
| 18 | `nrf24.h` | `NRF24_PIN_CLK` | SPI clock | OUT | SPI3_HOST (VSPI), 8 MHz |
| 19 | `nrf24.h` | `NRF24_PIN_MISO` | SPI MISO | IN | SPI3_HOST (VSPI) |
| 21 | `motor_driver.h` | `MOTOR_PIN_WEAPON` | Weapon ESC PWM | OUT | MCPWM group 0 |
| 22 | `i2c_bus.h` | `I2C0_DEFAULT_SCL` | I²C bus 0 clock | OUT | BMP280 @0x76 and @0x77 + INA3221 @0x40, 400 kHz |
| 23 | `nrf24.h` | `NRF24_PIN_MOSI` | SPI MOSI | OUT | SPI3_HOST (VSPI) |
| 25 | `tempsensor_driver.h` | `TEMP_I2C1_SDA` | I²C bus 1 data | BIDIR | BMP280 @0x76, 400 kHz |
| 26 | `tempsensor_driver.h` | `TEMP_I2C1_SCL` | I²C bus 1 clock | OUT | 400 kHz |
| 27 | `nrf24.h` | `NRF24_PIN_IRQ` | nRF24L01+ interrupt | IN | Active LOW, GPIO_INTR_NEGEDGE, pull-up |
| 33 | `i2c_bus.h` | `I2C0_DEFAULT_SDA` | I²C bus 0 data | BIDIR | BMP280 @0x76 and @0x77 + INA3221 @0x40, 400 kHz |

---

## GPIO 12 is a strapping pin

The left wheel ESC now sits on GPIO 12, which is MTDI. Its level at reset
selects the flash voltage: held high at boot, the ESP32 configures VDD_SDIO
for 1.8 V flash and will not start on a 3.3 V module. The symptom is a board
that refuses to boot with the ESC connected but boots fine with it unplugged.

Most ESC signal inputs are high-impedance and idle low, which is why this
usually works. If the robot ever fails to boot with the ESC attached, this is
the first thing to check.

## Available GPIOs

The following ESP32 GPIOs are **not used** by the current firmware and are available for expansion:

| GPIO | ESP32 notes |
|---|---|
| 0 | Boot strapping pin  avoid using as output |
| 2 | Boot strapping pin  avoid using as output |
| 14 | Generally safe |
| 16 | Generally safe |
| 17 | Generally safe |
| 32 | Input only (no internal pull-up/down on some boards) |
| 34 | Input only |
| 35 | Input only |
| 36 | Input only (VP) |
| 39 | Input only (VN) |

GPIOs 34–39 are input-only (no output capability, no internal pull resistors)  suitable for additional sensor inputs.

---

## How to Change a Pin Assignment

1. Locate the `#define` in the relevant header file
2. Change the value to the new GPIO number
3. Recompile and flash
4. Update this document

There is no dynamic GPIO configuration  all assignments are compile-time constants.

**Example:** Move the encoder to GPIO 16:
```c
// In robot/main/include/encoder_driver.h:
#define ENCODER_GPIO  16   // was 15
```

---

## See Also

- [Architecture](../architecture.md)
- [Wiring](wiring.md)
