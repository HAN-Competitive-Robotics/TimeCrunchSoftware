#include "power_sensor_driver.h"
#include "i2c_bus.h"

#include <math.h>
#include <stdbool.h>
#include "driver/i2c.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_log.h"

#define I2C_PORT         I2C_NUM_0
#define I2C_TIMEOUT_MS   10

// INA3221 register map (TI INA3221 datasheet, table 8-2)
#define INA3221_REG_CONFIG     0x00
#define INA3221_REG_SHUNT(ch)  (0x01 + ((ch) * 2))   // ch = 0..2  → 0x01/0x03/0x05
#define INA3221_REG_BUS(ch)    (0x02 + ((ch) * 2))   // ch = 0..2  → 0x02/0x04/0x06
#define INA3221_REG_MFG_ID     0xFE
#define INA3221_REG_DIE_ID     0xFF

#define INA3221_MFG_ID  0x5449
#define INA3221_DIE_ID  0x3220

// Configuration register: all 3 channels enabled, 64-sample averaging,
// 1.1 ms bus and shunt conversion times, continuous shunt+bus mode.
//   bit 15      RST   = 0
//   bits 14:12  CH1/CH2/CH3 enable = 111
//   bits 11:9   AVG   = 011 (64 samples)
//   bits  8:6   VBUSCT = 100 (1.1 ms)
//   bits  5:3   VSHCT  = 100 (1.1 ms)
//   bits  2:0   MODE   = 111 (continuous shunt + bus, all channels)
#define INA3221_CFG_VAL  0x7727

// The shunt and bus voltage registers hold a 13-bit signed value left-
// aligned in 16 bits (lower 3 bits reserved/0). Treating the whole 16-bit
// word as int16 and scaling once collapses the >>3 and the LSB step into
// a single multiplication:
//   bus:   raw * 8 mV / 8  = raw * 1 mV
//   shunt: raw * 40 µV / 8 = raw * 5 µV
#define BUS_LSB_V        1.0e-3f
#define SHUNT_LSB_V      5.0e-6f

// Bensel INA3221 breakout fits 0.100 Ω shunts on all three channels.
#define SHUNT_OHMS       0.100f

// Any active channel reads the same battery rail when all three channel
// inputs share a common V+. Channel 1 = POWER_LEFT_WHEEL.
#define VOLTAGE_CHANNEL  0

static const char *TAG = "POWER";
static bool s_ready = false;

static esp_err_t ina3221_write_reg(uint8_t reg, uint16_t value)
{
    uint8_t buf[3] = { reg, (uint8_t)(value >> 8), (uint8_t)(value & 0xFF) };
    return i2c_master_write_to_device(I2C_PORT, POWER_I2C_ADDR,
                                      buf, sizeof(buf),
                                      pdMS_TO_TICKS(I2C_TIMEOUT_MS));
}

static esp_err_t ina3221_read_reg(uint8_t reg, uint16_t *value)
{
    uint8_t raw[2];
    esp_err_t err = i2c_master_write_read_device(I2C_PORT, POWER_I2C_ADDR,
                                                 &reg, 1, raw, sizeof(raw),
                                                 pdMS_TO_TICKS(I2C_TIMEOUT_MS));
    if (err != ESP_OK) return err;
    *value = ((uint16_t)raw[0] << 8) | raw[1];
    return ESP_OK;
}

void power_sensor_driver_init(void)
{
    ESP_ERROR_CHECK(i2c_bus_init(I2C_PORT, I2C0_DEFAULT_SDA, I2C0_DEFAULT_SCL,
                                 I2C_BUS_DEFAULT_FREQ_HZ));

    uint16_t mfg = 0, die = 0;
    if (ina3221_read_reg(INA3221_REG_MFG_ID, &mfg) != ESP_OK ||
        ina3221_read_reg(INA3221_REG_DIE_ID, &die) != ESP_OK) {
        ESP_LOGW(TAG, "INA3221 not responding at 0x%02X on I2C bus %d",
                 POWER_I2C_ADDR, I2C_PORT);
        return;
    }
    if (mfg != INA3221_MFG_ID || die != INA3221_DIE_ID) {
        ESP_LOGW(TAG, "INA3221 ID mismatch: MFG=0x%04X DIE=0x%04X",
                 mfg, die);
        return;
    }

    if (ina3221_write_reg(INA3221_REG_CONFIG, INA3221_CFG_VAL) != ESP_OK) {
        ESP_LOGW(TAG, "INA3221 config write failed");
        return;
    }

    s_ready = true;
    ESP_LOGI(TAG, "INA3221 init OK at 0x%02X", POWER_I2C_ADDR);
}

float power_sensor_get_voltage(void)
{
    if (!s_ready) return NAN;

    uint16_t raw;
    if (ina3221_read_reg(INA3221_REG_BUS(VOLTAGE_CHANNEL), &raw) != ESP_OK) {
        return NAN;
    }
    return (float)(int16_t)raw * BUS_LSB_V;
}

float power_sensor_get_current(power_channel_t channel)
{
    if (!s_ready || channel >= POWER_COUNT) return NAN;

    uint16_t raw;
    if (ina3221_read_reg(INA3221_REG_SHUNT(channel), &raw) != ESP_OK) {
        return NAN;
    }
    float v_shunt = (float)(int16_t)raw * SHUNT_LSB_V;
    return v_shunt / SHUNT_OHMS;
}
