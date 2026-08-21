#include "safety_monitor.h"

#include <math.h>
#include <stdatomic.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_log.h"
#include "hall_sensor.h"
#include "power_sensor_driver.h"
#include "robot_config.h"
#include "weapon_controller.h"

#define MONITOR_PERIOD_MS   50      /* 20 Hz */

static const char *TAG = "SAFETY";

static _Atomic bool  s_feedback_fault = false;
static _Atomic bool  s_weapon_inhibit = false;
static _Atomic float s_battery_v      = 0.0f;   /* NAN-initialised in the task */

bool safety_weapon_feedback_fault(void)
{
    return atomic_load_explicit(&s_feedback_fault, memory_order_relaxed);
}

bool safety_weapon_inhibited(void)
{
    return atomic_load_explicit(&s_weapon_inhibit, memory_order_relaxed);
}

float safety_get_battery_voltage(void)
{
    return atomic_load_explicit(&s_battery_v, memory_order_relaxed);
}

/* --------------------------------------------------------------------------
 * Feedback fault
 *
 * Fault when the weapon has been commanded above WEAPON_FEEDBACK_MIN_OUTPUT
 * for WEAPON_FEEDBACK_FAULT_MS with no Hall edge in that whole time.
 *
 * The current reading, when the INA3221 is present, is used only to SUPPRESS
 * the fault: if the weapon is drawing essentially nothing then the ESC is not
 * actually driving the motor, so silence from the sensor is correct and not a
 * fault. When the INA3221 is absent the reading is NAN and the check falls
 * back to command-and-silence alone.
 *
 * Both directions of a wrong threshold are safe. Too sensitive and we declare
 * a fault that is not there, which degrades to open-loop feed-forward, exactly
 * what the firmware does today. Too insensitive and we simply fail to upgrade
 * that behaviour. Neither makes the weapon less safe than it currently is.
 * -------------------------------------------------------------------------- */
static void update_feedback_fault(TickType_t now)
{
    static TickType_t commanded_since = 0;
    static bool       was_commanded   = false;

    float output = weapon_controller_get_output();
    bool  driven = output >= WEAPON_FEEDBACK_MIN_OUTPUT;

    if (driven) {
        float amps = power_sensor_get_current(POWER_WEAPON);
        if (!isnan(amps) && fabsf(amps) < WEAPON_FEEDBACK_MIN_CURRENT_A) {
            driven = false;   /* commanded, but the ESC is not delivering */
        }
    }

    if (!driven) {
        was_commanded = false;
        if (atomic_exchange_explicit(&s_feedback_fault, false, memory_order_relaxed)) {
            ESP_LOGI(TAG, "Weapon feedback fault cleared");
        }
        return;
    }

    if (!was_commanded) {
        was_commanded   = true;
        commanded_since = now;
        return;
    }

    if (hall_sensor_signal_fresh()) {
        /* Sensor is reporting; restart the window so a brief dropout during
         * spin-up does not accumulate towards a fault. */
        commanded_since = now;
        if (atomic_exchange_explicit(&s_feedback_fault, false, memory_order_relaxed)) {
            ESP_LOGI(TAG, "Weapon feedback fault cleared");
        }
        return;
    }

    if ((now - commanded_since) >= pdMS_TO_TICKS(WEAPON_FEEDBACK_FAULT_MS) &&
        !atomic_exchange_explicit(&s_feedback_fault, true, memory_order_relaxed)) {
        ESP_LOGE(TAG, "WEAPON FEEDBACK FAULT: commanded %.0f%% for %d ms with no Hall edge. "
                      "Holding integrator, running open-loop feed-forward.",
                 output, WEAPON_FEEDBACK_FAULT_MS);
    }
}

/* --------------------------------------------------------------------------
 * Battery sag
 *
 * Disabled unless WEAPON_BATTERY_CELLS is set, because a cut threshold that
 * does not match the actual pack is worse than no threshold at all: too high
 * and the weapon drops out mid-match, too low and it never fires.
 * -------------------------------------------------------------------------- */
static void update_battery(void)
{
#if WEAPON_BATTERY_CELLS > 0
    static int low_samples = 0;

    float v = power_sensor_get_voltage();
    atomic_store_explicit(&s_battery_v, v, memory_order_relaxed);

    if (isnan(v)) {
        /* No usable reading. Do not inhibit on missing data — that would cut
         * the weapon every time an I2C read glitches. */
        low_samples = 0;
        return;
    }

    const float cut_v = WEAPON_BATTERY_CELLS * WEAPON_BATTERY_CUT_V_PER_CELL;

    if (v < cut_v) {
        if (low_samples < WEAPON_BATTERY_SAG_SAMPLES) {
            low_samples++;
        }
    } else if (v > cut_v + WEAPON_BATTERY_RECOVER_V) {
        low_samples = 0;
    }

    bool inhibit = (low_samples >= WEAPON_BATTERY_SAG_SAMPLES);
    if (inhibit != atomic_exchange_explicit(&s_weapon_inhibit, inhibit, memory_order_relaxed)) {
        if (inhibit) {
            ESP_LOGE(TAG, "BATTERY SAG: %.2f V below %.2f V for %d ms — cutting weapon",
                     v, cut_v, WEAPON_BATTERY_SAG_SAMPLES * MONITOR_PERIOD_MS);
        } else {
            ESP_LOGW(TAG, "Battery recovered: %.2f V — weapon re-enabled", v);
        }
    }
#else
    atomic_store_explicit(&s_battery_v, power_sensor_get_voltage(), memory_order_relaxed);
#endif
}

static void task_safety(void *pvParameters)
{
    atomic_store_explicit(&s_battery_v, NAN, memory_order_relaxed);
    TickType_t wake = xTaskGetTickCount();

    while (1) {
        vTaskDelayUntil(&wake, pdMS_TO_TICKS(MONITOR_PERIOD_MS));
        update_feedback_fault(xTaskGetTickCount());
        update_battery();
    }
}

void safety_monitor_init(void)
{
#if WEAPON_BATTERY_CELLS > 0
    ESP_LOGI(TAG, "Battery monitor enabled: %dS pack, weapon cut below %.2f V",
             WEAPON_BATTERY_CELLS,
             WEAPON_BATTERY_CELLS * WEAPON_BATTERY_CUT_V_PER_CELL);
#else
    ESP_LOGW(TAG, "Battery monitor DISABLED — set WEAPON_BATTERY_CELLS in robot_config.h");
#endif
    xTaskCreatePinnedToCore(task_safety, "task_safety", 3072, NULL, 1, NULL, 1);
}
