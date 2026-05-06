# Robot

ESP32 receiver that drives the battlebot over radio.

## Hardware

- ESP32 DevKit
- nRF24L01+ (SPI3: CLK=18, MISO=19, MOSI=23, CSN=5, CE=4, IRQ=27)
- Motor drivers (pins defined in `motor_driver.h`)
- Weapon controller
- Temperature sensor
- Quadrature encoders

## Build & Flash

```bash
cd robot
source ~/esp/esp-idf/export.sh
idf.py -p /dev/cu.usbserial-0001 flash monitor
```

## Radio Config

Receives on the same ESB parameters as the dongle:

| Parameter | Value |
|-----------|-------|
| Mode | PRX (Primary Receiver) |
| Channel | 40 |
| Bitrate | 1 Mbps |
| Address | `1NODE` |
| Payload | 4 bytes |

## Packet Format

```
[0] motor1    (0-255)
[1] motor2    (0-255)
[2] weapon    (0-255)
[3] failsafe  (0-255)
```
