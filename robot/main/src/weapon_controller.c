#include "weapon_controller.h"

#include "hall_sensor.h"
#include "motor_driver.h"
#include "safety_monitor.h"
#include "robot_config.h"   /* WEAPON_HALL_SENSOR_FITTED */
#include "esp_timer.h"

#define OUTPUT_MIN   0.0f
#define OUTPUT_MAX 100.0f

/* Final gate on every commanded output. Applied after the ceiling so that a
 * misconfigured WEAPON_MAX_OUTPUT_PCT still cannot exceed the actuator range. */
static float clamp_output(float output)
{
    if (output > WEAPON_MAX_OUTPUT_PCT) output = WEAPON_MAX_OUTPUT_PCT;
    if (output > OUTPUT_MAX)            output = OUTPUT_MAX;
    if (output < OUTPUT_MIN)            output = OUTPUT_MIN;
    return output;
}

/* Throttle to use when there is no usable RPM feedback.
 *
 * Derived from the commanded target rather than a single constant, so idle and
 * attack stay distinguishable with the loop open. Anything at or above the
 * attack target gets the attack level; any other non-zero command gets idle. */
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

    // Run open-loop when there is no usable RPM. The two ways that happens are
    // NOT the same and must not be treated the same:
    //
    //   - No sensor fitted: open-loop IS the normal, intended mode, so honour
    //     the commanded level. Attack can be full throttle.
    //   - Sensor fitted but silent (fault): speed control has been lost
    //     mid-run, so back off to a conservative feed-forward level rather than
    //     driving the open-loop attack percentage blind. Capped at WEAPON_FF,
    //     so it never exceeds the normal command and idle still stays idle.
    //
    // Either way hold the integrator at zero: closing the loop without feedback
    // lets rpm read 0, makes the error the whole target, and winds the output
    // to saturation on a weapon that may well be spinning.
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

    // Anti-windup by conditional integration.
    //
    // Integrate the candidate step first, then keep it only if the resulting
    // command is inside the actuator range, or if the error is pushing back
    // out of the limit it is already against. An integrator that keeps
    // accumulating while the throttle is pinned at 100% cannot make the
    // weapon spin faster; all it does is store up a delay before the
    // controller can respond to the error changing sign.
    //
    // The magnitude clamp below is kept as a second line of defence so that a
    // single bad dt cannot park the integral somewhere extreme.
    float candidate = s_integral + error * dt;
    float unsat     = WEAPON_FF + WEAPON_KP * error + WEAPON_KI * candidate;

    bool inside      = (unsat > OUTPUT_MIN) && (unsat < OUTPUT_MAX);
    bool unwinding   = (unsat >= OUTPUT_MAX && error < 0.0f) ||
                       (unsat <= OUTPUT_MIN && error > 0.0f);

    if (inside || unwinding) {
        s_integral = candidate;
    }

    // Bound the integral so that KI * integral can never exceed the throttle
    // range on its own. With KI == 0 this collapses to zero, so no integral
    // accumulates while the loop is open and there is no stored surprise the
    // first time KI is tuned to a non-zero value.
    float max_integral = (WEAPON_KI != 0.0f) ? (OUTPUT_MAX - WEAPON_FF) / WEAPON_KI : 0.0f;
    if (s_integral >  max_integral) s_integral =  max_integral;
    if (s_integral < -max_integral) s_integral = -max_integral;

    float output = WEAPON_FF + WEAPON_KP * error + WEAPON_KI * s_integral;

    // Clamp the magnitude before applying direction. reverse_flag (+1/-1)
    // selects spin direction; the PI magnitude is always non-negative.
    output = clamp_output(output);

    publish(s_target_rpm, rpm, error, output, true);
    motor_set_throttle(MOTOR_WEAPON, (int)output * reverse_flag);
}
