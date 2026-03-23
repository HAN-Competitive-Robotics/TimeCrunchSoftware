#include "motor_driver.h"
#include "tempsensor_driver.h"
#include "driver/mcpwm_prelude.h"
#define MOTOR_TEMP_LIMIT_C  100.0f

#define MCPWM_GROUP          0
#define MCPWM_RESOLUTION_HZ  1000000   // 1 MHz -> 1 tick = 1 us
#define MCPWM_PERIOD_TICKS   20000     // 20 ms period -> 50 Hz

#define PWM_TICKS_MIN  ((uint32_t)(0.10f * MCPWM_PERIOD_TICKS))  // 2000 us (throttle -100)
#define PWM_TICKS_MAX  ((uint32_t)(0.20f * MCPWM_PERIOD_TICKS))  // 4000 us (throttle +100)

static mcpwm_cmpr_handle_t s_comparators[MOTOR_COUNT];

static const int motor_pins[MOTOR_COUNT] = {
    [MOTOR_RIGHT_WHEEL] = MOTOR_PIN_RIGHT_WHEEL,
    [MOTOR_LEFT_WHEEL]  = MOTOR_PIN_LEFT_WHEEL,
    [MOTOR_WEAPON]      = MOTOR_PIN_WEAPON,
};

void motor_driver_init(void)
{
    mcpwm_timer_handle_t timer;
    mcpwm_timer_config_t timer_config = {
        .group_id      = MCPWM_GROUP,
        .clk_src       = MCPWM_TIMER_CLK_SRC_DEFAULT,
        .resolution_hz = MCPWM_RESOLUTION_HZ,
        .count_mode    = MCPWM_TIMER_COUNT_MODE_UP,
        .period_ticks  = MCPWM_PERIOD_TICKS,
    };
    mcpwm_new_timer(&timer_config, &timer);

    for (int i = 0; i < MOTOR_COUNT; i++) {
        mcpwm_oper_handle_t oper;
        mcpwm_operator_config_t oper_config = {
            .group_id = MCPWM_GROUP,
        };
        mcpwm_new_operator(&oper_config, &oper);
        mcpwm_operator_connect_timer(oper, timer);

        mcpwm_comparator_config_t cmp_config = {
            .flags.update_cmp_on_tez = true,
        };
        mcpwm_new_comparator(oper, &cmp_config, &s_comparators[i]);
        mcpwm_comparator_set_compare_value(s_comparators[i], PWM_TICKS_MIN);

        mcpwm_gen_handle_t gen;
        mcpwm_generator_config_t gen_config = {
            .gen_gpio_num = motor_pins[i],
        };
        mcpwm_new_generator(oper, &gen_config, &gen);

        // Set high at start of period, set low on comparator match
        mcpwm_generator_set_action_on_timer_event(gen,
            MCPWM_GEN_TIMER_EVENT_ACTION(MCPWM_TIMER_DIRECTION_UP,
                                         MCPWM_TIMER_EVENT_EMPTY,
                                         MCPWM_GEN_ACTION_HIGH));
        mcpwm_generator_set_action_on_compare_event(gen,
            MCPWM_GEN_COMPARE_EVENT_ACTION(MCPWM_TIMER_DIRECTION_UP,
                                            s_comparators[i],
                                            MCPWM_GEN_ACTION_LOW));
    }

    mcpwm_timer_enable(timer);
    mcpwm_timer_start_stop(timer, MCPWM_TIMER_START_NO_STOP);
}

void motor_safety_check(void)
{
    // motor_t and temp_sensor_t share the same indices intentionally
    for (int i = 0; i < MOTOR_COUNT; i++) {
        float temp = temp_get_temperature((temp_sensor_t)i);
        if (temp >= MOTOR_TEMP_LIMIT_C) {
            motor_set_throttle((motor_t)i, 0);
        }
    }
}

void motor_set_throttle(motor_t motor, int throttle)
{
    if (throttle < -100) throttle = -100;
    if (throttle >  100) throttle = 100;

    // Map [-100, 100] -> [PWM_TICKS_MIN, PWM_TICKS_MAX]
    uint32_t ticks = PWM_TICKS_MIN + (uint32_t)((throttle + 100) * (PWM_TICKS_MAX - PWM_TICKS_MIN) / 200);
    mcpwm_comparator_set_compare_value(s_comparators[motor], ticks);
}
