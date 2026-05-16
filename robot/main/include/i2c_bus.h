#pragma once

#include "driver/i2c.h"
#include "esp_err.h"

// ESP32 default I2C0 IO_MUX pins (silkscreened on most dev boards).
#define I2C0_DEFAULT_SDA  21
#define I2C0_DEFAULT_SCL  22

#define I2C_BUS_DEFAULT_FREQ_HZ  400000

// Install the I2C master driver on `port` with the given pins and bus
// frequency. Idempotent: the first call configures and installs the bus;
// subsequent calls for the same port return ESP_OK without touching it,
// so multiple device drivers can safely share one I2C bus regardless of
// the order they are initialised.
esp_err_t i2c_bus_init(i2c_port_t port, int sda, int scl, uint32_t freq_hz);
