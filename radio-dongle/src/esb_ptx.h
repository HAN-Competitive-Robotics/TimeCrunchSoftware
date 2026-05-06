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

#ifdef __cplusplus
}
#endif