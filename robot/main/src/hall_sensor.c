#include "hall_sensor.h"

#include <stdatomic.h>
#include "driver/gpio.h"
#include "esp_attr.h"
#include "esp_timer.h"
#include "esp_log.h"

// Why edge-interval timing instead of counting edges in a fixed window:
//
// The previous implementation counted PCNT edges over a 20 ms window, so RPM
// resolution was 60 / 0.020 / 2 = 1500 RPM per count. The weapon targets are
// 3000 and 5000 RPM, and 5000 is not even representable on that grid — it
// reads 4500 or 6000 and dithers between them. Any non-zero KP multiplies an
// error quantised to +/-1500 RPM, which slams the throttle between extremes.
// That is why the closed-loop gains could not be tuned.
//
// Timing the interval between edges instead gives resolution that improves
// with speed rather than degrading. At 5000 RPM the edges are ~6000 us apart,
// and d(RPM)/d(period) is 60e6 / (2 * 6000^2) = 0.83 RPM per microsecond, so a
// 1 us timer resolves better than 1 RPM. That is a usable feedback signal.
//
// The cost is an interrupt per edge: 167 Hz at 5000 RPM, which is negligible.

// Smoothing on the measured interval, as a power-of-two divisor:
//   period_ema += (dt - period_ema) / 2^HALL_EMA_SHIFT
// 2 gives a 4-edge time constant, about 24 ms at 5000 RPM. Enough to suppress
// magnet-spacing asymmetry without adding meaningful phase lag to the loop.
#define HALL_EMA_SHIFT  2

static const char *TAG = "HALL_SENSOR";

// All shared state is 32-bit so that loads and stores are single native
// instructions on Xtensa and therefore safe between the ISR and either core
// without disabling interrupts. Timestamps are truncated to the low 32 bits of
// esp_timer_get_time(); unsigned subtraction stays correct across the ~71.6
// minute wrap as long as the intervals measured are far shorter than that,
// which they are by many orders of magnitude.
static _Atomic uint32_t s_period_us   = 0;  // smoothed edge interval, 0 = no measurement yet
static _Atomic uint32_t s_last_edge_us = 0;
static _Atomic uint32_t s_edge_count  = 0;
static _Atomic bool     s_have_edge   = false;

static void IRAM_ATTR hall_isr(void *arg)
{
    uint32_t now  = (uint32_t)esp_timer_get_time();
    uint32_t prev = atomic_load_explicit(&s_last_edge_us, memory_order_relaxed);
    bool     seen = atomic_load_explicit(&s_have_edge, memory_order_relaxed);

    if (seen) {
        uint32_t dt = now - prev;

        // Contact bounce or electrical noise: ignore the edge entirely and
        // leave the previous timestamp in place, so the next real edge still
        // measures against a valid reference.
        if (dt < HALL_MIN_EDGE_INTERVAL_US) {
            return;
        }

        uint32_t ema = atomic_load_explicit(&s_period_us, memory_order_relaxed);
        if (ema == 0 || dt > HALL_STALL_TIMEOUT_US) {
            // First measurement, or the rotor was stopped and has just started
            // turning again. Seed rather than average, so the estimate does not
            // crawl up from a stale value.
            ema = dt;
        } else {
            ema += ((int32_t)dt - (int32_t)ema) >> HALL_EMA_SHIFT;
        }
        atomic_store_explicit(&s_period_us, ema, memory_order_relaxed);
    }

    atomic_store_explicit(&s_last_edge_us, now, memory_order_relaxed);
    atomic_store_explicit(&s_have_edge, true, memory_order_relaxed);
    atomic_fetch_add_explicit(&s_edge_count, 1, memory_order_relaxed);
}

void hall_sensor_init(void)
{
    gpio_config_t io_cfg = {
        .pin_bit_mask = 1ULL << HALL_SENSOR_GPIO,
        .mode         = GPIO_MODE_INPUT,
        // NPN open-collector output: only sinks to GND, so the line must be
        // pulled high through the internal pull-up.
        .pull_up_en   = GPIO_PULLUP_ENABLE,
        .pull_down_en = GPIO_PULLDOWN_DISABLE,
        // Bipolar Hall latch toggles on each pole transition, so both edges
        // are real transitions and both are counted.
        .intr_type    = GPIO_INTR_ANYEDGE,
    };
    ESP_ERROR_CHECK(gpio_config(&io_cfg));

    // Another driver may already own the shared GPIO ISR service; that is fine
    // and is not an error for us.
    esp_err_t err = gpio_install_isr_service(ESP_INTR_FLAG_IRAM);
    if (err != ESP_OK && err != ESP_ERR_INVALID_STATE) {
        ESP_ERROR_CHECK(err);
    }
    ESP_ERROR_CHECK(gpio_isr_handler_add(HALL_SENSOR_GPIO, hall_isr, NULL));

    ESP_LOGI(TAG, "Hall sensor init OK: GPIO %d, %d pulses/rev, edge-interval timing",
             HALL_SENSOR_GPIO, HALL_SENSOR_PULSES_PER_REV);
}

bool hall_sensor_signal_fresh(void)
{
    if (!atomic_load_explicit(&s_have_edge, memory_order_relaxed)) {
        return false;
    }
    uint32_t now  = (uint32_t)esp_timer_get_time();
    uint32_t last = atomic_load_explicit(&s_last_edge_us, memory_order_relaxed);
    return (now - last) <= HALL_STALL_TIMEOUT_US;
}

float hall_sensor_get_rpm(void)
{
    uint32_t period = atomic_load_explicit(&s_period_us, memory_order_relaxed);
    if (period == 0 || !hall_sensor_signal_fresh()) {
        return 0.0f;
    }
    return 60.0f * 1.0e6f / ((float)period * (float)HALL_SENSOR_PULSES_PER_REV);
}

uint32_t hall_sensor_get_edge_count(void)
{
    return atomic_load_explicit(&s_edge_count, memory_order_relaxed);
}
