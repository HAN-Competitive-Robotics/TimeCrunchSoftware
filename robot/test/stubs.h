#pragma once
#include <stdint.h>
#include <stdbool.h>

/* esp_timer stub: the harness drives time explicitly. */
extern int64_t g_now_us;

/* Real motor_driver.h supplies motor_t and motor_set_throttle; the harness
 * only provides the implementation. */
extern int g_last_weapon_cmd;

/* Fakes driving the controller's two inputs. */
extern float g_fake_rpm;
extern bool  g_fake_fresh;
extern bool  g_fake_fault;
