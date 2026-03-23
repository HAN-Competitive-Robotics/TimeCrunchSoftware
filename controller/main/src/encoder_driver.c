#include "encoder_driver.h"

#include "driver/gpio.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"

#define ENCODER_HOLES       20
#define SAMPLE_INTERVAL_MS  100

// RPM = count * (60 / sample_interval_s) / holes
//     = count * (60 / 0.1) / 20 = count * 30
#define COUNTS_TO_RPM  (60.0f / (SAMPLE_INTERVAL_MS / 1000.0f) / ENCODER_HOLES)

static volatile uint32_t s_pulse_count = 0;
static float             s_rpm         = 0.0f;
static portMUX_TYPE      s_mux         = portMUX_INITIALIZER_UNLOCKED;

static void IRAM_ATTR encoder_isr(void *arg)
{
    portENTER_CRITICAL_ISR(&s_mux);
    s_pulse_count++;
    portEXIT_CRITICAL_ISR(&s_mux);
}

static void rpm_timer_cb(void *arg)
{
    portENTER_CRITICAL(&s_mux);
    uint32_t count = s_pulse_count;
    s_pulse_count  = 0;
    portEXIT_CRITICAL(&s_mux);

    s_rpm = (float)count * COUNTS_TO_RPM;
}

void encoder_driver_init(void)
{
    gpio_config_t cfg = {
        .pin_bit_mask = 1ULL << ENCODER_GPIO,
        .mode         = GPIO_MODE_INPUT,
        .pull_up_en   = GPIO_PULLUP_ENABLE,
        .pull_down_en = GPIO_PULLDOWN_DISABLE,
        .intr_type    = GPIO_INTR_POSEDGE,
    };
    gpio_config(&cfg);

    gpio_install_isr_service(0);
    gpio_isr_handler_add(ENCODER_GPIO, encoder_isr, NULL);

    esp_timer_handle_t timer;
    esp_timer_create_args_t timer_args = {
        .callback = rpm_timer_cb,
        .name     = "encoder_rpm",
    };
    esp_timer_create(&timer_args, &timer);
    esp_timer_start_periodic(timer, SAMPLE_INTERVAL_MS * 1000);
}

float encoder_get_rpm(void)
{
    return s_rpm;
}
