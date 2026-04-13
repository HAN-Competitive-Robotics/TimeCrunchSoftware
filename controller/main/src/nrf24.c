#include "nrf24.h"

#include <string.h>

#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_log.h"
#include "esp_rom_sys.h"

static const char *TAG = "NRF24";

spi_device_handle_t nrf24_spi = NULL;

void nrf24_ce_high(void)
{
    gpio_set_level(NRF24_PIN_CE, 1);
}

void nrf24_ce_low(void)
{
    gpio_set_level(NRF24_PIN_CE, 0);
}

void nrf24_csn_high(void)
{
    gpio_set_level(NRF24_PIN_CSN, 1);
}

void nrf24_csn_low(void)
{
    gpio_set_level(NRF24_PIN_CSN, 0);
}

static esp_err_t nrf24_write_raw(const uint8_t *tx, uint8_t *rx, size_t len)
{
    if (nrf24_spi == NULL)
    {
        return ESP_ERR_INVALID_STATE;
    }

    spi_transaction_t t = {
        .flags = 0,
        .length = len * 8,
        .tx_buffer = tx,
        .rx_buffer = rx,
    };

    nrf24_csn_low();
    esp_err_t err = spi_device_polling_transmit(nrf24_spi, &t);
    nrf24_csn_high();

    return err;
}

esp_err_t nrf24_spi_transfer(const uint8_t *tx, uint8_t *rx, size_t len)
{
    if (tx == NULL || len == 0)
    {
        return ESP_ERR_INVALID_ARG;
    }

    return nrf24_write_raw(tx, rx, len);
}

esp_err_t nrf24_init_gpio(void)
{
    gpio_config_t ce_cfg = {
        .pin_bit_mask = (1ULL << NRF24_PIN_CE),
        .mode = GPIO_MODE_OUTPUT,
        .pull_up_en = GPIO_PULLUP_DISABLE,
        .pull_down_en = GPIO_PULLDOWN_DISABLE,
        .intr_type = GPIO_INTR_DISABLE,
    };
    ESP_ERROR_CHECK(gpio_config(&ce_cfg));
    nrf24_ce_low();

    gpio_config_t csn_cfg = {
        .pin_bit_mask = (1ULL << NRF24_PIN_CSN),
        .mode = GPIO_MODE_OUTPUT,
        .pull_up_en = GPIO_PULLUP_DISABLE,
        .pull_down_en = GPIO_PULLDOWN_DISABLE,
        .intr_type = GPIO_INTR_DISABLE,
    };
    ESP_ERROR_CHECK(gpio_config(&csn_cfg));
    nrf24_csn_high();

    gpio_config_t irq_cfg = {
        .pin_bit_mask = (1ULL << NRF24_PIN_IRQ),
        .mode = GPIO_MODE_INPUT,
        .pull_up_en = GPIO_PULLUP_ENABLE,
        .pull_down_en = GPIO_PULLDOWN_DISABLE,
        .intr_type = GPIO_INTR_DISABLE,
    };
    ESP_ERROR_CHECK(gpio_config(&irq_cfg));

    return ESP_OK;
}

esp_err_t nrf24_init_spi(void)
{
    spi_bus_config_t buscfg = {
        .mosi_io_num = NRF24_PIN_MOSI,
        .miso_io_num = NRF24_PIN_MISO,
        .sclk_io_num = NRF24_PIN_CLK,
        .quadwp_io_num = -1,
        .quadhd_io_num = -1,
        .max_transfer_sz = 33,
    };

    spi_device_interface_config_t devcfg = {
        .clock_speed_hz = 1000000,
        .mode = 0,
        .spics_io_num = -1,
        .queue_size = 1,
        .flags = 0,
    };

    esp_err_t err = spi_bus_initialize(SPI3_HOST, &buscfg, SPI_DMA_DISABLED);
    if (err != ESP_OK && err != ESP_ERR_INVALID_STATE)
    {
        return err;
    }

    if (nrf24_spi == NULL)
    {
        ESP_ERROR_CHECK(spi_bus_add_device(SPI3_HOST, &devcfg, &nrf24_spi));
    }

    return ESP_OK;
}

esp_err_t nrf24_init(void)
{
    ESP_ERROR_CHECK(nrf24_init_gpio());
    ESP_ERROR_CHECK(nrf24_init_spi());
    return ESP_OK;
}

uint8_t nrf24_get_status(void)
{
    uint8_t tx[1] = {NRF_CMD_NOP};
    uint8_t rx[1] = {0};

    ESP_ERROR_CHECK(nrf24_spi_transfer(tx, rx, sizeof(tx)));
    return rx[0];
}

uint8_t nrf24_read_reg(uint8_t reg)
{
    uint8_t tx[2] = {
        (uint8_t)(NRF_CMD_R_REGISTER | (reg & 0x1F)),
        NRF_CMD_NOP};
    uint8_t rx[2] = {0};

    ESP_ERROR_CHECK(nrf24_spi_transfer(tx, rx, sizeof(tx)));
    return rx[1];
}

esp_err_t nrf24_read_reg_checked(uint8_t reg, uint8_t *value)
{
    if (value == NULL)
    {
        return ESP_ERR_INVALID_ARG;
    }

    uint8_t tx[2] = {
        (uint8_t)(NRF_CMD_R_REGISTER | (reg & 0x1F)),
        NRF_CMD_NOP};
    uint8_t rx[2] = {0};

    esp_err_t err = nrf24_spi_transfer(tx, rx, sizeof(tx));
    if (err != ESP_OK)
    {
        return err;
    }

    *value = rx[1];
    return ESP_OK;
}

esp_err_t nrf24_write_reg(uint8_t reg, uint8_t value)
{
    uint8_t tx[2] = {
        (uint8_t)(NRF_CMD_W_REGISTER | (reg & 0x1F)),
        value};

    return nrf24_spi_transfer(tx, NULL, sizeof(tx));
}

esp_err_t nrf24_read_buf(uint8_t reg, uint8_t *data, size_t len)
{
    if (data == NULL || len == 0 || len > NRF24_MAX_PAYLOAD_LEN)
    {
        return ESP_ERR_INVALID_ARG;
    }

    uint8_t tx[1 + NRF24_MAX_PAYLOAD_LEN] = {0};
    uint8_t rx[1 + NRF24_MAX_PAYLOAD_LEN] = {0};

    tx[0] = (uint8_t)(NRF_CMD_R_REGISTER | (reg & 0x1F));

    ESP_ERROR_CHECK(nrf24_spi_transfer(tx, rx, len + 1));
    memcpy(data, &rx[1], len);

    return ESP_OK;
}

esp_err_t nrf24_write_buf(uint8_t reg, const uint8_t *data, size_t len)
{
    if (data == NULL || len == 0 || len > NRF24_MAX_PAYLOAD_LEN)
    {
        return ESP_ERR_INVALID_ARG;
    }

    uint8_t tx[1 + NRF24_MAX_PAYLOAD_LEN] = {0};
    tx[0] = (uint8_t)(NRF_CMD_W_REGISTER | (reg & 0x1F));
    memcpy(&tx[1], data, len);

    return nrf24_spi_transfer(tx, NULL, len + 1);
}

esp_err_t nrf24_command(uint8_t cmd)
{
    return nrf24_spi_transfer(&cmd, NULL, 1);
}

esp_err_t nrf24_clear_irqs(void)
{
    return nrf24_write_reg(NRF_REG_STATUS,
                           NRF_STATUS_RX_DR | NRF_STATUS_TX_DS | NRF_STATUS_MAX_RT);
}

esp_err_t nrf24_flush_tx(void)
{
    return nrf24_command(NRF_CMD_FLUSH_TX);
}

esp_err_t nrf24_flush_rx(void)
{
    return nrf24_command(NRF_CMD_FLUSH_RX);
}

esp_err_t nrf24_power_up(void)
{
    uint8_t config = nrf24_read_reg(NRF_REG_CONFIG);
    config |= NRF_CONFIG_PWR_UP;
    ESP_ERROR_CHECK(nrf24_write_reg(NRF_REG_CONFIG, config));
    vTaskDelay(pdMS_TO_TICKS(5));
    return ESP_OK;
}

esp_err_t nrf24_power_down(void)
{
    uint8_t config = nrf24_read_reg(NRF_REG_CONFIG);
    config &= (uint8_t)(~NRF_CONFIG_PWR_UP);
    return nrf24_write_reg(NRF_REG_CONFIG, config);
}

esp_err_t nrf24_set_channel(uint8_t channel)
{
    if (channel > 125)
    {
        return ESP_ERR_INVALID_ARG;
    }
    return nrf24_write_reg(NRF_REG_RF_CH, channel);
}

esp_err_t nrf24_set_rf_setup(uint8_t rf_setup)
{
    return nrf24_write_reg(NRF_REG_RF_SETUP, rf_setup);
}

esp_err_t nrf24_set_retries(uint8_t ard, uint8_t arc)
{
    if (ard > 0x0F || arc > 0x0F)
    {
        return ESP_ERR_INVALID_ARG;
    }

    uint8_t value = (uint8_t)((ard << 4) | arc);
    return nrf24_write_reg(NRF_REG_SETUP_RETR, value);
}

esp_err_t nrf24_set_address_width_5bytes(void)
{
    return nrf24_write_reg(NRF_REG_SETUP_AW, 0x03);
}

esp_err_t nrf24_set_tx_address(const uint8_t *addr, size_t len)
{
    if (addr == NULL || len != NRF24_ADDR_LEN)
    {
        return ESP_ERR_INVALID_ARG;
    }
    return nrf24_write_buf(NRF_REG_TX_ADDR, addr, len);
}

esp_err_t nrf24_set_rx_address_p0(const uint8_t *addr, size_t len)
{
    if (addr == NULL || len != NRF24_ADDR_LEN)
    {
        return ESP_ERR_INVALID_ARG;
    }
    return nrf24_write_buf(NRF_REG_RX_ADDR_P0, addr, len);
}

esp_err_t nrf24_set_payload_width_p0(uint8_t width)
{
    if (width > NRF24_MAX_PAYLOAD_LEN)
    {
        return ESP_ERR_INVALID_ARG;
    }
    return nrf24_write_reg(NRF_REG_RX_PW_P0, width);
}

esp_err_t nrf24_set_rx_mode(void)
{
    uint8_t config = nrf24_read_reg(NRF_REG_CONFIG);
    config |= NRF_CONFIG_PRIM_RX;
    config |= NRF_CONFIG_PWR_UP;

    nrf24_ce_low();
    ESP_ERROR_CHECK(nrf24_write_reg(NRF_REG_CONFIG, config));
    vTaskDelay(pdMS_TO_TICKS(5));
    nrf24_ce_high();

    return ESP_OK;
}

esp_err_t nrf24_set_tx_mode(void)
{
    uint8_t config = nrf24_read_reg(NRF_REG_CONFIG);
    config &= (uint8_t)(~NRF_CONFIG_PRIM_RX);
    config |= NRF_CONFIG_PWR_UP;

    nrf24_ce_low();
    ESP_ERROR_CHECK(nrf24_write_reg(NRF_REG_CONFIG, config));
    vTaskDelay(pdMS_TO_TICKS(5));

    return ESP_OK;
}

esp_err_t nrf24_write_tx_payload(const uint8_t *data, size_t len)
{
    if (data == NULL || len == 0 || len > NRF24_MAX_PAYLOAD_LEN)
    {
        return ESP_ERR_INVALID_ARG;
    }

    uint8_t tx[1 + NRF24_MAX_PAYLOAD_LEN] = {0};
    tx[0] = NRF_CMD_W_TX_PAYLOAD;
    memcpy(&tx[1], data, len);

    return nrf24_spi_transfer(tx, NULL, len + 1);
}

esp_err_t nrf24_read_rx_payload(uint8_t *data, size_t len)
{
    if (data == NULL || len == 0 || len > NRF24_MAX_PAYLOAD_LEN)
    {
        return ESP_ERR_INVALID_ARG;
    }

    uint8_t tx[1 + NRF24_MAX_PAYLOAD_LEN] = {0};
    uint8_t rx[1 + NRF24_MAX_PAYLOAD_LEN] = {0};
    tx[0] = NRF_CMD_R_RX_PAYLOAD;

    ESP_ERROR_CHECK(nrf24_spi_transfer(tx, rx, len + 1));
    memcpy(data, &rx[1], len);

    return ESP_OK;
}

bool nrf24_data_ready(void)
{
    uint8_t status = nrf24_read_reg(NRF_REG_STATUS);
    if (status & NRF_STATUS_RX_DR)
    {
        return true;
    }

    uint8_t fifo = nrf24_read_reg(NRF_REG_FIFO_STATUS);
    return ((fifo & NRF_FIFO_RX_EMPTY) == 0U);
}

esp_err_t nrf24_send_packet(const uint8_t *data, size_t len)
{
    if (data == NULL || len == 0 || len > NRF24_MAX_PAYLOAD_LEN)
    {
        return ESP_ERR_INVALID_ARG;
    }

    ESP_ERROR_CHECK(nrf24_set_tx_mode());
    ESP_ERROR_CHECK(nrf24_clear_irqs());
    ESP_ERROR_CHECK(nrf24_flush_tx());
    ESP_ERROR_CHECK(nrf24_write_tx_payload(data, len));

    nrf24_ce_high();
    esp_rom_delay_us(20);
    nrf24_ce_low();

    TickType_t start = xTaskGetTickCount();
    const TickType_t timeout = pdMS_TO_TICKS(100);

    while ((xTaskGetTickCount() - start) < timeout)
    {
        uint8_t status = nrf24_read_reg(NRF_REG_STATUS);

        if (status & NRF_STATUS_TX_DS)
        {
            ESP_ERROR_CHECK(nrf24_clear_irqs());
            return ESP_OK;
        }

        if (status & NRF_STATUS_MAX_RT)
        {
            ESP_ERROR_CHECK(nrf24_clear_irqs());
            ESP_ERROR_CHECK(nrf24_flush_tx());
            return ESP_FAIL;
        }

        vTaskDelay(pdMS_TO_TICKS(1));
    }

    return ESP_ERR_TIMEOUT;
}

esp_err_t nrf24_receive_packet(uint8_t *data, size_t len)
{
    if (data == NULL || len == 0 || len > NRF24_MAX_PAYLOAD_LEN)
    {
        return ESP_ERR_INVALID_ARG;
    }

    if (!nrf24_data_ready())
    {
        return ESP_ERR_NOT_FOUND;
    }

    ESP_ERROR_CHECK(nrf24_read_rx_payload(data, len));
    ESP_ERROR_CHECK(nrf24_clear_irqs());

    return ESP_OK;
}

esp_err_t nrf24_basic_config(const uint8_t *addr, uint8_t channel, uint8_t payload_len)
{
    if (addr == NULL || payload_len == 0 || payload_len > NRF24_MAX_PAYLOAD_LEN)
    {
        return ESP_ERR_INVALID_ARG;
    }

    nrf24_ce_low();

    ESP_ERROR_CHECK(nrf24_flush_tx());
    ESP_ERROR_CHECK(nrf24_flush_rx());
    ESP_ERROR_CHECK(nrf24_clear_irqs());

    ESP_ERROR_CHECK(nrf24_set_address_width_5bytes());

    ESP_ERROR_CHECK(nrf24_write_reg(NRF_REG_EN_AA, 0x01));
    ESP_ERROR_CHECK(nrf24_write_reg(NRF_REG_EN_RXADDR, 0x01));

    ESP_ERROR_CHECK(nrf24_set_retries(0x02, 0x0F));
    ESP_ERROR_CHECK(nrf24_set_channel(channel));
    ESP_ERROR_CHECK(nrf24_set_rf_setup(NRF_RF_SETUP_1MBPS));

    ESP_ERROR_CHECK(nrf24_set_rx_address_p0(addr, NRF24_ADDR_LEN));
    ESP_ERROR_CHECK(nrf24_set_tx_address(addr, NRF24_ADDR_LEN));
    ESP_ERROR_CHECK(nrf24_set_payload_width_p0(payload_len));

    ESP_ERROR_CHECK(nrf24_write_reg(NRF_REG_DYNPD, 0x00));
    ESP_ERROR_CHECK(nrf24_write_reg(NRF_REG_FEATURE, 0x00));

    ESP_ERROR_CHECK(nrf24_write_reg(
        NRF_REG_CONFIG,
        NRF_CONFIG_EN_CRC | NRF_CONFIG_CRCO | NRF_CONFIG_PWR_UP | NRF_CONFIG_PRIM_RX));

    vTaskDelay(pdMS_TO_TICKS(5));
    nrf24_ce_high();

    ESP_LOGI(TAG, "nRF24 configured: channel=%u payload=%u", channel, payload_len);
    return ESP_OK;
}