#pragma once

#include <stdint.h>

// I2C bus 0 hosts the left/right wheel sensors (0x76, 0x77) on the default
// ESP32 IO_MUX pins  see I2C0_DEFAULT_SDA / I2C0_DEFAULT_SCL in i2c_bus.h.
// Bus 0 is shared with the INA3221 power monitor (power_sensor_driver).

// I2C bus 1 pins  weapon sensor (address 0x76)
#define TEMP_I2C1_SDA 25
#define TEMP_I2C1_SCL 26

typedef enum
{
    TEMP_LEFT_WHEEL,
    TEMP_RIGHT_WHEEL,
    TEMP_WEAPON,
    TEMP_COUNT,
} temp_sensor_t;

// Initialize both I2C buses and all three BMP280 sensors.
// Must be called before temp_get_temperature.
void tempsensor_driver_init(void);

// Read temperature in Celsius. Returns NAN on error.
float temp_get_temperature(temp_sensor_t sensor);
