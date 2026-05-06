#ifndef NRF24_H
#define NRF24_H

#include <stddef.h>
#include <stdint.h>
#include <stdbool.h>

#include "esp_err.h"
#include "driver/spi_master.h"
#include "driver/gpio.h"
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"

#ifdef __cplusplus
extern "C"
{
#endif

// =========================
// Pin configuration
// =========================
#define NRF24_PIN_MISO 19
#define NRF24_PIN_MOSI 23
#define NRF24_PIN_CLK  18
#define NRF24_PIN_CSN   5
#define NRF24_PIN_CE    4
#define NRF24_PIN_IRQ  27

// =========================
// General constants
// =========================
#define NRF24_ADDR_LEN        5
#define NRF24_MAX_PAYLOAD_LEN 32

// =========================
// Commands
// =========================
#define NRF_CMD_R_REGISTER   0x00
#define NRF_CMD_W_REGISTER   0x20
#define NRF_CMD_R_RX_PAYLOAD 0x61
#define NRF_CMD_W_TX_PAYLOAD 0xA0
#define NRF_CMD_FLUSH_TX     0xE1
#define NRF_CMD_FLUSH_RX     0xE2
#define NRF_CMD_NOP          0xFF

// =========================
// Registers
// =========================
#define NRF_REG_CONFIG      0x00
#define NRF_REG_EN_AA       0x01
#define NRF_REG_EN_RXADDR   0x02
#define NRF_REG_SETUP_AW    0x03
#define NRF_REG_SETUP_RETR  0x04
#define NRF_REG_RF_CH       0x05
#define NRF_REG_RF_SETUP    0x06
#define NRF_REG_STATUS      0x07
#define NRF_REG_RX_ADDR_P0  0x0A
#define NRF_REG_TX_ADDR     0x10
#define NRF_REG_RX_PW_P0   0x11
#define NRF_REG_FIFO_STATUS 0x17
#define NRF_REG_DYNPD       0x1C
#define NRF_REG_FEATURE     0x1D

// =========================
// CONFIG bits
// =========================
#define NRF_CONFIG_EN_CRC  (1U << 3)
#define NRF_CONFIG_CRCO    (1U << 2)
#define NRF_CONFIG_PWR_UP  (1U << 1)
#define NRF_CONFIG_PRIM_RX (1U << 0)

// =========================
// STATUS bits
// =========================
#define NRF_STATUS_RX_DR  (1U << 6)
#define NRF_STATUS_TX_DS  (1U << 5)
#define NRF_STATUS_MAX_RT (1U << 4)

// =========================
// FIFO_STATUS bits
// =========================
#define NRF_FIFO_RX_EMPTY (1U << 0)

// =========================
// RF_SETUP helpers
// =========================
#define NRF_RF_SETUP_2MBPS 0x0E

// =========================
// Public state (used by main for ISR sync)
// =========================
extern spi_device_handle_t nrf24_spi;
extern SemaphoreHandle_t   nrf24_irq_sem;

// =========================
// Init
// =========================
esp_err_t nrf24_init(void);
esp_err_t nrf24_init_spi(void);
esp_err_t nrf24_init_gpio(void);
esp_err_t nrf24_init_irq(void);

// =========================
// Low-level helpers
// =========================
esp_err_t nrf24_spi_transfer(const uint8_t *tx, uint8_t *rx, size_t len);
uint8_t   nrf24_get_status(void);
uint8_t   nrf24_read_reg(uint8_t reg);
esp_err_t nrf24_write_reg(uint8_t reg, uint8_t value);

// =========================
// GPIO helpers (CE only — CSN is internal)
// =========================
void nrf24_ce_high(void);
void nrf24_ce_low(void);

// =========================
// IRQ management
// =========================
esp_err_t nrf24_clear_irqs(void);
esp_err_t nrf24_set_channel(uint8_t channel);

// =========================
// Data transfer (RX only)
// =========================
bool      nrf24_data_ready(void);
esp_err_t nrf24_receive_packet(uint8_t *data, size_t len);

// =========================
// Convenience setup
// =========================
esp_err_t nrf24_basic_config(const uint8_t *addr, uint8_t channel, uint8_t payload_len);

#ifdef __cplusplus
}
#endif

#endif // NRF24_H
