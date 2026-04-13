#include <stdio.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_log.h"
#include "motor_driver.h"
#include "nrf24.h"

static const char *TAG = "MAIN";

void task_core0(void *pvParameters)
{ 
     const uint8_t address[NRF24_ADDR_LEN] = {'N', 'O', 'D', 'E', '1'};
     uint8_t rx_buf[NRF24_MAX_PAYLOAD_LEN] = {0};
     uint8_t status = 0;
     uint8_t rf_ch = 0;

     ESP_LOGI(TAG, "Initializing nRF24...");
     ESP_ERROR_CHECK(nrf24_init());

     ESP_ERROR_CHECK(nrf24_basic_config(address, 40, 4));

     status = nrf24_get_status();
     ESP_LOGI(TAG, "STATUS = 0x%02X", status);
     nrf24_read_reg_checked(NRF_REG_RF_CH, &rf_ch);
     ESP_LOGI(TAG, "RF_CH = %u (0x%02X)", rf_ch, rf_ch);

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