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
    uint8_t weapon_throttle;
    bool    failsafe_active;
    bool    packet_received;
    bool    hard_failsafe;   /* latches permanently on explicit failsafe — only power cycle clears */
} robot_state_t;

static QueueHandle_t  state_queue;
static TaskHandle_t   h_core0 = NULL;
static TaskHandle_t   h_core1 = NULL;
static TaskHandle_t   h_temp  = NULL;

static int map_byte_to_throttle(uint8_t b)
{
    return ((int)b - 127) * 100 / 127;
}

/* --------------------------------------------------------------------------
 * Core 0 — Radio receive, drive motors, failsafe
 *
 * Uses a 50 ms semaphore poll so the timeout check runs at
 * least 10× per second. Worst-case failsafe latency is now 550 ms max
 * (one 50 ms window past the 500 ms threshold) rather than 1000 ms.
 *
 * weapon_controller_reset() is intentionally NOT called here.
 * task_core1 owns the weapon controller state exclusively — it resets
 * when it sees failsafe_active or !packet_received in the queue.
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
    ESP_LOGI(TAG, "Mode: RECEIVER (IRQ-driven, 50 ms poll)");

    while (1) {
        /* Wait for nRF24 IRQ or 50 ms — gives failsafe check 20 Hz resolution */
        if (xSemaphoreTake(nrf24_irq_sem, pdMS_TO_TICKS(50)) == pdTRUE) {
            /* Drain entire FIFO on each wake */
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

                    if (state.hard_failsafe || failsafe_raw > 127) {
                        state.hard_failsafe   = true;
                        state.weapon_throttle = 0;
                        state.failsafe_active = true;
                        motor_set_throttle(MOTOR_LEFT_WHEEL, 0);
                        motor_set_throttle(MOTOR_RIGHT_WHEEL, 0);
                        if (failsafe_raw > 127) {
                            ESP_LOGW(TAG, "Hard failsafe triggered — latched until power cycle");
                        }
                    } else {
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

        /* Failsafe timeout: >= 500 ms since last good packet.
         * Checked on every 50 ms poll iteration so it fires promptly. */
        if (have_packet &&
            (xTaskGetTickCount() - last_packet_tick) >= pdMS_TO_TICKS(500)) {
            ESP_LOGW(TAG, "Packet timeout — stopping motors");
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
 * Core 1 — Weapon PI controller (100 Hz, drift-free)
 *
 * Uses vTaskDelayUntil for drift-compensated 10 ms periods.
 * Exclusively owns weapon_controller state — no other task touches it.
 * Temperature safety runs in task_temp; this task never blocks on I2C.
 * -------------------------------------------------------------------------- */
void task_core1(void *pvParameters)
{
    robot_state_t state = {0};
    TickType_t    wake_time = xTaskGetTickCount();

    while (1) {
        vTaskDelayUntil(&wake_time, pdMS_TO_TICKS(10)); /* drift-free 100 Hz */

        robot_state_t new_state;
        if (xQueueReceive(state_queue, &new_state, 0) == pdTRUE) {
            state = new_state;
        }

        /* Weapon control: 0=off, 1-127=idle, 128-255=attack */
        if (state.hard_failsafe || state.failsafe_active || !state.packet_received || state.weapon_throttle == 0) {
            weapon_controller_reset();
            motor_set_throttle(MOTOR_WEAPON, 0);
        } else if (state.weapon_throttle >= 128) {
            weapon_controller_set_target_rpm(WEAPON_ATTACK_RPM);
            weapon_controller_update();
        } else {
            weapon_controller_set_target_rpm(WEAPON_IDLE_RPM);
            weapon_controller_update();
        }
    }
}

/* --------------------------------------------------------------------------
 * Core 1 — Thermal safety (1 Hz)
 *
 * Dedicated low-priority task so blocking I2C reads (up to 30 ms for 3
 * sensors) never stall the weapon PI loop in task_core1.
 * motor_safety_check() latches per-motor thermal cutoff flags that
 * motor_set_throttle() enforces atomically.
 * -------------------------------------------------------------------------- */
void task_temp(void *pvParameters)
{
    /* Stagger startup so all three tasks don't hit I2C simultaneously */
    vTaskDelay(pdMS_TO_TICKS(500));

    while (1) {
        motor_safety_check();

        ESP_LOGD(TAG, "Core0 stack HWM: %u  Core1: %u  Temp: %u",
                 h_core0 ? uxTaskGetStackHighWaterMark(h_core0) : 0,
                 h_core1 ? uxTaskGetStackHighWaterMark(h_core1) : 0,
                 uxTaskGetStackHighWaterMark(NULL));

        vTaskDelay(pdMS_TO_TICKS(1000)); /* 1 Hz */
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

    /* Stack sizes: core0 does heavy init (SPI, I2C, MCPWM, PCNT drivers).
     * 6144 words gives headroom; verify uxTaskGetStackHighWaterMark in logs. */
    xTaskCreatePinnedToCore(task_core0, "task_core0", 6144, NULL, 3, &h_core0, 0);
    xTaskCreatePinnedToCore(task_core1, "task_core1", 4096, NULL, 2, &h_core1, 1);
    xTaskCreatePinnedToCore(task_temp,  "task_temp",  4096, NULL, 1, &h_temp,  1);
}
