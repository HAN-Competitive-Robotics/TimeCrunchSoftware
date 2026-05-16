#pragma once

#include <stdint.h>

// INA3221 3-channel high-side current and bus voltage monitor (Bensel module).
// Sits on I2C_NUM_0 (default IO_MUX pins, see i2c_bus.h) — the bus is shared
// with the wheel temperature sensors via i2c_bus_init, so init order does
// not matter. A0 strapped to GND → 7-bit address 0x40.
#define POWER_I2C_ADDR  0x40

// Channel layout matches the temperature sensor mapping: each motor's
// power line is wired through the matching INA3221 channel.
typedef enum {
    POWER_LEFT_WHEEL,   // INA3221 channel 1
    POWER_RIGHT_WHEEL,  // INA3221 channel 2
    POWER_WEAPON,       // INA3221 channel 3
    POWER_COUNT,
} power_channel_t;

// Probe the INA3221, verify IDs and configure it for continuous sampling.
// Must be called AFTER tempsensor_driver_init (which installs the I2C bus).
// On failure the driver stays disabled and subsequent reads return NAN.
void power_sensor_driver_init(void);

// Battery bus voltage in Volts (read from channel 1's bus-voltage register).
// Returns NAN on I2C error or if the driver failed to initialise.
float power_sensor_get_voltage(void);

// High-side current through the given channel's shunt, in Amps.
// Returns NAN on I2C error or if the driver failed to initialise.
float power_sensor_get_current(power_channel_t channel);
