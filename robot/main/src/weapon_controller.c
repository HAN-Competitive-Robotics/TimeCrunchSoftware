#include "weapon_controller.h"

#include "hall_sensor.h"
#include "motor_driver.h"
#include "safety_monitor.h"
#include "robot_config.h"   /* WEAPON_HALL_SENSOR_FITTED */
#include "esp_timer.h"

#define OUTPUT_MIN   0.0f
#define OUTPUT_MAX 100.0f

/* Final gate: ceiling, then actuator range. */
static float clamp_output(float output)
{
    if (output > WEAPON_MAX_OUTPUT_PCT) output = WEAPON_MAX_OUTPUT_PCT;
    if (output > OUTPUT_MAX)            output = OUTPUT_MAX;
    if (output < OUTPUT_MIN)            output = OUTPUT_MIN;
    return output;
}

/* Open-loop throttle from the target, so idle and attack stay distinct. */
static float open_loop_output(float target_rpm)
{
    if (target_rpm <= 0.0f)                 return 0.0f;
    if (target_rpm >= WEAPON_ATTACK_RPM)    return WEAPON_OL_ATTACK_PCT;
    return WEAPON_OL_IDLE_PCT;
}

static float   s_integral     = 0.0f;
static int64_t s_last_time    = 0;
static float   s_target_rpm   = WEAPON_ATTACK_RPM;
static int8_t  reverse_flag   = 1; // 1 or -1
static float   s_last_output  = 0.0f;

static weapon_telemetry_t s_telemetry = {0};

void weapon_controller_init(void)
{
    s_last_time   = esp_timer_get_time();
    s_target_rpm  = WEAPON_ATTACK_RPM;
    s_integral    = 0.0f;
    s_last_output = 0.0f;
}

void weapon_controller_set_target_rpm(float rpm)
{
    s_target_rpm = rpm;
}

void weapon_controller_set_reverse_flag(int8_t flag)
{
    reverse_flag = flag;
}

void weapon_controller_reset(void)
{
    s_integral    = 0.0f;
    s_last_time   = esp_timer_get_time();
    s_last_output = 0.0f;
}

float weapon_controller_get_output(void)
{
    return s_last_output;
}

void weapon_controller_get_telemetry(weapon_telemetry_t *out)
{
    if (out) *out = s_telemetry;
}

static void publish(float target, float rpm, float error, float output, bool feedback_ok)
{
    s_telemetry.target_rpm   = target;
    s_telemetry.measured_rpm = rpm;
    s_telemetry.error        = error;
    s_telemetry.integral     = s_integral;
    s_telemetry.output       = output;
    s_telemetry.feedback_ok  = feedback_ok;
    s_last_output            = output;
}

void weapon_controller_test(int pct)
{
    int8_t dir = (pct < 0) ? -1 : 1;
    float  mag = clamp_output((float)(pct < 0 ? -pct : pct));
    s_integral  = 0.0f;
    s_last_time = esp_timer_get_time();
    publish(0.0f, 0.0f, 0.0f, mag, false);
    motor_set_throttle(MOTOR_WEAPON, (int)mag * dir);
}

void weapon_controller_update(void)
{
    int64_t now = esp_timer_get_time();
    float   dt  = (float)(now - s_last_time) / 1e6f;
    s_last_time = now;

    if (dt <= 0.0f)            dt = 0.0f;
    if (dt > WEAPON_MAX_DT_S)  dt = WEAPON_MAX_DT_S;

    // Open-loop with no usable RPM. Two distinct cases:
    //   - No sensor fitted: normal mode, honour the commanded level.
    //   - Sensor fitted but silent (fault): back off to WEAPON_FF, don't drive
    //     the attack percent blind.
    // Both hold the integrator at zero (no feedback would else wind it up).
    if (!WEAPON_HALL_SENSOR_FITTED) {
        s_integral = 0.0f;
        float output = clamp_output(open_loop_output(s_target_rpm));
        publish(s_target_rpm, 0.0f, 0.0f, output, false);
        motor_set_throttle(MOTOR_WEAPON, (int)output * reverse_flag);
        return;
    }
    if (safety_weapon_feedback_fault()) {
        s_integral = 0.0f;
        float base = open_loop_output(s_target_rpm);
        if (base > WEAPON_FF) base = WEAPON_FF;   /* conservative on a fault */
        float output = clamp_output(base);
        publish(s_target_rpm, 0.0f, 0.0f, output, false);
        motor_set_throttle(MOTOR_WEAPON, (int)output * reverse_flag);
        return;
    }

    float rpm   = hall_sensor_get_rpm();
    float error = s_target_rpm - rpm;

    // Anti-windup: keep the integrated step only if the command stays in range,
    // or if the error is pushing back out of the limit it's against.
    float candidate = s_integral + error * dt;
    float unsat     = WEAPON_FF + WEAPON_KP * error + WEAPON_KI * candidate;

    bool inside      = (unsat > OUTPUT_MIN) && (unsat < OUTPUT_MAX);
    bool unwinding   = (unsat >= OUTPUT_MAX && error < 0.0f) ||
                       (unsat <= OUTPUT_MIN && error > 0.0f);

    if (inside || unwinding) {
        s_integral = candidate;
    }

    // Bound the integral so KI*integral can't exceed the throttle range alone.
    float max_integral = (WEAPON_KI != 0.0f) ? (OUTPUT_MAX - WEAPON_FF) / WEAPON_KI : 0.0f;
    if (s_integral >  max_integral) s_integral =  max_integral;
    if (s_integral < -max_integral) s_integral = -max_integral;

    float output = WEAPON_FF + WEAPON_KP * error + WEAPON_KI * s_integral;

    // Clamp magnitude before applying direction (reverse_flag is +1/-1).
    output = clamp_output(output);

    publish(s_target_rpm, rpm, error, output, true);
    motor_set_throttle(MOTOR_WEAPON, (int)output * reverse_flag);
}
