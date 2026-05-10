#include "nrf24.h"

#include <string.h>

#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_log.h"

static const char *TAG = "NRF24";

static spi_device_handle_t s_spi = NULL;
SemaphoreHandle_t nrf24_irq_sem = NULL;

static void nrf24_ce_high(void) { gpio_set_level(NRF24_PIN_CE, 1); }
static void nrf24_ce_low(void)  { gpio_set_level(NRF24_PIN_CE, 0); }

static void csn_high(void) { gpio_set_level(NRF24_PIN_CSN, 1); }
static void csn_low(void)  { gpio_set_level(NRF24_PIN_CSN, 0); }

static esp_err_t spi_transfer(const uint8_t *tx, uint8_t *rx, size_t len)
{
    if (s_spi == NULL || tx == NULL || len == 0) return ESP_ERR_INVALID_STATE;

    spi_transaction_t t = {
        .flags     = 0,
        .length    = len * 8,
        .tx_buffer = tx,
        .rx_buffer = rx,
    };

    csn_low();
    esp_err_t err = spi_device_polling_transmit(s_spi, &t);
    csn_high();

    return err;
}

static esp_err_t write_reg(uint8_t reg, uint8_t value)
{
    uint8_t tx[2] = {(uint8_t)(NRF_CMD_W_REGISTER | (reg & 0x1F)), value};
    return spi_transfer(tx, NULL, sizeof(tx));
}

static esp_err_t write_buf(uint8_t reg, const uint8_t *data, size_t len)
{
    if (data == NULL || len == 0 || len > NRF24_MAX_PAYLOAD_LEN) return ESP_ERR_INVALID_ARG;

    uint8_t tx[1 + NRF24_MAX_PAYLOAD_LEN] = {0};
    tx[0] = (uint8_t)(NRF_CMD_W_REGISTER | (reg & 0x1F));
    memcpy(&tx[1], data, len);

    return spi_transfer(tx, NULL, len + 1);
}

static esp_err_t send_cmd(uint8_t cmd)        { return spi_transfer(&cmd, NULL, 1); }
static esp_err_t flush_tx(void)               { return send_cmd(NRF_CMD_FLUSH_TX); }
static esp_err_t flush_rx(void)               { return send_cmd(NRF_CMD_FLUSH_RX); }

static esp_err_t clear_irqs(void)
{
    return write_reg(NRF_REG_STATUS,
                     NRF_STATUS_RX_DR | NRF_STATUS_TX_DS | NRF_STATUS_MAX_RT);
}

static esp_err_t init_gpio(void)
{
    gpio_config_t ce_cfg = {
        .pin_bit_mask = (1ULL << NRF24_PIN_CE),
        .mode         = GPIO_MODE_OUTPUT,
        .pull_up_en   = GPIO_PULLUP_DISABLE,
        .pull_down_en = GPIO_PULLDOWN_DISABLE,
        .intr_type    = GPIO_INTR_DISABLE,
    };
    ESP_ERROR_CHECK(gpio_config(&ce_cfg));
    nrf24_ce_low();

    gpio_config_t csn_cfg = {
        .pin_bit_mask = (1ULL << NRF24_PIN_CSN),
        .mode         = GPIO_MODE_OUTPUT,
        .pull_up_en   = GPIO_PULLUP_DISABLE,
        .pull_down_en = GPIO_PULLDOWN_DISABLE,
        .intr_type    = GPIO_INTR_DISABLE,
    };
    ESP_ERROR_CHECK(gpio_config(&csn_cfg));
    csn_high();

    gpio_config_t irq_cfg = {
        .pin_bit_mask = (1ULL << NRF24_PIN_IRQ),
        .mode         = GPIO_MODE_INPUT,
        .pull_up_en   = GPIO_PULLUP_ENABLE,
        .pull_down_en = GPIO_PULLDOWN_DISABLE,
        .intr_type    = GPIO_INTR_DISABLE,
    };
    ESP_ERROR_CHECK(gpio_config(&irq_cfg));

    return ESP_OK;
}

static esp_err_t init_spi(void)
{
    spi_bus_config_t buscfg = {
        .mosi_io_num     = NRF24_PIN_MOSI,
        .miso_io_num     = NRF24_PIN_MISO,
        .sclk_io_num     = NRF24_PIN_CLK,
        .quadwp_io_num   = -1,
        .quadhd_io_num   = -1,
        .max_transfer_sz = 33,
    };

    spi_device_interface_config_t devcfg = {
        .clock_speed_hz = 8000000,
        .mode           = 0,
        .spics_io_num   = -1,
        .queue_size     = 1,
    };

    esp_err_t err = spi_bus_initialize(SPI3_HOST, &buscfg, SPI_DMA_DISABLED);
    if (err != ESP_OK && err != ESP_ERR_INVALID_STATE) return err;

    if (s_spi == NULL) {
        ESP_ERROR_CHECK(spi_bus_add_device(SPI3_HOST, &devcfg, &s_spi));
    }

    return ESP_OK;
}

static void IRAM_ATTR nrf24_irq_handler(void *arg)
{
    (void)arg;
    BaseType_t hptw = pdFALSE;
    if (nrf24_irq_sem != NULL) {
        xSemaphoreGiveFromISR(nrf24_irq_sem, &hptw);
    }
    if (hptw == pdTRUE) {
        portYIELD_FROM_ISR();
    }
}

esp_err_t nrf24_init(void)
{
    ESP_ERROR_CHECK(init_gpio());
    ESP_ERROR_CHECK(init_spi());
    return ESP_OK;
}

esp_err_t nrf24_init_irq(void)
{
    nrf24_irq_sem = xSemaphoreCreateBinary();
    if (nrf24_irq_sem == NULL) return ESP_ERR_NO_MEM;

    esp_err_t err = gpio_install_isr_service(0);
    if (err != ESP_OK && err != ESP_ERR_INVALID_STATE) return err;

    ESP_ERROR_CHECK(gpio_set_intr_type(NRF24_PIN_IRQ, GPIO_INTR_NEGEDGE));
    ESP_ERROR_CHECK(gpio_isr_handler_add(NRF24_PIN_IRQ, nrf24_irq_handler, NULL));
    ESP_ERROR_CHECK(gpio_intr_enable(NRF24_PIN_IRQ));

    ESP_ERROR_CHECK(clear_irqs());

    ESP_LOGI(TAG, "IRQ init OK on GPIO %d", NRF24_PIN_IRQ);
    return ESP_OK;
}

uint8_t nrf24_get_status(void)
{
    uint8_t tx[1] = {NRF_CMD_NOP};
    uint8_t rx[1] = {0};
    ESP_ERROR_CHECK(spi_transfer(tx, rx, sizeof(tx)));
    return rx[0];
}

uint8_t nrf24_read_reg(uint8_t reg)
{
    uint8_t tx[2] = {(uint8_t)(NRF_CMD_R_REGISTER | (reg & 0x1F)), NRF_CMD_NOP};
    uint8_t rx[2] = {0};
    ESP_ERROR_CHECK(spi_transfer(tx, rx, sizeof(tx)));
    return rx[1];
}

bool nrf24_data_ready(void)
{
    uint8_t status = nrf24_read_reg(NRF_REG_STATUS);
    if (status & NRF_STATUS_RX_DR) return true;

    uint8_t fifo = nrf24_read_reg(NRF_REG_FIFO_STATUS);
    return ((fifo & NRF_FIFO_RX_EMPTY) == 0U);
}

esp_err_t nrf24_receive_packet(uint8_t *data, size_t len)
{
    if (data == NULL || len == 0 || len > NRF24_MAX_PAYLOAD_LEN) return ESP_ERR_INVALID_ARG;
    if (!nrf24_data_ready()) return ESP_ERR_NOT_FOUND;

    uint8_t tx[1 + NRF24_MAX_PAYLOAD_LEN] = {0};
    uint8_t rx[1 + NRF24_MAX_PAYLOAD_LEN] = {0};
    tx[0] = NRF_CMD_R_RX_PAYLOAD;
    ESP_ERROR_CHECK(spi_transfer(tx, rx, len + 1));
    memcpy(data, &rx[1], len);

    ESP_ERROR_CHECK(clear_irqs());
    return ESP_OK;
}

esp_err_t nrf24_basic_config(const uint8_t *addr, uint8_t channel, uint8_t payload_len)
{
    if (addr == NULL || payload_len == 0 || payload_len > NRF24_MAX_PAYLOAD_LEN) {
        return ESP_ERR_INVALID_ARG;
    }
    if (channel > 125) return ESP_ERR_INVALID_ARG;

    nrf24_ce_low();

    ESP_ERROR_CHECK(flush_tx());
    ESP_ERROR_CHECK(flush_rx());
    ESP_ERROR_CHECK(clear_irqs());

    ESP_ERROR_CHECK(write_reg(NRF_REG_SETUP_AW,   0x03));
    ESP_ERROR_CHECK(write_reg(NRF_REG_EN_AA,       0x01));
    ESP_ERROR_CHECK(write_reg(NRF_REG_EN_RXADDR,   0x01));
    ESP_ERROR_CHECK(write_reg(NRF_REG_SETUP_RETR,  (0x02 << 4) | 0x0F));
    ESP_ERROR_CHECK(write_reg(NRF_REG_RF_CH,       channel));
    ESP_ERROR_CHECK(write_reg(NRF_REG_RF_SETUP,    NRF_RF_SETUP_2MBPS));
    ESP_ERROR_CHECK(write_buf(NRF_REG_RX_ADDR_P0,  addr, NRF24_ADDR_LEN));
    ESP_ERROR_CHECK(write_buf(NRF_REG_TX_ADDR,     addr, NRF24_ADDR_LEN));
    ESP_ERROR_CHECK(write_reg(NRF_REG_RX_PW_P0,   payload_len));
    ESP_ERROR_CHECK(write_reg(NRF_REG_DYNPD,       0x00));
    ESP_ERROR_CHECK(write_reg(NRF_REG_FEATURE,     0x00));
    ESP_ERROR_CHECK(write_reg(NRF_REG_CONFIG,
        NRF_CONFIG_EN_CRC | NRF_CONFIG_CRCO | NRF_CONFIG_PWR_UP | NRF_CONFIG_PRIM_RX));

    vTaskDelay(pdMS_TO_TICKS(5));
    nrf24_ce_high();

    ESP_LOGI(TAG, "nRF24 configured: channel=%u payload=%u @ 8 MHz SPI", channel, payload_len);
    return ESP_OK;
}
