#pragma once

#include <zephyr/kernel.h>
#include <esb.h>

#ifdef __cplusplus
extern "C" {
#endif

int esb_radio_init(void);

bool esb_radio_ready(void);

int esb_radio_send(struct esb_payload *pl);

struct esb_payload esb_set_battlebot_payload(uint8_t motor1, uint8_t motor2, uint8_t weaponEn, uint8_t failsafe);

#ifdef CONFIG_DONGLE_TELEMETRY
#define ESB_TELEM_LEN 16
int esb_telem_try_get(uint8_t *buf, size_t len);
#endif

#ifdef __cplusplus
}
#endif