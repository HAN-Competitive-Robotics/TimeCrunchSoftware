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

/* ---- hardware ------------------------------------------------------------ */
#define WEAPON_GPIO       21

/* ---- PWM timing ---------------------------------------------------------- */
#define PWM_RESOLUTION_HZ 1000000   /* 1 MHz → 1 tick = 1 µs               */
#define PWM_PERIOD_TICKS  20000     /* 20 ms period → 50 Hz                 */
#define PWM_NEUTRAL       1500      /* 1500 µs  ESC neutral / stopped      */
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

/* Set throttle 0-100 → maps to neutral(1500µs) .. full fwd(2000µs) */
static void pwm_set_throttle(int pct)
{
    if (pct < 0)   pct = 0;
    if (pct > 100) pct = 100;
    uint32_t us = (uint32_t)(PWM_NEUTRAL + pct * (PWM_FULL_FWD - PWM_NEUTRAL) / 100);
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

    /* Full brake */
    pwm_set_us(PWM_FULL_BRK);
    printf("\nSTEP 4  Signal → FULL BRAKE (%d µs)\n", PWM_FULL_BRK);
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
    printf("Type 0-100 and press Enter to set throttle %%.\n");
    printf("0 = stopped (neutral), 100 = full speed.\n\n");

    char    buf[8];
    uint8_t idx = 0;
    uint8_t c   = 0;
    int     cur = 0;

    while (1) {
        if (uart_read_bytes(UART_NUM_0, &c, 1, portMAX_DELAY) != 1) continue;

        if (c == '\r' || c == '\n') {
            if (idx == 0) continue;
            buf[idx] = '\0';
            idx = 0;

            int pct = atoi(buf);
            if (pct < 0)   pct = 0;
            if (pct > 100) pct = 100;

            pwm_set_throttle(pct);
            cur = pct;

            uint32_t us = (uint32_t)(PWM_NEUTRAL + pct * (PWM_FULL_FWD - PWM_NEUTRAL) / 100);
            printf("Throttle: %3d%%  (%lu µs)\n", cur, (unsigned long)us);
        } else if ((c == 8 || c == 127) && idx > 0) {
            idx--;
        } else if (idx < (uint8_t)(sizeof(buf) - 1) && c >= '0' && c <= '9') {
            buf[idx++] = (char)c;
        }
    }
}

#endif
