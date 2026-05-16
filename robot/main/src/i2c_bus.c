#include "i2c_bus.h"

#include <stdbool.h>
#include "esp_log.h"

static const char *TAG = "I2C_BUS";
static bool s_installed[I2C_NUM_MAX] = { false };

esp_err_t i2c_bus_init(i2c_port_t port, int sda, int scl, uint32_t freq_hz)
{
    if (port < 0 || port >= I2C_NUM_MAX) return ESP_ERR_INVALID_ARG;
    if (s_installed[port]) return ESP_OK;

    i2c_config_t cfg = {
        .mode             = I2C_MODE_MASTER,
        .sda_io_num       = sda,
        .scl_io_num       = scl,
        .sda_pullup_en    = GPIO_PULLUP_ENABLE,
        .scl_pullup_en    = GPIO_PULLUP_ENABLE,
        .master.clk_speed = freq_hz,
    };

    esp_err_t err = i2c_param_config(port, &cfg);
    if (err != ESP_OK) return err;

    err = i2c_driver_install(port, I2C_MODE_MASTER, 0, 0, 0);
    if (err != ESP_OK) return err;

    s_installed[port] = true;
    ESP_LOGI(TAG, "I2C%d up: SDA=%d SCL=%d @ %lu Hz",
             port, sda, scl, (unsigned long)freq_hz);
    return ESP_OK;
}
