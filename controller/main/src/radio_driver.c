#include "radio_driver.h"

#include <string.h>

#include "esp_rom_sys.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

/* Commands */
#define CMD_R_REGISTER 0x00
#define CMD_W_REGISTER 0x20
#define CMD_R_RX_PAYLOAD 0x61
#define CMD_FLUSH_RX 0xE2
#define CMD_NOP 0xFF

/* Registers */
#define REG_CONFIG 0x00
#define REG_EN_AA 0x01
#define REG_EN_RXADDR 0x02
#define REG_SETUP_AW 0x03
#define REG_RF_CH 0x05
#define REG_RF_SETUP 0x06
#define REG_STATUS 0x07
#define REG_RX_ADDR_P0 0x0A
#define REG_RX_PW_P0 0x11
#define REG_FIFO_STATUS 0x17

/* Bits */
#define CONFIG_EN_CRC (1 << 3)
#define CONFIG_CRCO (1 << 2)
#define CONFIG_PWR_UP (1 << 1)
#define CONFIG_PRIM_RX (1 << 0)

#define STATUS_RX_DR (1 << 6)

#define FIFO_RX_EMPTY (1 << 0)

static inline void ce_low(nrf24_t *dev)
{
    gpio_set_level(dev->ce_pin, 0);
}

static inline void ce_high(nrf24_t *dev)
{
    gpio_set_level(dev->ce_pin, 1);
}

static esp_err_t spi_xfer(nrf24_t *dev, const uint8_t *tx, uint8_t *rx, size_t len)
{
    spi_transaction_t t = {
        .length = len * 8,
        .tx_buffer = tx,
        .rx_buffer = rx,
    };
    return spi_device_transmit(dev->spi, &t);
}

static esp_err_t reg_write(nrf24_t *dev, uint8_t reg, uint8_t value)
{
    uint8_t tx[2] = {(uint8_t)(CMD_W_REGISTER | (reg & 0x1F)), value};
    uint8_t rx[2];
    return spi_xfer(dev, tx, rx, sizeof(tx));
}

static esp_err_t reg_read(nrf24_t *dev, uint8_t reg, uint8_t *value)
{
    uint8_t tx[2] = {(uint8_t)(CMD_R_REGISTER | (reg & 0x1F)), CMD_NOP};
    uint8_t rx[2];
    esp_err_t err = spi_xfer(dev, tx, rx, sizeof(tx));
    if (err != ESP_OK)
        return err;
    *value = rx[1];
    return ESP_OK;
}

static esp_err_t reg_write_buf(nrf24_t *dev, uint8_t reg, const uint8_t *buf, size_t len)
{
    uint8_t tx[1 + NRF24_ADDR_LEN];
    uint8_t rx[1 + NRF24_ADDR_LEN];

    tx[0] = CMD_W_REGISTER | (reg & 0x1F);
    memcpy(&tx[1], buf, len);

    return spi_xfer(dev, tx, rx, len + 1);
}

static esp_err_t cmd_simple(nrf24_t *dev, uint8_t cmd)
{
    uint8_t tx[1] = {cmd};
    uint8_t rx[1];
    return spi_xfer(dev, tx, rx, 1);
}

esp_err_t nrf24_flush_rx(nrf24_t *dev)
{
    return cmd_simple(dev, CMD_FLUSH_RX);
}

esp_err_t nrf24_init(nrf24_t *dev, const nrf24_config_t *cfg)
{
    if (!dev || !cfg)
        return ESP_ERR_INVALID_ARG;
    if (cfg->payload_size <= 0 || cfg->payload_size > NRF24_PAYLOAD_SIZE)
        return ESP_ERR_INVALID_ARG;

    memset(dev, 0, sizeof(*dev));
    dev->ce_pin = cfg->ce_pin;
    dev->payload_size = cfg->payload_size;

    spi_bus_config_t buscfg = {
        .mosi_io_num = cfg->mosi_pin,
        .miso_io_num = cfg->miso_pin,
        .sclk_io_num = cfg->sck_pin,
        .quadwp_io_num = -1,
        .quadhd_io_num = -1,
        .max_transfer_sz = 64,
    };

    spi_device_interface_config_t devcfg = {
        .clock_speed_hz = cfg->spi_clock_hz > 0 ? cfg->spi_clock_hz : 8000000,
        .mode = 0,
        .spics_io_num = cfg->cs_pin,
        .queue_size = 1,
    };

    esp_err_t err = spi_bus_initialize(cfg->spi_host, &buscfg, SPI_DMA_CH_AUTO);
    if (err != ESP_OK && err != ESP_ERR_INVALID_STATE)
    {
        return err;
    }

    err = spi_bus_add_device(cfg->spi_host, &devcfg, &dev->spi);
    if (err != ESP_OK)
        return err;

    gpio_config_t io = {
        .pin_bit_mask = 1ULL << cfg->ce_pin,
        .mode = GPIO_MODE_OUTPUT,
    };
    err = gpio_config(&io);
    if (err != ESP_OK)
        return err;

    ce_low(dev);

    /* Basic nRF24 setup for fixed payload RX */
    err = reg_write(dev, REG_SETUP_AW, 0x03); /* 5-byte address */
    if (err != ESP_OK)
        return err;

    err = reg_write_buf(dev, REG_RX_ADDR_P0, cfg->rx_addr, NRF24_ADDR_LEN);
    if (err != ESP_OK)
        return err;

    err = reg_write(dev, REG_RX_PW_P0, cfg->payload_size); /* fixed payload size */
    if (err != ESP_OK)
        return err;

    err = reg_write(dev, REG_RF_CH, cfg->channel);
    if (err != ESP_OK)
        return err;

    err = reg_write(dev, REG_RF_SETUP, 0x06); /* 1 Mbps, 0 dBm */
    if (err != ESP_OK)
        return err;

    err = reg_write(dev, REG_EN_AA, 0x00); /* disable auto-ack */
    if (err != ESP_OK)
        return err;

    err = reg_write(dev, REG_EN_RXADDR, 0x01); /* enable pipe 0 */
    if (err != ESP_OK)
        return err;

    err = reg_write(dev, REG_STATUS, 0x70); /* clear IRQ flags */
    if (err != ESP_OK)
        return err;

    err = nrf24_flush_rx(dev);
    if (err != ESP_OK)
        return err;

    err = reg_write(dev, REG_CONFIG,
                    CONFIG_EN_CRC | CONFIG_CRCO | CONFIG_PWR_UP | CONFIG_PRIM_RX);
    if (err != ESP_OK)
        return err;

    vTaskDelay(pdMS_TO_TICKS(5));
    ce_high(dev);

    return ESP_OK;
}

esp_err_t nrf24_start_listening(nrf24_t *dev)
{
    if (!dev)
        return ESP_ERR_INVALID_ARG;
    ce_high(dev);
    esp_rom_delay_us(150);
    return ESP_OK;
}

esp_err_t nrf24_available(nrf24_t *dev, bool *available)
{
    if (!dev || !available)
        return ESP_ERR_INVALID_ARG;

    uint8_t fifo = 0;
    esp_err_t err = reg_read(dev, REG_FIFO_STATUS, &fifo);
    if (err != ESP_OK)
        return err;

    *available = ((fifo & FIFO_RX_EMPTY) == 0);
    return ESP_OK;
}

esp_err_t nrf24_read(nrf24_t *dev, void *data, size_t len)
{
    if (!dev || !data)
        return ESP_ERR_INVALID_ARG;
    if (len < dev->payload_size)
        return ESP_ERR_INVALID_SIZE;

    uint8_t tx[1 + NRF24_PAYLOAD_SIZE];
    uint8_t rx[1 + NRF24_PAYLOAD_SIZE];

    tx[0] = CMD_R_RX_PAYLOAD;
    memset(&tx[1], CMD_NOP, dev->payload_size);

    esp_err_t err = spi_xfer(dev, tx, rx, dev->payload_size + 1);
    if (err != ESP_OK)
        return err;

    memcpy(data, &rx[1], dev->payload_size);

    /* clear RX_DR */
    return reg_write(dev, REG_STATUS, STATUS_RX_DR);
}