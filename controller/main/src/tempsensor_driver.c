#include "tempsensor_driver.h"

#include <math.h>
#include "driver/i2c.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

#define I2C_FREQ_HZ     400000
#define I2C_TIMEOUT_MS  10

// BMP280 registers
#define BMP280_REG_CALIB     0x88
#define BMP280_REG_CHIP_ID   0xD0
#define BMP280_REG_CONFIG    0xF5
#define BMP280_REG_CTRL_MEAS 0xF4
#define BMP280_REG_TEMP_MSB  0xFA

#define BMP280_CHIP_ID  0x60

// ctrl_meas: osrs_t=x1 (001), osrs_p=skip (000), mode=normal (11) → 0x23
#define BMP280_CTRL_VAL 0x23

typedef struct {
    uint16_t dig_T1;
    int16_t  dig_T2;
    int16_t  dig_T3;
} bmp280_calib_t;

typedef struct {
    i2c_port_t     bus;
    uint8_t        addr;
    bmp280_calib_t calib;
} sensor_cfg_t;

static sensor_cfg_t s_sensors[TEMP_COUNT] = {
    [TEMP_LEFT_WHEEL]  = { .bus = I2C_NUM_0, .addr = 0x76 },
    [TEMP_RIGHT_WHEEL] = { .bus = I2C_NUM_0, .addr = 0x77 },
    [TEMP_WEAPON]      = { .bus = I2C_NUM_1, .addr = 0x76 },
};

static esp_err_t bmp280_read(sensor_cfg_t *s, uint8_t reg, uint8_t *buf, size_t len)
{
    return i2c_master_write_read_device(s->bus, s->addr, &reg, 1, buf, len,
                                        pdMS_TO_TICKS(I2C_TIMEOUT_MS));
}

static esp_err_t bmp280_write(sensor_cfg_t *s, uint8_t reg, uint8_t val)
{
    uint8_t buf[2] = { reg, val };
    return i2c_master_write_to_device(s->bus, s->addr, buf, sizeof(buf),
                                      pdMS_TO_TICKS(I2C_TIMEOUT_MS));
}

static void init_i2c_bus(i2c_port_t port, int sda, int scl)
{
    i2c_config_t cfg = {
        .mode             = I2C_MODE_MASTER,
        .sda_io_num       = sda,
        .scl_io_num       = scl,
        .sda_pullup_en    = GPIO_PULLUP_ENABLE,
        .scl_pullup_en    = GPIO_PULLUP_ENABLE,
        .master.clk_speed = I2C_FREQ_HZ,
    };
    i2c_param_config(port, &cfg);
    i2c_driver_install(port, I2C_MODE_MASTER, 0, 0, 0);
}

static void init_sensor(sensor_cfg_t *s)
{
    uint8_t chip_id;
    if (bmp280_read(s, BMP280_REG_CHIP_ID, &chip_id, 1) != ESP_OK ||
        chip_id != BMP280_CHIP_ID) {
        return;
    }

    // Read 6 calibration bytes starting at 0x88
    uint8_t raw[6];
    if (bmp280_read(s, BMP280_REG_CALIB, raw, sizeof(raw)) != ESP_OK) {
        return;
    }

    s->calib.dig_T1 = (uint16_t)((raw[1] << 8) | raw[0]);
    s->calib.dig_T2 =  (int16_t)((raw[3] << 8) | raw[2]);
    s->calib.dig_T3 =  (int16_t)((raw[5] << 8) | raw[4]);

    bmp280_write(s, BMP280_REG_CONFIG,    0x00);       // filter off, standby 0.5 ms
    bmp280_write(s, BMP280_REG_CTRL_MEAS, BMP280_CTRL_VAL);

}

void tempsensor_driver_init(void)
{
    init_i2c_bus(I2C_NUM_0, TEMP_I2C0_SDA, TEMP_I2C0_SCL);
    init_i2c_bus(I2C_NUM_1, TEMP_I2C1_SDA, TEMP_I2C1_SCL);

    for (int i = 0; i < TEMP_COUNT; i++) {
        init_sensor(&s_sensors[i]);
    }
}

float temp_get_temperature(temp_sensor_t sensor)
{
    if (sensor >= TEMP_COUNT) return NAN;

    sensor_cfg_t *s = &s_sensors[sensor];

    uint8_t raw[3];
    if (bmp280_read(s, BMP280_REG_TEMP_MSB, raw, sizeof(raw)) != ESP_OK) {
        return NAN;
    }

    int32_t adc_T = ((int32_t)raw[0] << 12) |
                    ((int32_t)raw[1] <<  4) |
                    ((int32_t)raw[2] >>  4);

    // BMP280 compensation formula (from datasheet section 4.2.3)
    bmp280_calib_t *c = &s->calib;
    int32_t var1 = (((adc_T >> 3) - ((int32_t)c->dig_T1 << 1)) * (int32_t)c->dig_T2) >> 11;
    int32_t var2 = (((((adc_T >> 4) - (int32_t)c->dig_T1) *
                       ((adc_T >> 4) - (int32_t)c->dig_T1)) >> 12) *
                     (int32_t)c->dig_T3) >> 14;
    int32_t T = ((var1 + var2) * 5 + 128) >> 8;  // hundredths of °C

    return (float)T / 100.0f;
}
