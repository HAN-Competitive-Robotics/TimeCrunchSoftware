#include <stdio.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/queue.h"
#include "esp_log.h"
#include "motor_driver.h"
#include "tempsensor_driver.h"
#include "encoder_driver.h"
#include "weapon_controller.h"
#include "nrf24.h"

static const char *TAG = "MAIN";

/* --------------------------------------------------------------------------
 * Shared state between cores
 * -------------------------------------------------------------------------- */
typedef struct {
    bool weapon_armed;
    bool failsafe_active;
    bool packet_received;
} robot_state_t;

static QueueHandle_t state_queue;

static int map_byte_to_throttle(uint8_t b)
{
    return ((int)b - 127) * 100 / 127;
}

/* --------------------------------------------------------------------------
 * Core 0 — Radio receive, drive motors, failsafe
 * -------------------------------------------------------------------------- */
void task_core0(void *pvParameters)
{
    const uint8_t address[NRF24_ADDR_LEN] = {'1', 'N', 'O', 'D', 'E'};
    uint8_t rx_buf[NRF24_MAX_PAYLOAD_LEN] = {0};
    TickType_t last_packet_tick = 0;
    bool have_packet = false;
    robot_state_t state = {0};

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
    ESP_ERROR_CHECK(nrf24_init_irq());

    uint8_t status = nrf24_get_status();
    uint8_t rf_ch = nrf24_read_reg(NRF_REG_RF_CH);
    ESP_LOGI(TAG, "STATUS = 0x%02X", status);
    ESP_LOGI(TAG, "RF_CH = %u (0x%02X)", rf_ch, rf_ch);
    ESP_LOGI(TAG, "Mode: RECEIVER (IRQ-driven)");

    while (1) {
        /* Wait for nRF24 IRQ (packet received) or 500 ms timeout for failsafe */
        if (xSemaphoreTake(nrf24_irq_sem, pdMS_TO_TICKS(500)) == pdTRUE) {
            /* Packet(s) arrived — drain the entire FIFO */
            while (nrf24_data_ready()) {
                if (nrf24_receive_packet(rx_buf, 4) == ESP_OK) {
                    last_packet_tick = xTaskGetTickCount();
                    have_packet = true;

                    uint8_t left_raw     = rx_buf[0];
                    uint8_t right_raw    = rx_buf[1];
                    uint8_t weapon_raw   = rx_buf[2];
                    uint8_t failsafe_raw = rx_buf[3];

                    ESP_LOGD(TAG, "RX: L=%3d R=%3d W=%3d F=%3d",
                             left_raw, right_raw, weapon_raw, failsafe_raw);

                    if (failsafe_raw > 127) {
                        state.weapon_armed    = false;
                        state.failsafe_active = true;
                        motor_set_throttle(MOTOR_LEFT_WHEEL, 0);
                        motor_set_throttle(MOTOR_RIGHT_WHEEL, 0);
                        weapon_controller_reset();
                    } else {
                        int left  = map_byte_to_throttle(left_raw);
                        int right = map_byte_to_throttle(right_raw);

                        state.weapon_armed    = (weapon_raw > 127);
                        state.failsafe_active = false;

                        motor_set_throttle(MOTOR_LEFT_WHEEL, left);
                        motor_set_throttle(MOTOR_RIGHT_WHEEL, right);
                    }

                    state.packet_received = true;
                    xQueueOverwrite(state_queue, &state);
                }
            }
        }

        /* Failsafe timeout: stop motors if no packet for 500 ms */
        if (have_packet && (xTaskGetTickCount() - last_packet_tick) > pdMS_TO_TICKS(500)) {
            ESP_LOGW(TAG, "Packet timeout — stopping motors");
            motor_set_throttle(MOTOR_LEFT_WHEEL, 0);
            motor_set_throttle(MOTOR_RIGHT_WHEEL, 0);
            weapon_controller_reset();

            state.weapon_armed    = false;
            state.failsafe_active = true;
            state.packet_received = false;
            xQueueOverwrite(state_queue, &state);
            have_packet = false;
        }
    }
}

/* --------------------------------------------------------------------------
 * Core 1 — Weapon PI controller + temperature safety (100 Hz)
 * -------------------------------------------------------------------------- */
void task_core1(void *pvParameters)
{
    robot_state_t state = {0};
    uint32_t tick_count = 0;

    while (1) {
        /* Pull latest state from Core 0 (non-blocking) */
        robot_state_t new_state;
        if (xQueueReceive(state_queue, &new_state, 0) == pdTRUE) {
            state = new_state;
        }

        /* Weapon control */
        if (state.failsafe_active || !state.packet_received) {
            weapon_controller_reset();
            motor_set_throttle(MOTOR_WEAPON, 0);
        } else if (state.weapon_armed) {
            weapon_controller_update();
        } else {
            weapon_controller_reset();
            motor_set_throttle(MOTOR_WEAPON, 0);
        }

        /* Temperature safety check at 1 Hz */
        if (++tick_count >= 100) {
            tick_count = 0;
            motor_safety_check();
        }

        vTaskDelay(pdMS_TO_TICKS(10)); /* 100 Hz loop */
    }
}

/* --------------------------------------------------------------------------
 * Startup
 * -------------------------------------------------------------------------- */
void app_main(void)
{
    state_queue = xQueueCreate(1, sizeof(robot_state_t));
    if (state_queue == NULL) {
        ESP_LOGE(TAG, "Failed to create state queue");
        return;
    }

    xTaskCreatePinnedToCore(
        task_core0, "task_core0", 4096, NULL, 3, NULL, 0
    );

    xTaskCreatePinnedToCore(
        task_core1, "task_core1", 4096, NULL, 2, NULL, 1
    );
}
