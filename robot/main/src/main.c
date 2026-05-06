#include <stdio.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_log.h"
#include "motor_driver.h"
#include "tempsensor_driver.h"
#include "encoder_driver.h"
#include "weapon_controller.h"
#include "nrf24.h"

static const char *TAG = "MAIN";

static int map_byte_to_throttle(uint8_t b)
{
    return ((int)b - 127) * 100 / 127;
}

void task_core0(void *pvParameters)
{ 
     const uint8_t address[NRF24_ADDR_LEN] = {'1', 'N', 'O', 'D', 'E'};
     uint8_t rx_buf[NRF24_MAX_PAYLOAD_LEN] = {0};
     uint8_t status = 0;
     uint8_t rf_ch = 0;
     TickType_t last_packet_tick = 0;
     bool have_packet = false;

     ESP_LOGI(TAG, "Initializing motor driver...");
     motor_driver_init();

     ESP_LOGI(TAG, "Initializing temperature sensors...");
     tempsensor_driver_init();

     ESP_LOGI(TAG, "Initializing encoder...");
     encoder_driver_init();

     ESP_LOGI(TAG, "Initializing weapon controller...");
     weapon_controller_init();

     ESP_LOGI(TAG, "Initializing nRF24...");
     ESP_ERROR_CHECK(nrf24_init());

     ESP_ERROR_CHECK(nrf24_basic_config(address, 40, 4));

     status = nrf24_get_status();
     ESP_LOGI(TAG, "STATUS = 0x%02X", status);
     nrf24_read_reg_checked(NRF_REG_RF_CH, &rf_ch);
     ESP_LOGI(TAG, "RF_CH = %u (0x%02X)", rf_ch, rf_ch);

     ESP_LOGI(TAG, "Mode: RECEIVER");

     uint32_t loop_count = 0;
     while (1)
     {
         if (nrf24_receive_packet(rx_buf, 4) == ESP_OK)
         {
             last_packet_tick = xTaskGetTickCount();
             have_packet = true;

             uint8_t left_raw     = rx_buf[0];
             uint8_t right_raw    = rx_buf[1];
             uint8_t weapon_raw   = rx_buf[2];
             uint8_t failsafe_raw = rx_buf[3];

             ESP_LOGD(TAG, "RX: L=%3d R=%3d W=%3d F=%3d",
                      left_raw, right_raw, weapon_raw, failsafe_raw);

             if (failsafe_raw > 127)
             {
                 motor_set_throttle(MOTOR_LEFT_WHEEL, 0);
                 motor_set_throttle(MOTOR_RIGHT_WHEEL, 0);
                 motor_set_throttle(MOTOR_WEAPON, 0);
                 weapon_controller_reset();
             }
             else
             {
                 int left_throttle  = map_byte_to_throttle(left_raw);
                 int right_throttle = map_byte_to_throttle(right_raw);

                 motor_set_throttle(MOTOR_LEFT_WHEEL, left_throttle);
                 motor_set_throttle(MOTOR_RIGHT_WHEEL, right_throttle);

                 /* Weapon PI control: run closed-loop when armed, stop when disarmed */
                 if (weapon_raw > 127)
                 {
                     weapon_controller_update();
                 }
                 else
                 {
                     weapon_controller_reset();
                     motor_set_throttle(MOTOR_WEAPON, 0);
                 }
             }
         }

         /* Failsafe timeout: stop motors if no packet for 500 ms */
         if (have_packet && (xTaskGetTickCount() - last_packet_tick) > pdMS_TO_TICKS(500))
         {
             ESP_LOGW(TAG, "Packet timeout — stopping motors");
             motor_set_throttle(MOTOR_LEFT_WHEEL, 0);
             motor_set_throttle(MOTOR_RIGHT_WHEEL, 0);
             motor_set_throttle(MOTOR_WEAPON, 0);
             have_packet = false;
         }

         /* Dump STATUS / FIFO every ~2 s so we can see if anything is arriving */
         if (++loop_count >= 40)
         {
             loop_count = 0;
             uint8_t status = nrf24_get_status();
             uint8_t fifo   = nrf24_read_reg(NRF_REG_FIFO_STATUS);
             ESP_LOGD(TAG, "STATUS=0x%02X FIFO=0x%02X", status, fifo);
         }

         motor_safety_check();
         vTaskDelay(pdMS_TO_TICKS(50));
     }
}

/* Core 1 idle task — available for future real-time work (e.g. weapon PID at higher rate,
   telemetry back-channel, or safety watchdog). */
void task_core1(void *pvParameters)
{
    while (1)
    {
        vTaskDelay(pdMS_TO_TICKS(1000));
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