#include "trim_store.h"

#include <string.h>

#include "esp_log.h"
#include "nvs.h"
#include "nvs_flash.h"

static const char *TAG = "TRIM";

#define TRIM_NAMESPACE "robot"
#define TRIM_KEY_LEFT  "trim_l"
#define TRIM_KEY_RIGHT "trim_r"

static motor_trim_t s_trim = {0, 0};

esp_err_t trim_store_init(void)
{
    /* nvs_flash_init() is not called anywhere else in this firmware, so do it
     * here. A truncated or version-mismatched partition is erased and retried
     * rather than left failing: losing a trim value is not worth refusing to
     * boot a combat robot over. */
    esp_err_t err = nvs_flash_init();
    if (err == ESP_ERR_NVS_NO_FREE_PAGES || err == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        ESP_LOGW(TAG, "NVS partition unusable (%s), erasing", esp_err_to_name(err));
        ESP_ERROR_CHECK(nvs_flash_erase());
        err = nvs_flash_init();
    }
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "nvs_flash_init failed: %s — running untrimmed",
                 esp_err_to_name(err));
        return err;
    }

    nvs_handle_t h;
    err = nvs_open(TRIM_NAMESPACE, NVS_READONLY, &h);
    if (err != ESP_OK) {
        /* ESP_ERR_NVS_NOT_FOUND simply means nothing has been saved yet. */
        ESP_LOGI(TAG, "No saved trim (%s), starting at 0/0", esp_err_to_name(err));
        return ESP_OK;
    }

    int8_t l = 0, r = 0;
    if (nvs_get_i8(h, TRIM_KEY_LEFT, &l) != ESP_OK) l = 0;
    if (nvs_get_i8(h, TRIM_KEY_RIGHT, &r) != ESP_OK) r = 0;
    nvs_close(h);

    s_trim.left = l;
    s_trim.right = r;
    ESP_LOGI(TAG, "Loaded trim from NVS: L=%d R=%d", l, r);
    return ESP_OK;
}

motor_trim_t trim_store_get(void)
{
    return s_trim;
}

esp_err_t trim_store_set(int8_t left, int8_t right)
{
    /* Apply first, persist second. If the flash write fails the robot still
     * drives with the requested trim for this power cycle, which is what the
     * operator asked for; they just lose it on reboot. */
    s_trim.left = left;
    s_trim.right = right;

    nvs_handle_t h;
    esp_err_t err = nvs_open(TRIM_NAMESPACE, NVS_READWRITE, &h);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "nvs_open failed: %s — trim applied but not saved",
                 esp_err_to_name(err));
        return err;
    }

    err = nvs_set_i8(h, TRIM_KEY_LEFT, left);
    if (err == ESP_OK) {
        err = nvs_set_i8(h, TRIM_KEY_RIGHT, right);
    }
    if (err == ESP_OK) {
        err = nvs_commit(h);
    }
    nvs_close(h);

    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Saving trim failed: %s", esp_err_to_name(err));
    } else {
        ESP_LOGI(TAG, "Trim saved: L=%d R=%d", left, right);
    }
    return err;
}

uint8_t trim_apply(uint8_t raw, int8_t trim)
{
    int v = (int)raw + (int)trim;
    if (v < 0) v = 0;
    if (v > 255) v = 255;
    return (uint8_t)v;
}
