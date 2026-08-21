/* Host harness for weapon_controller.c.
 *
 * Compiles the REAL controller source against stubs so the behaviour under
 * test is the shipped logic, not a re-implementation of it. */

#include <stdio.h>
#include <math.h>
#include <string.h>
#include "stubs.h"
#include "motor_driver.h"
#include "weapon_controller.h"
#include "hall_sensor.h"

int64_t g_now_us       = 0;
int     g_last_weapon_cmd = 0;
float   g_fake_rpm     = 0.0f;
bool    g_fake_fresh   = false;
bool    g_fake_fault   = false;

void motor_set_throttle(motor_t m, int pct) { if (m == MOTOR_WEAPON) g_last_weapon_cmd = pct; }
float hall_sensor_get_rpm(void)        { return g_fake_rpm; }
bool  hall_sensor_signal_fresh(void)   { return g_fake_fresh; }
uint32_t hall_sensor_get_edge_count(void) { return 0; }
void  hall_sensor_init(void)           {}
bool  safety_weapon_feedback_fault(void) { return g_fake_fault; }
bool  safety_weapon_inhibited(void)      { return false; }
float safety_get_battery_voltage(void)   { return 16.0f; }
void  safety_monitor_init(void)          {}

static int failures = 0;
static void check(const char *name, bool ok, const char *detail)
{
    printf("%-58s %s   %s\n", name, ok ? "PASS" : "FAIL", detail ? detail : "");
    if (!ok) failures++;
}

/* Advance one 10 ms control step. */
static void step(void) { g_now_us += 10000; weapon_controller_update(); }

/* ------------------------------------------------------------------ */
/* 1. RPM resolution: the reason the loop could not be closed.         */
/* ------------------------------------------------------------------ */
static void test_rpm_resolution(void)
{
    const float ppr = (float)HALL_SENSOR_PULSES_PER_REV;

    /* Old scheme: count edges in a 20 ms window. */
    float old_step = 60.0f / 0.020f / ppr;

    /* New scheme: time the interval between edges, 1 us timer resolution. */
    float p_at_5000 = 60.0e6f / (5000.0f * ppr);         /* microseconds */
    float rpm_a = 60.0e6f / (p_at_5000 * ppr);
    float rpm_b = 60.0e6f / ((p_at_5000 + 1.0f) * ppr);
    float new_step = fabsf(rpm_a - rpm_b);

    char buf[160];
    snprintf(buf, sizeof buf, "old=%.0f RPM/count, new=%.2f RPM/us at 5000 RPM (%.0fx better)",
             old_step, new_step, old_step / new_step);
    check("RPM resolution is usable for closed-loop control",
          new_step < 5.0f && old_step > 1000.0f, buf);

    snprintf(buf, sizeof buf, "period at 5000 RPM = %.0f us", p_at_5000);
    check("5000 RPM target is exactly representable", fabsf(p_at_5000 - 6000.0f) < 0.5f, buf);

    /* The old grid could not represent 5000 RPM at all. */
    float lower = floorf(5000.0f / old_step) * old_step;
    float upper = lower + old_step;
    snprintf(buf, sizeof buf, "old grid straddles it: %.0f / %.0f", lower, upper);
    check("5000 RPM was NOT representable on the old grid",
          fabsf(lower - 5000.0f) > 1.0f && fabsf(upper - 5000.0f) > 1.0f, buf);
}

/* ------------------------------------------------------------------ */
/* 2. Zero gains reproduce the historical open-loop behaviour.         */
/* ------------------------------------------------------------------ */
static void test_zero_gains_are_open_loop(void)
{
    weapon_controller_init();
    weapon_controller_set_reverse_flag(1);
    weapon_controller_set_target_rpm(WEAPON_ATTACK_RPM);
    g_fake_fault = false; g_fake_fresh = true; g_fake_rpm = 0.0f;

    for (int i = 0; i < 200; i++) step();

    weapon_telemetry_t t; weapon_controller_get_telemetry(&t);
    char buf[128];
    snprintf(buf, sizeof buf, "output=%.1f%% integral=%.3f", t.output, t.integral);
    check("KP=KI=0 gives exactly the feed-forward baseline",
          fabsf(t.output - WEAPON_FF) < 0.001f, buf);
    check("no integral accumulates while the loop is open",
          fabsf(t.integral) < 1e-6f, buf);
}

/* ------------------------------------------------------------------ */
/* 3. Feedback fault must NOT wind up to full throttle.                */
/*    This is the dangerous case the fault handling exists to prevent. */
/* ------------------------------------------------------------------ */
static void test_fault_does_not_wind_up(void)
{
    weapon_controller_init();
    weapon_controller_set_reverse_flag(1);
    weapon_controller_set_target_rpm(WEAPON_ATTACK_RPM);

    /* Sensor is dead: reads 0 RPM forever while the weapon is commanded. */
    g_fake_fault = true; g_fake_fresh = false; g_fake_rpm = 0.0f;

    for (int i = 0; i < 500; i++) step();   /* 5 seconds */

    weapon_telemetry_t t; weapon_controller_get_telemetry(&t);
    char buf[128];
    snprintf(buf, sizeof buf, "output=%.1f%% (feed-forward is %.0f%%), integral=%.3f",
             t.output, WEAPON_FF, t.integral);
    check("dead sensor degrades to feed-forward, NOT full throttle",
          fabsf(t.output - WEAPON_FF) < 0.001f && t.output < 99.0f, buf);
    check("integrator is held at zero during a feedback fault",
          fabsf(t.integral) < 1e-6f, buf);
    check("telemetry reports the loop as open", t.feedback_ok == false, "");
}

/* ------------------------------------------------------------------ */
/* 4. Command range and direction stay bounded.                        */
/* ------------------------------------------------------------------ */
static void test_output_bounds(void)
{
    weapon_controller_init();
    weapon_controller_set_target_rpm(WEAPON_ATTACK_RPM);
    g_fake_fault = false; g_fake_fresh = true;

    bool ok = true;
    for (int rev = 0; rev < 2; rev++) {
        weapon_controller_set_reverse_flag(rev ? -1 : 1);
        for (float rpm = 0.0f; rpm <= 12000.0f; rpm += 250.0f) {
            g_fake_rpm = rpm;
            step();
            if (g_last_weapon_cmd > 100 || g_last_weapon_cmd < -100) ok = false;
        }
    }
    check("commanded throttle always stays within -100..100", ok, "swept 0-12000 RPM, both directions");
}

/* ------------------------------------------------------------------ */
/* 5. reset() clears state so a re-arm cannot resume mid-integral.     */
/* ------------------------------------------------------------------ */
static void test_reset_clears_state(void)
{
    weapon_controller_init();
    weapon_controller_set_reverse_flag(1);
    g_fake_fault = false; g_fake_fresh = true; g_fake_rpm = 1000.0f;
    for (int i = 0; i < 50; i++) step();

    weapon_controller_reset();
    weapon_telemetry_t before; weapon_controller_get_telemetry(&before);

    /* A long gap with the weapon off, then re-arm. dt must not blow up. */
    g_now_us += 30 * 1000000LL;
    step();

    weapon_telemetry_t t; weapon_controller_get_telemetry(&t);
    char buf[128];
    snprintf(buf, sizeof buf, "integral after 30 s gap = %.4f", t.integral);
    check("a 30 s off period cannot inject a huge dt into the integral",
          fabsf(t.integral) <= fabsf(WEAPON_MAX_DT_S * WEAPON_ATTACK_RPM) + 1e-3f, buf);
    check("output after re-arm is still bounded",
          t.output >= 0.0f && t.output <= 100.0f, "");
}

int main(void)
{
    printf("\nweapon_controller host tests  (KP=%.3f KI=%.3f FF=%.0f)\n", WEAPON_KP, WEAPON_KI, WEAPON_FF);
    printf("--------------------------------------------------------------------------\n");
    test_rpm_resolution();
    test_zero_gains_are_open_loop();
    test_fault_does_not_wind_up();
    test_output_bounds();
    test_reset_clears_state();
    printf("--------------------------------------------------------------------------\n");
    printf("%s (%d failure%s)\n\n", failures ? "FAILURES" : "ALL PASS", failures, failures == 1 ? "" : "s");
    return failures != 0;
}
