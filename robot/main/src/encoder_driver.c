#include "encoder_driver.h"

#include "driver/pulse_cnt.h"
#include "esp_timer.h"

#define ENCODER_HOLES 20
#define SAMPLE_INTERVAL_MS 100
#define GLITCH_FILTER_NS 1000

// RPM = count * (60 / sample_interval_s) / holes
#define COUNTS_TO_RPM (60.0f / (SAMPLE_INTERVAL_MS / 1000.0f) / ENCODER_HOLES)

static pcnt_unit_handle_t s_unit = NULL;
static volatile float s_rpm = 0.0f;

static void rpm_timer_cb(void *arg)
{
    int count = 0;
    pcnt_unit_get_count(s_unit, &count);
    pcnt_unit_clear_count(s_unit);

    if (count < 0) count = 0;
    s_rpm = (float)count * COUNTS_TO_RPM;
}

void encoder_driver_init(void)
{
    pcnt_unit_config_t unit_cfg = {
        .high_limit = INT16_MAX,
        .low_limit = INT16_MIN,
    };
    pcnt_new_unit(&unit_cfg, &s_unit);

    pcnt_glitch_filter_config_t filter_cfg = {
        .max_glitch_ns = GLITCH_FILTER_NS,
    };
    pcnt_unit_set_glitch_filter(s_unit, &filter_cfg);

    pcnt_chan_config_t chan_cfg = {
        .edge_gpio_num = ENCODER_GPIO,
        .level_gpio_num = -1,
    };
    pcnt_channel_handle_t chan = NULL;
    pcnt_new_channel(s_unit, &chan_cfg, &chan);

    pcnt_channel_set_edge_action(chan,
        PCNT_CHANNEL_EDGE_ACTION_INCREASE,
        PCNT_CHANNEL_EDGE_ACTION_HOLD);
    pcnt_channel_set_level_action(chan,
        PCNT_CHANNEL_LEVEL_ACTION_KEEP,
        PCNT_CHANNEL_LEVEL_ACTION_KEEP);

    pcnt_unit_enable(s_unit);
    pcnt_unit_clear_count(s_unit);
    pcnt_unit_start(s_unit);

    esp_timer_handle_t timer;
    esp_timer_create_args_t timer_args = {
        .callback = rpm_timer_cb,
        .name = "encoder_rpm",
    };
    esp_timer_create(&timer_args, &timer);
    esp_timer_start_periodic(timer, SAMPLE_INTERVAL_MS * 1000);
}

float encoder_get_rpm(void)
{
    return s_rpm;
}
