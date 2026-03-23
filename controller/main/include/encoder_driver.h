#pragma once

// GPIO pin for the weapon encoder optical sensor
#define ENCODER_GPIO   4

// Initialize the encoder GPIO interrupt and RPM sampling timer.
// Must be called before encoder_get_rpm.
void encoder_driver_init(void);

// Returns the most recently computed weapon motor RPM.
float encoder_get_rpm(void);
