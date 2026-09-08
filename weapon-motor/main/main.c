/*
 * Weapon motor utility firmware  standalone ESP-IDF project.
 *
 * Use the flash script to pick a mode:
 *   python scripts/flash.py   →  choose option 4 (CALIBRATE) or 5 (TEST)
 *
 * For manual idf.py use, pass the mode as a cmake argument:
 *   idf.py -B build_calibrate -DWEAPON_MODE=MODE_CALIBRATE flash monitor
 *   idf.py -B build_test      -DWEAPON_MODE=MODE_TEST      flash monitor
 *
 * Modes:
 *   MODE_CALIBRATE   serial-guided 8BL150 throttle range calibration (do once)
 *   MODE_TEST        type 0-100 in serial monitor to spin the weapon
 */
#if !defined(MODE_CALIBRATE) && !defined(MODE_TEST)
#error "No mode set  use flash.py or pass -DWEAPON_MODE=MODE_CALIBRATE / MODE_TEST to idf.py"
#endif

#include <stdio.h>
#include <stdlib.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "driver/mcpwm_prelude.h"
#include "driver/uart.h"
#include "esp_err.h"
#include "esp_timer.h"

/* ---- hardware ------------------------------------------------------------ */
#define WEAPON_GPIO       21

/* ---- PWM timing ---------------------------------------------------------- */
#define PWM_RESOLUTION_HZ 1000000   /* 1 MHz → 1 tick = 1 µs               */
#define PWM_PERIOD_TICKS  20000     /* 20 ms period → 50 Hz                 */
#define PWM_NEUTRAL       1500      /* 1500 µs  ESC neutral / stopped      */

/* --------------------------------------------------------------------------
 * Deadman timeout (MODE_TEST)
 * --------------------------------------------------------------------------
 * This firmware spins a weapon disc from a serial prompt. If the USB cable is
 * pulled, the terminal is closed, or the laptop sleeps, the throttle would
 * otherwise stay exactly where it was and the disc would keep spinning with
 * nobody able to stop it.
 *
 * The ESP32 cannot detect the disconnection itself: UART0 sits behind the
 * CP2102 bridge, whose DTR/RTS lines are wired to EN/BOOT for auto-reset and
 * are not readable from application code. So instead of detecting the cable,
 * require proof that somebody is still there.
 *
 * While the throttle is non-zero, any keypress refreshes the timer. Silence
 * for this long ramps back to neutral. A pulled cable, a closed terminal and
 * an unattended bench all look the same from here, which is the point.
 */
#define DEADMAN_TIMEOUT_MS   3000
#define DEADMAN_RAMP_MS       500   /* ease to neutral rather than stepping  */
#define DEADMAN_RAMP_STEPS     20
#define PWM_FULL_FWD      2000      /* 2000 µs  full throttle forward      */
#define PWM_FULL_BRK      1000      /* 1000 µs  full brake                 */

static mcpwm_cmpr_handle_t s_cmp;

static void pwm_init(void)
{
    mcpwm_timer_handle_t timer;
    mcpwm_timer_config_t timer_cfg = {
        .group_id      = 0,
        .clk_src       = MCPWM_TIMER_CLK_SRC_DEFAULT,
        .resolution_hz = PWM_RESOLUTION_HZ,
        .count_mode    = MCPWM_TIMER_COUNT_MODE_UP,
        .period_ticks  = PWM_PERIOD_TICKS,
    };
    ESP_ERROR_CHECK(mcpwm_new_timer(&timer_cfg, &timer));

    mcpwm_oper_handle_t oper;
    mcpwm_operator_config_t oper_cfg = { .group_id = 0 };
    ESP_ERROR_CHECK(mcpwm_new_operator(&oper_cfg, &oper));
    ESP_ERROR_CHECK(mcpwm_operator_connect_timer(oper, timer));

    mcpwm_comparator_config_t cmp_cfg = { .flags.update_cmp_on_tez = true };
    ESP_ERROR_CHECK(mcpwm_new_comparator(oper, &cmp_cfg, &s_cmp));
    ESP_ERROR_CHECK(mcpwm_comparator_set_compare_value(s_cmp, PWM_NEUTRAL));

    mcpwm_gen_handle_t gen;
    mcpwm_generator_config_t gen_cfg = { .gen_gpio_num = WEAPON_GPIO };
    ESP_ERROR_CHECK(mcpwm_new_generator(oper, &gen_cfg, &gen));

    ESP_ERROR_CHECK(mcpwm_generator_set_action_on_timer_event(gen,
        MCPWM_GEN_TIMER_EVENT_ACTION(MCPWM_TIMER_DIRECTION_UP,
                                     MCPWM_TIMER_EVENT_EMPTY,
                                     MCPWM_GEN_ACTION_HIGH)));
    ESP_ERROR_CHECK(mcpwm_generator_set_action_on_compare_event(gen,
        MCPWM_GEN_COMPARE_EVENT_ACTION(MCPWM_TIMER_DIRECTION_UP,
                                        s_cmp,
                                        MCPWM_GEN_ACTION_LOW)));

    ESP_ERROR_CHECK(mcpwm_timer_enable(timer));
    ESP_ERROR_CHECK(mcpwm_timer_start_stop(timer, MCPWM_TIMER_START_NO_STOP));
}

/* Set pulse width in microseconds directly */
static void pwm_set_us(uint32_t us)
{
    if (us < PWM_FULL_BRK) us = PWM_FULL_BRK;
    if (us > PWM_FULL_FWD) us = PWM_FULL_FWD;
    mcpwm_comparator_set_compare_value(s_cmp, us);
}

/* Set throttle -100..100
 *  positive  → forward:  neutral(1500µs) .. full fwd(2000µs)
 *  0         → neutral
 *  negative  → brake/reverse zone: neutral(1500µs) .. full(1000µs)
 *    (ESC decides brake vs reverse based on motor state)
 */
static void pwm_set_throttle(int pct)
{
    if (pct < -100) pct = -100;
    if (pct > 100)  pct = 100;

    uint32_t us;
    if (pct >= 0) {
        us = (uint32_t)(PWM_NEUTRAL + pct * (PWM_FULL_FWD - PWM_NEUTRAL) / 100);
    } else {
        us = (uint32_t)(PWM_NEUTRAL + pct * (PWM_NEUTRAL - PWM_FULL_BRK) / 100);
    }
    pwm_set_us(us);
}

/* ---- serial helper ------------------------------------------------------- */
static void uart_init(void)
{
    ESP_ERROR_CHECK(uart_driver_install(UART_NUM_0, 256, 0, 0, NULL, 0));
}

static void wait_enter(void)
{
    uint8_t c = 0;
    while (c != '\n' && c != '\r')
        uart_read_bytes(UART_NUM_0, &c, 1, portMAX_DELAY);
}

/* =========================================================================
 * MODE_CALIBRATE
 * ========================================================================= */
#if defined(MODE_CALIBRATE)

void app_main(void)
{
    uart_init();
    pwm_init();

    /* Start at neutral so the ESC can arm when battery is connected normally */
    pwm_set_us(PWM_NEUTRAL);

    printf("\n");
    printf("╔══════════════════════════════════════════╗\n");
    printf("║   8BL150 ESC THROTTLE RANGE CALIBRATION  ║\n");
    printf("╚══════════════════════════════════════════╝\n\n");
    printf("Only needed on first use or after factory reset.\n\n");

    printf("STEP 1  Hold the SET button on the ESC.\n");
    printf("        Press ON/OFF to power it on.\n");
    printf("        RED LED flashes → release SET immediately.\n");
    printf("        Press Enter when RED LED is flashing...\n");
    wait_enter();

    /* Neutral */
    pwm_set_us(PWM_NEUTRAL);
    printf("\nSTEP 2  Signal → NEUTRAL (%d µs)\n", PWM_NEUTRAL);
    printf("        Press SET on ESC → GREEN flashes 1×, 1 beep.\n");
    printf("        Press Enter when done...\n");
    wait_enter();

    /* Full throttle */
    pwm_set_us(PWM_FULL_FWD);
    printf("\nSTEP 3  Signal → FULL THROTTLE (%d µs)\n", PWM_FULL_FWD);
    printf("        Press SET on ESC → GREEN flashes 2×, 2 beeps.\n");
    printf("        (Motor will NOT spin  ESC is in calibration mode.)\n");
    printf("        Press Enter when done...\n");
    wait_enter();

    /* Full brake / reverse endpoint */
    pwm_set_us(PWM_FULL_BRK);
    printf("\nSTEP 4  Signal → FULL BRAKE / REVERSE (%d µs)\n", PWM_FULL_BRK);
    printf("        Press SET on ESC → GREEN flashes 3×, 3 beeps.\n");
    printf("        Press Enter when done...\n");
    wait_enter();

    pwm_set_us(PWM_NEUTRAL);
    printf("\n✓  CALIBRATION COMPLETE\n");
    printf("   Calibration is saved on the ESC.\n");
    printf("   You can now flash the normal robot firmware.\n\n");

    while (1) vTaskDelay(pdMS_TO_TICKS(1000));
}

/* =========================================================================
 * MODE_TEST
 * ========================================================================= */
#elif defined(MODE_TEST)

void app_main(void)
{
    uart_init();
    pwm_init();

    pwm_set_us(PWM_NEUTRAL);

    printf("\n");
    printf("╔══════════════════════════════╗\n");
    printf("║   WEAPON ESC TEST            ║\n");
    printf("╚══════════════════════════════╝\n\n");
    printf("Connect battery to ESC. Wait for arming beep.\n");
    printf("Type -100 to 100 and press Enter to set throttle %%.\n");
    printf("  0   = stopped (neutral)\n");
    printf("  100 = full forward\n");
    printf(" -10  = brake (while spinning)\n");
    printf(" -10  = reverse (after motor has stopped)\n");
    printf(" -100 = full brake/reverse\n\n");

    char    buf[16];
    uint8_t idx = 0;
    uint8_t c   = 0;
    int     cur = 0;

    int64_t last_input_us = esp_timer_get_time();

    while (1) {
        /* Poll rather than block forever, so the deadman can expire while no
         * one is typing. */
        int got = uart_read_bytes(UART_NUM_0, &c, 1, pdMS_TO_TICKS(100));

        if (got != 1) {
            if (cur != 0 &&
                (esp_timer_get_time() - last_input_us) > (int64_t)DEADMAN_TIMEOUT_MS * 1000) {
                printf("\n*** DEADMAN: no input for %d ms - ramping to neutral ***\n",
                       DEADMAN_TIMEOUT_MS);
                for (int i = DEADMAN_RAMP_STEPS; i >= 0; i--) {
                    pwm_set_throttle(cur * i / DEADMAN_RAMP_STEPS);
                    vTaskDelay(pdMS_TO_TICKS(DEADMAN_RAMP_MS / DEADMAN_RAMP_STEPS));
                }
                pwm_set_throttle(0);
                cur = 0;
                idx = 0;
                printf("Throttle: 0%% (neutral). Type a value to resume.\n");
                last_input_us = esp_timer_get_time();
            }
            continue;
        }

        last_input_us = esp_timer_get_time();

        if (c == '\r' || c == '\n') {
            if (idx == 0) continue;
            buf[idx] = '\0';
            idx = 0;

            int pct = atoi(buf);
            if (pct < -100) pct = -100;
            if (pct > 100)  pct = 100;

            pwm_set_throttle(pct);
            cur = pct;

            uint32_t us;
            if (pct >= 0) {
                us = (uint32_t)(PWM_NEUTRAL + pct * (PWM_FULL_FWD - PWM_NEUTRAL) / 100);
                printf("Throttle: %3d%%  (%lu µs)\n", cur, (unsigned long)us);
            } else {
                us = (uint32_t)(PWM_NEUTRAL + pct * (PWM_NEUTRAL - PWM_FULL_BRK) / 100);
                printf("Rev/Brk:  %3d%%  (%lu µs)\n", -cur, (unsigned long)us);
            }
        } else if ((c == 8 || c == 127) && idx > 0) {
            idx--;
        } else if (idx < (uint8_t)(sizeof(buf) - 1)) {
            if (c >= '0' && c <= '9') {
                buf[idx++] = (char)c;
            } else if (c == '-' && idx == 0) {
                buf[idx++] = (char)c;
            }
        }
    }
}

#endif
