#include "weapon_controller.h"
#include "encoder_driver.h"
#include "motor_driver.h"
#include "esp_timer.h"

static float   s_integral  = 0.0f;
static int64_t s_last_time = 0;

void weapon_controller_init(void)
{
    s_last_time = esp_timer_get_time();
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

    float error = WEAPON_TARGET_RPM - encoder_get_rpm();

    s_integral += error * dt;

    // Anti-windup: clamp integral so WEAPON_KI*integral never exceeds throttle range
    if (WEAPON_KI != 0.0f) {
        float max_integral = 100.0f / WEAPON_KI;
        if (s_integral >  max_integral) s_integral =  max_integral;
        if (s_integral < -max_integral) s_integral = -max_integral;
    }

    float output = WEAPON_KP * error + WEAPON_KI * s_integral;

    if (output >  100.0f) output =  100.0f;
    if (output < -100.0f) output = -100.0f;

    motor_set_throttle(MOTOR_WEAPON, (int)output);
}
