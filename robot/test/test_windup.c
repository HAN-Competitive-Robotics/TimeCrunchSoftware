/* Anti-windup behaviour with NON-ZERO gains.
 *
 * Built separately with -DWEAPON_KP/-DWEAPON_KI so the saturated path is
 * actually exercised. The shipped gains are zero, which makes the windup
 * tests in test_weapon.c vacuous; this is the file that proves the scheme.
 *
 * The scheme under test is conditional integration: the integral is only
 * accepted when the resulting command is inside the actuator range, or when
 * the error is pushing back out of the limit it is already against. */

#include <stdio.h>
#include <math.h>
#include "stubs.h"
#include "motor_driver.h"
#include "weapon_controller.h"
#include "hall_sensor.h"

int64_t g_now_us          = 0;
int     g_last_weapon_cmd = 0;
float   g_fake_rpm        = 0.0f;
bool    g_fake_fresh      = false;
bool    g_fake_fault      = false;

void  motor_set_throttle(motor_t m, int pct) { if (m == MOTOR_WEAPON) g_last_weapon_cmd = pct; }
float hall_sensor_get_rpm(void)              { return g_fake_rpm; }
bool  hall_sensor_signal_fresh(void)         { return g_fake_fresh; }
uint32_t hall_sensor_get_edge_count(void)    { return 0; }
void  hall_sensor_init(void)                 {}
bool  safety_weapon_feedback_fault(void)     { return g_fake_fault; }
bool  safety_weapon_inhibited(void)          { return false; }
float safety_get_battery_voltage(void)       { return 16.0f; }
void  safety_monitor_init(void)              {}

static int failures = 0;
static void check(const char *name, bool ok, const char *detail)
{
    printf("%-58s %s   %s\n", name, ok ? "PASS" : "FAIL", detail ? detail : "");
    if (!ok) failures++;
}
static void step(void) { g_now_us += 10000; weapon_controller_update(); }

int main(void)
{
    printf("\nanti-windup tests  (KP=%.4f KI=%.4f FF=%.0f)\n", WEAPON_KP, WEAPON_KI, WEAPON_FF);
    printf("--------------------------------------------------------------------------\n");

    char buf[192];

    /* ---------------------------------------------------------------- */
    /* Saturation: hold the weapon far below target so the command pins  */
    /* at 100% for a long time, then check the integral did not run away.*/
    /* ---------------------------------------------------------------- */
    weapon_controller_init();
    weapon_controller_set_reverse_flag(1);
    weapon_controller_set_target_rpm(WEAPON_ATTACK_RPM);
    g_fake_fault = false; g_fake_fresh = true;
    g_fake_rpm   = 0.0f;                     /* huge positive error, output saturates high */

    for (int i = 0; i < 1000; i++) step();   /* 10 seconds pinned at the limit */

    weapon_telemetry_t sat; weapon_controller_get_telemetry(&sat);
    float bound = (WEAPON_KI != 0.0f) ? (100.0f - WEAPON_FF) / WEAPON_KI : 0.0f;
    snprintf(buf, sizeof buf, "integral=%.2f, bound=%.2f, output=%.1f%%", sat.integral, bound, sat.output);
    check("integral stays within the KI*I <= throttle-range bound",
          fabsf(sat.integral) <= bound + 1e-3f, buf);
    /* Conditional integration parks the integral exactly at the edge of the
     * actuator range rather than pushing through it, so the steady command
     * sits just under 100% rather than pinned at it. That is the scheme
     * working, not a shortfall: the stored integral is the largest value that
     * still yields an in-range command. */
    check("output drives to the top of the actuator range",
          sat.output >= 98.0f && sat.output <= 100.0f, buf);
    check("integral parked at the saturation edge, not beyond it",
          fabsf(WEAPON_FF + WEAPON_KP * sat.error + WEAPON_KI * sat.integral - sat.output) < 0.01f, buf);

    /* ---------------------------------------------------------------- */
    /* Recovery: the real test. Bring RPM above target and count how     */
    /* many steps until the controller backs off. A wound-up integrator  */
    /* would keep the throttle pinned for a long time after the error    */
    /* changed sign; that delay is exactly what anti-windup removes.     */
    /* ---------------------------------------------------------------- */
    g_fake_rpm = WEAPON_ATTACK_RPM + 1500.0f;   /* now overspeed: error is negative */

    int steps_to_back_off = -1;
    for (int i = 0; i < 1000; i++) {
        step();
        weapon_telemetry_t t; weapon_controller_get_telemetry(&t);
        if (t.output < 99.9f) { steps_to_back_off = i + 1; break; }
    }

    snprintf(buf, sizeof buf, "backed off after %d steps (%d ms)",
             steps_to_back_off, steps_to_back_off * 10);
    check("controller responds promptly once the error changes sign",
          steps_to_back_off >= 0 && steps_to_back_off <= 5, buf);

    /* ---------------------------------------------------------------- */
    /* Steady state: at target, output should settle near feed-forward.  */
    /* ---------------------------------------------------------------- */
    weapon_controller_init();
    weapon_controller_set_reverse_flag(1);
    weapon_controller_set_target_rpm(WEAPON_ATTACK_RPM);
    g_fake_rpm = WEAPON_ATTACK_RPM;             /* zero error */
    for (int i = 0; i < 200; i++) step();

    weapon_telemetry_t ss; weapon_controller_get_telemetry(&ss);
    snprintf(buf, sizeof buf, "output=%.2f%% error=%.1f integral=%.4f", ss.output, ss.error, ss.integral);
    check("zero error holds the output at the feed-forward baseline",
          fabsf(ss.output - WEAPON_FF) < 0.01f, buf);

    /* ---------------------------------------------------------------- */
    /* A feedback fault mid-flight must dump the integral immediately.   */
    /* ---------------------------------------------------------------- */
    g_fake_rpm = 0.0f;                           /* drive it into saturation again */
    for (int i = 0; i < 300; i++) step();
    g_fake_fault = true; g_fake_fresh = false;
    step();

    weapon_telemetry_t f; weapon_controller_get_telemetry(&f);
    snprintf(buf, sizeof buf, "output=%.1f%% integral=%.4f feedback_ok=%d",
             f.output, f.integral, (int)f.feedback_ok);
    check("fault raised while saturated drops straight to feed-forward",
          fabsf(f.output - WEAPON_FF) < 0.001f && fabsf(f.integral) < 1e-6f, buf);

    printf("--------------------------------------------------------------------------\n");
    printf("%s (%d failure%s)\n\n", failures ? "FAILURES" : "ALL PASS", failures, failures == 1 ? "" : "s");
    return failures != 0;
}
