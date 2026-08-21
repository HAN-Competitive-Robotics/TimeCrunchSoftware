#include "weapon_controller.h"

#include "hall_sensor.h"
#include "motor_driver.h"
#include "safety_monitor.h"
#include "esp_timer.h"

#define OUTPUT_MIN   0.0f
#define OUTPUT_MAX 100.0f

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

void weapon_controller_update(void)
{
    int64_t now = esp_timer_get_time();
    float   dt  = (float)(now - s_last_time) / 1e6f;
    s_last_time = now;

    if (dt <= 0.0f)            dt = 0.0f;
    if (dt > WEAPON_MAX_DT_S)  dt = WEAPON_MAX_DT_S;

    // Feedback fault: the weapon is being driven but the Hall sensor is not
    // reporting rotation, so measured RPM is not a measurement of anything.
    //
    // Closing the loop anyway is the dangerous case: rpm reads 0, the error
    // becomes the entire target, and the integrator drives the output to
    // saturation on a weapon that may well be spinning. Instead hold the
    // integrator at zero and emit the bare feed-forward term, which is exactly
    // the open-loop behaviour this firmware shipped before the loop existed.
    if (safety_weapon_feedback_fault()) {
        s_integral = 0.0f;
        float output = WEAPON_FF;
        if (output > OUTPUT_MAX) output = OUTPUT_MAX;
        if (output < OUTPUT_MIN) output = OUTPUT_MIN;
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
    if (output > OUTPUT_MAX) output = OUTPUT_MAX;
    if (output < OUTPUT_MIN) output = OUTPUT_MIN;

    publish(s_target_rpm, rpm, error, output, true);
    motor_set_throttle(MOTOR_WEAPON, (int)output * reverse_flag);
}
