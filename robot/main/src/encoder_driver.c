#include "encoder_driver.h"

#include <string.h>
#include <stdatomic.h>
#include "driver/gpio.h"
#include "driver/pulse_cnt.h"
#include "esp_timer.h"
#include "esp_log.h"

#define SAMPLE_INTERVAL_MS  20
#define GLITCH_FILTER_NS    1000

// RPM = count * (60 / sample_interval_s) / pulses_per_rev
#define COUNTS_TO_RPM (60.0f / (SAMPLE_INTERVAL_MS / 1000.0f) / ENCODER_PULSES_PER_REV)

static pcnt_unit_handle_t s_unit = NULL;
static const char *TAG = "ENCODER";

// s_rpm_bits holds the IEEE-754 bit pattern of the RPM float.
// Written by the esp_timer callback (timer service task, Core 0).
// Read by encoder_get_rpm from any task (Core 1 weapon controller).
// _Atomic uint32_t gives sequentially-consistent 32-bit load/store across
// both Xtensa cores without disabling interrupts.
static _Atomic uint32_t s_rpm_bits = 0;

static void rpm_timer_cb(void *arg)
{
    int count = 0;
    pcnt_unit_get_count(s_unit, &count);
    pcnt_unit_clear_count(s_unit);

    if (count < 0) count = 0;
    float rpm = (float)count * COUNTS_TO_RPM;

    uint32_t bits;
    memcpy(&bits, &rpm, sizeof(bits));
    atomic_store_explicit(&s_rpm_bits, bits, memory_order_release);
}

void encoder_driver_init(void)
{
    pcnt_unit_config_t unit_cfg = {
        .high_limit = INT16_MAX,
        .low_limit  = INT16_MIN,
    };
    ESP_ERROR_CHECK(pcnt_new_unit(&unit_cfg, &s_unit));

    pcnt_glitch_filter_config_t filter_cfg = {
        .max_glitch_ns = GLITCH_FILTER_NS,
    };
    ESP_ERROR_CHECK(pcnt_unit_set_glitch_filter(s_unit, &filter_cfg));

    pcnt_chan_config_t chan_cfg = {
        .edge_gpio_num  = ENCODER_GPIO,
        .level_gpio_num = -1,
    };
    pcnt_channel_handle_t chan = NULL;
    ESP_ERROR_CHECK(pcnt_new_channel(s_unit, &chan_cfg, &chan));

    // NPN open-collector output: only sinks to GND, so pull the line high
    // through the internal pull-up. PCNT does not configure this itself.
    ESP_ERROR_CHECK(gpio_set_pull_mode(ENCODER_GPIO, GPIO_PULLUP_ONLY));

    // Bipolar Hall latch toggles on each pole transition; count both edges.
    ESP_ERROR_CHECK(pcnt_channel_set_edge_action(chan,
        PCNT_CHANNEL_EDGE_ACTION_INCREASE,
        PCNT_CHANNEL_EDGE_ACTION_INCREASE));
    ESP_ERROR_CHECK(pcnt_channel_set_level_action(chan,
        PCNT_CHANNEL_LEVEL_ACTION_KEEP,
        PCNT_CHANNEL_LEVEL_ACTION_KEEP));

    ESP_ERROR_CHECK(pcnt_unit_enable(s_unit));
    ESP_ERROR_CHECK(pcnt_unit_clear_count(s_unit));
    ESP_ERROR_CHECK(pcnt_unit_start(s_unit));

    esp_timer_handle_t timer;
    esp_timer_create_args_t timer_args = {
        .callback = rpm_timer_cb,
        .name     = "encoder_rpm",
    };
    ESP_ERROR_CHECK(esp_timer_create(&timer_args, &timer));
    ESP_ERROR_CHECK(esp_timer_start_periodic(timer, SAMPLE_INTERVAL_MS * 1000));

    ESP_LOGI(TAG, "Encoder init OK: GPIO %d, %d pulses/rev",
             ENCODER_GPIO, ENCODER_PULSES_PER_REV);
}

float encoder_get_rpm(void)
{
    uint32_t bits = atomic_load_explicit(&s_rpm_bits, memory_order_acquire);
    float rpm;
    memcpy(&rpm, &bits, sizeof(rpm));
    return rpm;
}
