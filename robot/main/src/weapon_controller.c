#include "weapon_controller.h"
#include "hall_sensor.h"
#include "motor_driver.h"
#include "esp_timer.h"

static float   s_integral   = 0.0f;
static int64_t s_last_time  = 0;
static float   s_target_rpm = WEAPON_ATTACK_RPM;
static int8_t  reverse_flag = 1; // 1 or -1

void weapon_controller_init(void)
{
    s_last_time  = esp_timer_get_time();
    s_target_rpm = WEAPON_ATTACK_RPM;
    s_integral   = 0.0f;
}

void weapon_controller_set_target_rpm(float rpm)
{
    s_target_rpm = rpm;
}

void weapon_controller_set_reverse_flag(int8_t flag) {
    reverse_flag = flag;
}

void weapon_controller_reset(void)
{
    s_integral  = 0.0f;
    s_last_time = esp_timer_get_time();
}

void weapon_controller_update(void)
{
    int64_t now = esp_timer_get_time();
    float dt    = (float)(now - s_last_time) / 1e6f;
    s_last_time = now;

    float error = s_target_rpm - hall_sensor_get_rpm();

    s_integral += error * dt;

    // Anti-windup: clamp integral so WEAPON_KI * integral never exceeds throttle range.
    // When KI=0 clamp to zero so no surprise spike when KI is first tuned to non-zero.
    float max_integral = (WEAPON_KI != 0.0f) ? (100.0f - WEAPON_FF) / WEAPON_KI : 0.0f;
    if (s_integral >  max_integral) s_integral =  max_integral;
    if (s_integral < -max_integral) s_integral = -max_integral;

    float output = WEAPON_FF + WEAPON_KP * error + WEAPON_KI * s_integral;

    // Clamp PI magnitude to [0, 100] before applying direction.
    // reverse_flag (+1 or -1) selects spin direction; output magnitude is always non-negative.
    if (output > 100.0f) output = 100.0f;
    if (output <   0.0f) output =   0.0f;

    motor_set_throttle(MOTOR_WEAPON, (int)output * reverse_flag);
}
