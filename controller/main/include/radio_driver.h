#ifndef RADIO_DRIVER_H
#define RADIO_DRIVER_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#include "driver/gpio.h"
#include "driver/spi_master.h"
#include "esp_err.h"

#define NRF24_PAYLOAD_SIZE 32
#define NRF24_ADDR_LEN 5

typedef struct {
    spi_device_handle_t spi;
    gpio_num_t ce_pin;
    uint8_t payload_size;
} nrf24_t;

typedef struct {
    spi_host_device_t spi_host;
    gpio_num_t mosi_pin;
    gpio_num_t miso_pin;
    gpio_num_t sck_pin;
    gpio_num_t cs_pin;
    gpio_num_t ce_pin;

    int spi_clock_hz;

    uint8_t channel;
    uint8_t payload_size;
    uint8_t rx_addr[NRF24_ADDR_LEN];
} nrf24_config_t;

esp_err_t nrf24_init(nrf24_t *dev, const nrf24_config_t *cfg);
esp_err_t nrf24_start_listening(nrf24_t *dev);
esp_err_t nrf24_available(nrf24_t *dev, bool *available);
esp_err_t nrf24_read(nrf24_t *dev, void *data, size_t len);
esp_err_t nrf24_flush_rx(nrf24_t *dev);

#endif