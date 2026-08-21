#include <stdio.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/queue.h"
#include "esp_log.h"
#include "esp_sleep.h"
#include "esp_system.h"
#include "esp_task_wdt.h"
#include "motor_driver.h"
#include "power_sensor_driver.h"
#include "hall_sensor.h"
#include "safety_monitor.h"
#include "weapon_controller.h"
#include "nrf24.h"
#include "robot_config.h"
#if THERMAL_PROTECTION_ENABLED
#include "tempsensor_driver.h"
#endif

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
static TaskHandle_t   h_radio   = NULL;
static TaskHandle_t   h_weapon  = NULL;
static TaskHandle_t   h_thermal = NULL;

/* Center of the 0–255 packet range, per the protocol spec. */
#define PACKET_CENTER 127

/* System-level thermal shutdown threshold. 10 °C below MOTOR_TEMP_LIMIT_C so
 * the robot enters deep-sleep before per-motor cutoffs fire one by one. */
#define KILLSWITCH_TEMP_C 90.0f

static int map_byte_to_throttle(uint8_t b)
{
    return ((int)b - PACKET_CENTER) * 100 / PACKET_CENTER;
}

/* --------------------------------------------------------------------------
 * Packet gap statistics
 * --------------------------------------------------------------------------
 * LINK_LOSS_TIMEOUT_MS is currently 500 ms, inherited rather than measured.
 * Picking the right number needs the distribution of real inter-packet gaps
 * under arena conditions, so record it and print it periodically. After a
 * match, the highest occupied bucket is the worst gap the link actually
 * produced; the timeout wants to sit above that with margin.
 * -------------------------------------------------------------------------- */
#define GAP_BUCKET_COUNT 6
static const uint16_t gap_bucket_ms[GAP_BUCKET_COUNT] = { 50, 100, 200, 300, 400, 500 };

typedef struct {
    uint32_t packets;
    uint32_t timeouts;
    uint32_t max_gap_ms;
    uint32_t buckets[GAP_BUCKET_COUNT + 1];  /* last bucket = over 500 ms */
} packet_stats_t;

static void gap_record(packet_stats_t *s, uint32_t gap_ms)
{
    if (gap_ms > s->max_gap_ms) s->max_gap_ms = gap_ms;
    for (int i = 0; i < GAP_BUCKET_COUNT; i++) {
        if (gap_ms <= gap_bucket_ms[i]) { s->buckets[i]++; return; }
    }
    s->buckets[GAP_BUCKET_COUNT]++;
}

static void gap_report(const packet_stats_t *s)
{
    ESP_LOGI(TAG,
             "LINK: %lu pkts, %lu timeouts, max gap %lu ms | "
             "<=50:%lu <=100:%lu <=200:%lu <=300:%lu <=400:%lu <=500:%lu >500:%lu",
             (unsigned long)s->packets, (unsigned long)s->timeouts,
             (unsigned long)s->max_gap_ms,
             (unsigned long)s->buckets[0], (unsigned long)s->buckets[1],
             (unsigned long)s->buckets[2], (unsigned long)s->buckets[3],
             (unsigned long)s->buckets[4], (unsigned long)s->buckets[5],
             (unsigned long)s->buckets[6]);
}

/* --------------------------------------------------------------------------
 * task_radio — Radio receive, drive motors, failsafe  (Core 0)
 * -------------------------------------------------------------------------- */
void task_radio(void *pvParameters)
{
    const uint8_t address[NRF24_ADDR_LEN] = {'1', 'N', 'O', 'D', 'E'};
    uint8_t        rx_buf[4] = {0};
    TickType_t     last_packet_tick = 0;
    bool           have_packet = false;
    robot_state_t  state = {0};
    packet_stats_t stats = {0};
    TickType_t     last_report_tick = xTaskGetTickCount();

    ESP_LOGI(TAG, "Initializing motor driver...");
    motor_driver_init();

#if THERMAL_PROTECTION_ENABLED
    ESP_LOGI(TAG, "Initializing temperature sensors...");
    tempsensor_driver_init();
#endif

    ESP_LOGI(TAG, "Initializing power sensors...");
    power_sensor_driver_init();

    ESP_LOGI(TAG, "Initializing hall sensor...");
    hall_sensor_init();

    ESP_LOGI(TAG, "Initializing weapon controller...");
    weapon_controller_init();

    ESP_LOGI(TAG, "Initializing nRF24...");
    ESP_ERROR_CHECK(nrf24_init());
    ESP_ERROR_CHECK(nrf24_basic_config(address, 40, BATTLEBOT_PAYLOAD_LEN));
    ESP_ERROR_CHECK(nrf24_init_irq());

    uint8_t status = nrf24_get_status();
    uint8_t rf_ch  = nrf24_read_reg(NRF_REG_RF_CH);
    ESP_LOGI(TAG, "STATUS = 0x%02X", status);
    ESP_LOGI(TAG, "RF_CH = %u (0x%02X)", rf_ch, rf_ch);

    ESP_ERROR_CHECK(esp_task_wdt_add(NULL));

    while (1) {
        esp_task_wdt_reset();

        if (xSemaphoreTake(nrf24_irq_sem, pdMS_TO_TICKS(50)) == pdTRUE) {
            while (nrf24_data_ready()) {
                if (nrf24_receive_packet(rx_buf, BATTLEBOT_PAYLOAD_LEN) == ESP_OK) {
                    TickType_t rx_tick = xTaskGetTickCount();
                    if (have_packet) {
                        gap_record(&stats,
                                   (uint32_t)((rx_tick - last_packet_tick) * portTICK_PERIOD_MS));
                    }
                    stats.packets++;
                    last_packet_tick = rx_tick;
                    have_packet = true;

                    uint8_t left_raw     = rx_buf[0];
                    uint8_t right_raw    = rx_buf[1];
                    uint8_t weapon_raw   = rx_buf[2];
                    uint8_t failsafe_raw = rx_buf[3];

                    ESP_LOGD(TAG, "RX: L=%3d R=%3d W=%3d F=%3d  RPM: %.1f",
                             left_raw, right_raw, weapon_raw, failsafe_raw, hall_sensor_get_rpm());

#if THERMAL_PROTECTION_ENABLED
                    bool temp_critical = temp_get_temperature(TEMP_LEFT_WHEEL)  >= KILLSWITCH_TEMP_C ||
                                        temp_get_temperature(TEMP_RIGHT_WHEEL) >= KILLSWITCH_TEMP_C ||
                                        temp_get_temperature(TEMP_WEAPON)      >= KILLSWITCH_TEMP_C;
                    if (temp_critical && !state.hard_failsafe) {
                        state.hard_failsafe   = true;
                        state.weapon_throttle = 0;
                        state.failsafe_active = true;
                        motor_set_throttle(MOTOR_LEFT_WHEEL,  0);
                        motor_set_throttle(MOTOR_RIGHT_WHEEL, 0);
                        xQueueOverwrite(state_queue, &state);
                        ESP_LOGW(TAG, "THERMAL SHUTDOWN — entering deep sleep, power cycle to recover");
                        /* Leaving the watchdog subscribed here would panic the
                         * chip during the settle delay and turn a controlled
                         * shutdown into a reboot, which re-arms everything. */
                        esp_task_wdt_delete(NULL);
                        vTaskDelay(pdMS_TO_TICKS(200));
                        esp_deep_sleep_start();
                    }
#endif

                    if ((failsafe_raw > 127) && !state.hard_failsafe) {
                        state.hard_failsafe   = true;
                        state.weapon_throttle = 0;
                        state.failsafe_active = true;
                        motor_set_throttle(MOTOR_LEFT_WHEEL, 0);
                        motor_set_throttle(MOTOR_RIGHT_WHEEL, 0);
                        xQueueOverwrite(state_queue, &state);
                        ESP_LOGW(TAG, "KILLSWITCH  entering deep sleep, power cycle to recover");
                        /* Leaving the watchdog subscribed here would panic the
                         * chip during the settle delay and turn a controlled
                         * shutdown into a reboot, which re-arms everything. */
                        esp_task_wdt_delete(NULL);
                        vTaskDelay(pdMS_TO_TICKS(200));
                        esp_deep_sleep_start();
                    } else if (!state.hard_failsafe) {
                        int left  = map_byte_to_throttle(left_raw);
                        int right = map_byte_to_throttle(right_raw);

                        state.weapon_throttle = weapon_raw;
                        state.failsafe_active = false;
                        motor_set_throttle(MOTOR_LEFT_WHEEL, -left);
                        motor_set_throttle(MOTOR_RIGHT_WHEEL, right);
                    }

                    state.packet_received = true;
                    xQueueOverwrite(state_queue, &state);
                }
            }
        }

        if (have_packet &&
            (xTaskGetTickCount() - last_packet_tick) >= pdMS_TO_TICKS(LINK_LOSS_TIMEOUT_MS)) {
            ESP_LOGW(TAG, "Packet timeout (%d ms)  stopping motors", LINK_LOSS_TIMEOUT_MS);
            motor_set_throttle(MOTOR_LEFT_WHEEL, 0);
            motor_set_throttle(MOTOR_RIGHT_WHEEL, 0);

            stats.timeouts++;
            state.weapon_throttle = 0;
            state.failsafe_active = true;
            state.packet_received = false;
            xQueueOverwrite(state_queue, &state);
            have_packet = false;
        }

        if ((xTaskGetTickCount() - last_report_tick) >= pdMS_TO_TICKS(PACKET_STATS_LOG_MS)) {
            last_report_tick = xTaskGetTickCount();
            gap_report(&stats);
        }
    }
}

/* --------------------------------------------------------------------------
 * task_weapon — Weapon PI controller, 100 Hz  (Core 1)
 * -------------------------------------------------------------------------- */
void task_weapon(void *pvParameters)
{
    robot_state_t state = {0};
    TickType_t    wake_time = xTaskGetTickCount();

    ESP_ERROR_CHECK(esp_task_wdt_add(NULL));

    while (1) {
        vTaskDelayUntil(&wake_time, pdMS_TO_TICKS(10));
        esp_task_wdt_reset();

        robot_state_t new_state;
        if (xQueueReceive(state_queue, &new_state, 0) == pdTRUE) {
            state = new_state;
        }

        /* Weapon: 127=off, 0-63=attack rev, 64-126=idle rev, 128-190=idle, 191-255=attack */
        if (state.hard_failsafe || state.failsafe_active || !state.packet_received ||
            state.weapon_throttle == 127 || safety_weapon_inhibited()) {
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

#if THERMAL_PROTECTION_ENABLED
/* --------------------------------------------------------------------------
 * task_thermal — Thermal safety, 1 Hz  (Core 1)
 * -------------------------------------------------------------------------- */
void task_thermal(void *pvParameters)
{
    vTaskDelay(pdMS_TO_TICKS(500));

    while (1) {
        motor_safety_check();
        ESP_LOGD(TAG, "TEMP: L=%.1f°C R=%.1f°C W=%.1f°C  RPM=%.0f",
                 temp_get_temperature(TEMP_LEFT_WHEEL),
                 temp_get_temperature(TEMP_RIGHT_WHEEL),
                 temp_get_temperature(TEMP_WEAPON),
                 hall_sensor_get_rpm());
        vTaskDelay(pdMS_TO_TICKS(1000));
    }
}
#endif

/* --------------------------------------------------------------------------
 * Startup
 * -------------------------------------------------------------------------- */
void app_main(void)
{
    /* A brownout reset means the pack collapsed far enough to drop the rail.
     * Nothing latches across the reset, so the robot comes up disarmed and
     * stays that way until packets arrive, but the operator needs to know it
     * happened rather than seeing an unexplained reboot mid-match. */
    esp_reset_reason_t reason = esp_reset_reason();
    if (reason == ESP_RST_BROWNOUT) {
        ESP_LOGE(TAG, "Last reset was a BROWNOUT — check pack voltage and weapon current draw");
    } else if (reason == ESP_RST_TASK_WDT || reason == ESP_RST_WDT) {
        ESP_LOGE(TAG, "Last reset was a WATCHDOG timeout — a real-time task stalled");
    }

    /* The IDF starts the task watchdog for the idle tasks at boot, so this is
     * a reconfigure rather than a fresh init. idle_core_mask is cleared: the
     * idle tasks legitimately starve while the control tasks are busy, and
     * panicking over that would reset a perfectly healthy robot. */
    esp_task_wdt_config_t twdt_cfg = {
        .timeout_ms     = TASK_WDT_TIMEOUT_MS,
        .idle_core_mask = 0,
        .trigger_panic  = true,
    };
    esp_err_t werr = esp_task_wdt_reconfigure(&twdt_cfg);
    if (werr == ESP_ERR_INVALID_STATE) {
        werr = esp_task_wdt_init(&twdt_cfg);
    }
    ESP_ERROR_CHECK(werr);
    ESP_LOGI(TAG, "Task watchdog armed at %d ms", TASK_WDT_TIMEOUT_MS);

    state_queue = xQueueCreate(1, sizeof(robot_state_t));
    if (state_queue == NULL) {
        ESP_LOGE(TAG, "Failed to create state queue");
        return;
    }

    xTaskCreatePinnedToCore(task_radio,  "task_radio",  6144, NULL, 3, &h_radio,  0);
    xTaskCreatePinnedToCore(task_weapon, "task_weapon", 4096, NULL, 2, &h_weapon, 1);
#if THERMAL_PROTECTION_ENABLED
    xTaskCreatePinnedToCore(task_thermal, "task_thermal", 4096, NULL, 1, &h_thermal, 1);
#endif

    /* Started last so the drivers it reads are already initialised by
     * task_radio's init block. */
    safety_monitor_init();
}
