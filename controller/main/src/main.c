#include <stdio.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_log.h"
#include "motor_driver.h"
#include "include/nrf24.h"

static const char *TAG = "MAIN";

void task_core0(void *pvParameters)
{ /*
     const uint8_t address[NRF24_ADDR_LEN] = {'N', 'O', 'D', 'E', '1'};
     uint8_t rx_buf[NRF24_MAX_PAYLOAD_LEN] = {0};

     ESP_LOGI(TAG, "Initializing nRF24...");
     ESP_ERROR_CHECK(nrf24_init());

     ESP_ERROR_CHECK(nrf24_basic_config(address, 40, 4));

     ESP_LOGI(TAG, "Mode: RECEIVER");

     while (1)
     {
         if (nrf24_receive_packet(rx_buf, 4) == ESP_OK)
         {
             ESP_LOGI(TAG, "RX: %02X %02X %02X %02X",
                      rx_buf[0], rx_buf[1], rx_buf[2], rx_buf[3]);
         }

         vTaskDelay(pdMS_TO_TICKS(50));
     }
         */

    esp_err_t err;
    uint8_t status = 0;
    uint8_t config = 0;
    uint8_t setup_aw = 0;
    uint8_t rf_ch = 0;

    ESP_LOGI(TAG, "Starting nRF24L01 SPI test...");

    err = nrf24_init();
    if (err != ESP_OK)
    {
        ESP_LOGE(TAG, "nrf24_init failed: %s", esp_err_to_name(err));
        return;
    }

    vTaskDelay(pdMS_TO_TICKS(100));

    status = nrf24_get_status();
    ESP_LOGI(TAG, "STATUS = 0x%02X", status);

    err = nrf24_read_reg_checked(NRF_REG_CONFIG, &config);
    if (err != ESP_OK)
    {
        ESP_LOGE(TAG, "Read CONFIG failed: %s", esp_err_to_name(err));
        return;
    }
    ESP_LOGI(TAG, "CONFIG = 0x%02X", config);

    err = nrf24_read_reg_checked(NRF_REG_SETUP_AW, &setup_aw);
    if (err != ESP_OK)
    {
        ESP_LOGE(TAG, "Read SETUP_AW failed: %s", esp_err_to_name(err));
        return;
    }
    ESP_LOGI(TAG, "SETUP_AW = 0x%02X", setup_aw);

    err = nrf24_write_reg(NRF_REG_RF_CH, 40);
    if (err != ESP_OK)
    {
        ESP_LOGE(TAG, "Write RF_CH failed: %s", esp_err_to_name(err));
        return;
    }

    vTaskDelay(pdMS_TO_TICKS(10));

    err = nrf24_read_reg_checked(NRF_REG_RF_CH, &rf_ch);
    if (err != ESP_OK)
    {
        ESP_LOGE(TAG, "Read RF_CH failed: %s", esp_err_to_name(err));
        return;
    }
    ESP_LOGI(TAG, "RF_CH = %u (0x%02X)", rf_ch, rf_ch);

    if (config == 0x08 && setup_aw == 0x03 && rf_ch == 40)
    {
        ESP_LOGI(TAG, "SPI test PASSED");
    }
    else
    {
        ESP_LOGW(TAG, "SPI test gave unexpected values");
    }

    while (1)
    {
        vTaskDelay(pdMS_TO_TICKS(1000));
    }
}

void task_core1(void *pvParameters)
{
    motor_driver_init();

    while (1)
    {
        printf("hello core 1\n");
        motor_set_throttle(MOTOR_WEAPON, -100);
        vTaskDelay(pdMS_TO_TICKS(1000));
        motor_set_throttle(MOTOR_WEAPON, -50);
        vTaskDelay(pdMS_TO_TICKS(1000));
        motor_set_throttle(MOTOR_WEAPON, 0);
        vTaskDelay(pdMS_TO_TICKS(1000));
        motor_set_throttle(MOTOR_WEAPON, 50);
        vTaskDelay(pdMS_TO_TICKS(1000));
        motor_set_throttle(MOTOR_WEAPON, 100);
        printf("bye core 1 \n");
    }
}

void app_main(void)
{
    xTaskCreatePinnedToCore(
        task_core0,     // function
        "task_core0",   // name
        2048,           // stack size
        NULL,           // parameters
        1,              // priority
        NULL,           // task handle
        0               // core 0
    );

    xTaskCreatePinnedToCore(
        task_core1,
        "task_core1",
        2048,
        NULL,
        1,
        NULL,
        1               // core 1
    );
}