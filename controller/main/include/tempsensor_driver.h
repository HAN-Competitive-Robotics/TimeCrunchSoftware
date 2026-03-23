#pragma once

#include <stdint.h>

// I2C bus 0 pins — left and right wheel sensors (addresses 0x76 and 0x77)
#define TEMP_I2C0_SDA  22
#define TEMP_I2C0_SCL  23

// I2C bus 1 pins — weapon sensor (address 0x76)
#define TEMP_I2C1_SDA  25
#define TEMP_I2C1_SCL  26

typedef enum {
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
