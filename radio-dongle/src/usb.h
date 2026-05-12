#pragma once

#include <zephyr/kernel.h>
#include <zephyr/device.h>

#ifdef __cplusplus
extern "C" {
#endif

int usb_cdc_init(void);

int usb_cdc_read(uint8_t *buf, size_t max_len);

int usb_cdc_write(const uint8_t *buf, size_t len);

#ifdef __cplusplus
}
#endif