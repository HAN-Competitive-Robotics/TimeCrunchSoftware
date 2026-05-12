#include <stdio.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/queue.h"
#include "esp_log.h"
#include "esp_sleep.h"
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
    uint8_t weapon_throttle;
    bool    failsafe_active;
    bool    packet_received;
    bool    hard_failsafe;   /* latches permanently on explicit failsafe  only power cycle clears */
} robot_state_t;

static QueueHandle_t  state_queue;
static TaskHandle_t   h_core0 = NULL;
static TaskHandle_t   h_core1 = NULL;
static TaskHandle_t   h_temp  = NULL;

/* Center of the 0–255 packet range, per the protocol spec. */
#define PACKET_CENTER 127

static int map_byte_to_throttle(uint8_t b)
{
    return ((int)b - PACKET_CENTER) * 100 / PACKET_CENTER;
}

/* --------------------------------------------------------------------------
 * Core 0  Radio receive, drive motors, failsafe
 * -------------------------------------------------------------------------- */
void task_core0(void *pvParameters)
{
    const uint8_t address[NRF24_ADDR_LEN] = {'1', 'N', 'O', 'D', 'E'};
    uint8_t       rx_buf[4] = {0};
    TickType_t    last_packet_tick = 0;
    bool          have_packet = false;
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
    uint8_t rf_ch  = nrf24_read_reg(NRF_REG_RF_CH);
    ESP_LOGI(TAG, "STATUS = 0x%02X", status);
    ESP_LOGI(TAG, "RF_CH = %u (0x%02X)", rf_ch, rf_ch);

    while (1) {
        if (xSemaphoreTake(nrf24_irq_sem, pdMS_TO_TICKS(50)) == pdTRUE) {
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

                    /* 90 °C triggers deep-sleep killswitch  10 °C below the per-motor
                     * throttle cutoff (MOTOR_TEMP_LIMIT_C = 100 °C) so an overheating
                     * robot shuts down before individual motors are cut one by one. */
                    #define KILLSWITCH_TEMP_C 90.0f
                    bool temp_critical = temp_get_temperature(TEMP_LEFT_WHEEL)  >= KILLSWITCH_TEMP_C ||
                                        temp_get_temperature(TEMP_RIGHT_WHEEL) >= KILLSWITCH_TEMP_C ||
                                        temp_get_temperature(TEMP_WEAPON)      >= KILLSWITCH_TEMP_C;

                    if ((failsafe_raw > 127 || temp_critical) && !state.hard_failsafe) {
                        state.hard_failsafe   = true;
                        state.weapon_throttle = 0;
                        state.failsafe_active = true;
                        motor_set_throttle(MOTOR_LEFT_WHEEL, 0);
                        motor_set_throttle(MOTOR_RIGHT_WHEEL, 0);
                        xQueueOverwrite(state_queue, &state);
                        if (temp_critical)
                            ESP_LOGW(TAG, "THERMAL CUTOFF  entering deep sleep, power cycle to recover");
                        else
                            ESP_LOGW(TAG, "KILLSWITCH  entering deep sleep, power cycle to recover");
                        vTaskDelay(pdMS_TO_TICKS(200));
                        esp_deep_sleep_start();
                    } else if (!state.hard_failsafe) {
                        int left  = map_byte_to_throttle(left_raw);
                        int right = map_byte_to_throttle(right_raw);

                        state.weapon_throttle = weapon_raw;
                        state.failsafe_active = false;
                        motor_set_throttle(MOTOR_LEFT_WHEEL, left);
                        motor_set_throttle(MOTOR_RIGHT_WHEEL, right);
                    }

                    state.packet_received = true;
                    xQueueOverwrite(state_queue, &state);
                }
            }
        }

        if (have_packet &&
            (xTaskGetTickCount() - last_packet_tick) >= pdMS_TO_TICKS(500)) {
            ESP_LOGW(TAG, "Packet timeout  stopping motors");
            motor_set_throttle(MOTOR_LEFT_WHEEL, 0);
            motor_set_throttle(MOTOR_RIGHT_WHEEL, 0);

            state.weapon_throttle = 0;
            state.failsafe_active = true;
            state.packet_received = false;
            xQueueOverwrite(state_queue, &state);
            have_packet = false;
        }
    }
}

/* --------------------------------------------------------------------------
 * Core 1  Weapon PI controller (100 Hz)
 * -------------------------------------------------------------------------- */
void task_core1(void *pvParameters)
{
    robot_state_t state = {0};
    TickType_t    wake_time = xTaskGetTickCount();

    while (1) {
        vTaskDelayUntil(&wake_time, pdMS_TO_TICKS(10));

        robot_state_t new_state;
        if (xQueueReceive(state_queue, &new_state, 0) == pdTRUE) {
            state = new_state;
        }

        /* Weapon: 127=off, 0-62=attack reverse, 63-126=idle reverse, 128-191=idle, 192-255=attack */
        if (state.hard_failsafe || state.failsafe_active || !state.packet_received || state.weapon_throttle == 127) {
            weapon_controller_reset();
            motor_set_throttle(MOTOR_WEAPON, 0);
        } else if (state.weapon_throttle >= 191 || state.weapon_throttle <= 63) {
            weapon_controller_set_reverse_flag(state.weapon_throttle >= 191 ? 1 : -1);
            weapon_controller_set_target_rpm(WEAPON_ATTACK_RPM);
            weapon_controller_update();
        } else {
            weapon_controller_set_reverse_flag(state.weapon_throttle > 127 ? 1 : -1);
            weapon_controller_set_target_rpm(WEAPON_IDLE_RPM);
            weapon_controller_update();
        }
    }
}

/* --------------------------------------------------------------------------
 * Core 1  Thermal safety (1 Hz)
 * -------------------------------------------------------------------------- */
void task_temp(void *pvParameters)
{
    vTaskDelay(pdMS_TO_TICKS(500));

    while (1) {
        motor_safety_check();
        ESP_LOGD(TAG, "TEMP: L=%.1f°C R=%.1f°C W=%.1f°C  RPM=%.0f",
                 temp_get_temperature(TEMP_LEFT_WHEEL),
                 temp_get_temperature(TEMP_RIGHT_WHEEL),
                 temp_get_temperature(TEMP_WEAPON),
                 encoder_get_rpm());
        vTaskDelay(pdMS_TO_TICKS(1000));
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

    xTaskCreatePinnedToCore(task_core0, "task_core0", 6144, NULL, 3, &h_core0, 0);
    xTaskCreatePinnedToCore(task_core1, "task_core1", 4096, NULL, 2, &h_core1, 1);
    xTaskCreatePinnedToCore(task_temp,  "task_temp",  4096, NULL, 1, &h_temp,  1);
}
