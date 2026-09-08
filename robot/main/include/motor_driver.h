#pragma once

#include <stdint.h>

// GPIO pin assignments for each motor
#define MOTOR_PIN_RIGHT_WHEEL  13
/* GPIO 12 is the MTDI strapping pin: its level at reset selects the flash
 * voltage. Held high at boot the chip expects 1.8 V flash and will not
 * start on a 3.3 V module. Make sure the ESC does not pull this line up
 * while the ESP32 is resetting. */
#define MOTOR_PIN_LEFT_WHEEL   12
#define MOTOR_PIN_WEAPON       21

typedef enum {
    MOTOR_RIGHT_WHEEL,
    MOTOR_LEFT_WHEEL,
    MOTOR_WEAPON,
    MOTOR_COUNT
} motor_t;

// Initialize PWM channels for all motors (must be called before motor_set_throttle)
void motor_driver_init(void);

// Set motor throttle. Value must be in range [-100, 100].
// -100 = 1 ms pulse, 0 = 1.5 ms pulse (neutral), 100 = 2 ms pulse  standard RC ESC.
void motor_set_throttle(motor_t motor, int throttle);

// Check all motor temperatures and cut throttle to 0 on any motor exceeding 100 C.
// Call once per control loop.
void motor_safety_check(void);
