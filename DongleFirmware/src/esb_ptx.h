#pragma once

#include <zephyr/kernel.h>
#include <esb.h>

#ifdef __cplusplus
extern "C" {
#endif

/* Initialize ESB in PTX mode. Starts HFCLK if you call clocks_start() elsewhere. */
int esb_radio_init(void);

/* Returns true if radio is ready to accept a new TX payload (ACKed or failed). */
bool esb_radio_ready(void);

/* Write a payload. Nonblocking; completion via ESB events. */
int esb_radio_send(struct esb_payload *pl);

/* Convenience: create a default payload (your old pattern). */
struct esb_payload esb_radio_default_payload(void);

#ifdef __cplusplus
}
#endif