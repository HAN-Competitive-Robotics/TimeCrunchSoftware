#include "motor_driver.h"
#include "tempsensor_driver.h"
#include "driver/mcpwm_prelude.h"
#include <math.h>
#include <stdatomic.h>
#include "esp_log.h"

#define MOTOR_TEMP_LIMIT_C       100.0f
#define MOTOR_TEMP_HYSTERESIS_C   10.0f  // re-enable after temp drops below (limit - hysteresis)

static const char *TAG = "MOTOR";

#define MCPWM_GROUP          0
#define MCPWM_RESOLUTION_HZ  1000000   // 1 MHz -> 1 tick = 1 us
#define MCPWM_PERIOD_TICKS   20000     // 20 ms period -> 50 Hz

#define PWM_TICKS_MIN     ((uint32_t)(0.05f  * MCPWM_PERIOD_TICKS))  // 1000 us (throttle -100, full brake)
#define PWM_TICKS_MAX     ((uint32_t)(0.10f  * MCPWM_PERIOD_TICKS))  // 2000 us (throttle +100, full forward)
#define PWM_TICKS_NEUTRAL ((uint32_t)(0.075f * MCPWM_PERIOD_TICKS))  // 1500 us (throttle 0, neutral — ESC arms here)

static mcpwm_cmpr_handle_t s_comparators[MOTOR_COUNT];

// Persistent thermal cutoff flags — latched on overtemp, cleared with hysteresis.
// Written from task_temp (Core 1), read from task_core0 and task_core1.
// _Atomic bool gives sequentially consistent loads/stores across both cores.
static _Atomic bool s_thermal_cutoff[MOTOR_COUNT];

static const int motor_pins[MOTOR_COUNT] = {
    [MOTOR_RIGHT_WHEEL] = MOTOR_PIN_RIGHT_WHEEL,
    [MOTOR_LEFT_WHEEL]  = MOTOR_PIN_LEFT_WHEEL,
    [MOTOR_WEAPON]      = MOTOR_PIN_WEAPON,
};

// Maps a sensor index to its motor index. Keeps motor_safety_check correct
// even if enum ordering ever changes.
static const motor_t sensor_to_motor[TEMP_COUNT] = {
    [TEMP_LEFT_WHEEL]  = MOTOR_LEFT_WHEEL,
    [TEMP_RIGHT_WHEEL] = MOTOR_RIGHT_WHEEL,
    [TEMP_WEAPON]      = MOTOR_WEAPON,
};

// Applies PWM ticks directly without consulting the thermal gate.
// Only call from motor_safety_check to enforce a hard-stop under cutoff.
static void apply_throttle_direct(motor_t motor, int throttle)
{
    if (throttle < -100) throttle = -100;
    if (throttle >  100) throttle =  100;
    uint32_t ticks = PWM_TICKS_MIN +
        (uint32_t)((throttle + 100) * (PWM_TICKS_MAX - PWM_TICKS_MIN) / 200);
    mcpwm_comparator_set_compare_value(s_comparators[motor], ticks);
}

void motor_driver_init(void)
{
    for (int i = 0; i < MOTOR_COUNT; i++) {
        atomic_store(&s_thermal_cutoff[i], false);
    }

    mcpwm_timer_handle_t timer;
    mcpwm_timer_config_t timer_config = {
        .group_id      = MCPWM_GROUP,
        .clk_src       = MCPWM_TIMER_CLK_SRC_DEFAULT,
        .resolution_hz = MCPWM_RESOLUTION_HZ,
        .count_mode    = MCPWM_TIMER_COUNT_MODE_UP,
        .period_ticks  = MCPWM_PERIOD_TICKS,
    };
    ESP_ERROR_CHECK(mcpwm_new_timer(&timer_config, &timer));

    for (int i = 0; i < MOTOR_COUNT; i++) {
        mcpwm_oper_handle_t oper;
        mcpwm_operator_config_t oper_config = {
            .group_id = MCPWM_GROUP,
        };
        ESP_ERROR_CHECK(mcpwm_new_operator(&oper_config, &oper));
        ESP_ERROR_CHECK(mcpwm_operator_connect_timer(oper, timer));

        mcpwm_comparator_config_t cmp_config = {
            .flags.update_cmp_on_tez = true,
        };
        ESP_ERROR_CHECK(mcpwm_new_comparator(oper, &cmp_config, &s_comparators[i]));
        ESP_ERROR_CHECK(mcpwm_comparator_set_compare_value(s_comparators[i], PWM_TICKS_NEUTRAL));

        mcpwm_gen_handle_t gen;
        mcpwm_generator_config_t gen_config = {
            .gen_gpio_num = motor_pins[i],
        };
        ESP_ERROR_CHECK(mcpwm_new_generator(oper, &gen_config, &gen));

        ESP_ERROR_CHECK(mcpwm_generator_set_action_on_timer_event(gen,
            MCPWM_GEN_TIMER_EVENT_ACTION(MCPWM_TIMER_DIRECTION_UP,
                                         MCPWM_TIMER_EVENT_EMPTY,
                                         MCPWM_GEN_ACTION_HIGH)));
        ESP_ERROR_CHECK(mcpwm_generator_set_action_on_compare_event(gen,
            MCPWM_GEN_COMPARE_EVENT_ACTION(MCPWM_TIMER_DIRECTION_UP,
                                            s_comparators[i],
                                            MCPWM_GEN_ACTION_LOW)));
    }

    ESP_ERROR_CHECK(mcpwm_timer_enable(timer));
    ESP_ERROR_CHECK(mcpwm_timer_start_stop(timer, MCPWM_TIMER_START_NO_STOP));
    ESP_LOGI(TAG, "MCPWM init OK: %d motors on group %d", MOTOR_COUNT, MCPWM_GROUP);
}

void motor_safety_check(void)
{
    for (int i = 0; i < TEMP_COUNT; i++) {
        motor_t m = sensor_to_motor[i];
        float temp = temp_get_temperature((temp_sensor_t)i);

        if (isnan(temp) || temp >= MOTOR_TEMP_LIMIT_C) {
            if (!atomic_load(&s_thermal_cutoff[m])) {
                ESP_LOGW(TAG, "Thermal cutoff latched: motor %d (%.1f °C)", m, temp);
            }
            atomic_store(&s_thermal_cutoff[m], true);
        } else if (temp < MOTOR_TEMP_LIMIT_C - MOTOR_TEMP_HYSTERESIS_C) {
            if (atomic_load(&s_thermal_cutoff[m])) {
                ESP_LOGI(TAG, "Thermal cutoff cleared: motor %d (%.1f °C)", m, temp);
            }
            atomic_store(&s_thermal_cutoff[m], false);
        }

        // Enforce zero throttle directly — bypass the gate in motor_set_throttle
        // so task_core0 cannot override us between now and the next safety check.
        if (atomic_load(&s_thermal_cutoff[m])) {
            apply_throttle_direct(m, 0);
        }
    }
}

void motor_set_throttle(motor_t motor, int throttle)
{
    // Hard gate: reject any command while thermal cutoff is active.
    // Written by task_temp, read here from task_core0 and task_core1.
    if (atomic_load(&s_thermal_cutoff[motor])) {
        return;
    }
    apply_throttle_direct(motor, throttle);
}
