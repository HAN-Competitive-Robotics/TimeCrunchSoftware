#pragma once

/* Set to 1 to enable BMP280 thermal safety (per-motor cutoff at 100 °C and
 * system deep-sleep at 90 °C).  Set to 0 if temperature sensors are not
 * installed — tempsensor_driver_init() will not be called and task_thermal
 * will not be created. */
#define THERMAL_PROTECTION_ENABLED 1

/* Byte length of every over-the-air packet.  Must match nrf24_basic_config()
 * call in task_radio and the driver station's _hex_packet() encoding:
 *   byte 0 = left motor   (0–255, center 127)
 *   byte 1 = right motor  (0–255, center 127)
 *   byte 2 = weapon       (127=safe, 160=idle fwd, 255=attack fwd, 95=idle rev)
 *   byte 3 = failsafe     (0=normal, >127=hard killswitch) */
#define BATTLEBOT_PAYLOAD_LEN 4
