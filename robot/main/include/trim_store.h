#pragma once

#include <stdint.h>
#include "esp_err.h"

/* Per-side motor trim, persisted on the robot rather than the driver laptop.
 *
 * Trim describes the robot (motor and ESC mismatch), not the operator, so it
 * belongs with the robot. Storing it here means swapping laptops mid-event
 * does not lose the tuning.
 *
 * Units are motor bytes, matching the wire format: the value is added to the
 * incoming 0-255 throttle byte before it is mapped to a throttle percentage.
 */
typedef struct {
    int8_t left;
    int8_t right;
} motor_trim_t;

/* Reads the saved trim from NVS. Missing or unreadable values come back as
 * zero, which is the same as untrimmed, so a first boot needs no special
 * handling. Safe to call before any trim command arrives. */
esp_err_t trim_store_init(void);

motor_trim_t trim_store_get(void);

/* Applies the new trim immediately and writes it to NVS. Only called from a
 * received trim command, never per packet: flash has finite write cycles. */
esp_err_t trim_store_set(int8_t left, int8_t right);

/* Adds trim to a raw throttle byte, saturating instead of wrapping. Wrapping
 * here would turn a small trim into full reverse. */
uint8_t trim_apply(uint8_t raw, int8_t trim);
