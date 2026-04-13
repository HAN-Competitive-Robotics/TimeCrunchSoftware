#pragma once

#include <stdint.h>

// GPIO pin assignments for each motor
#define MOTOR_PIN_RIGHT_WHEEL  25
#define MOTOR_PIN_LEFT_WHEEL   26
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
// -100 = full reverse (duty cycle 0.10), 0 = neutral (0.15), 100 = full forward (0.20)
void motor_set_throttle(motor_t motor, int throttle);

// Check all motor temperatures and cut throttle to 0 on any motor exceeding 100 C.
// Call once per control loop.
void motor_safety_check(void);
