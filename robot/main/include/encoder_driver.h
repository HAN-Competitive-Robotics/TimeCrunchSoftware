#pragma once

// GPIO pin for the weapon RPM Hall sensor (RS PRO 289-2088).
// Sensor is an NPN open-collector bipolar Hall latch: supply (red) to external
// +V (up to 24 V), GND (black) to common ground, output (white) to this pin.
// Output only sinks to GND — a pull-up to 3.3 V is required and is enabled
// internally by the driver. Sensor V+ must NOT be pulled up to the ESP32 pin.
#define ENCODER_GPIO   15

// Magnetic transitions per full weapon-shaft revolution. The latch toggles on
// each pole change, so for one diametrically magnetised magnet on the shaft
// (one N-face + one S-face per turn) this is 2. Adjust to match the mechanical
// pole count actually mounted on the rotor.
#define ENCODER_PULSES_PER_REV  2

// Initialize the Hall sensor input, edge counter and RPM sampling timer.
// Must be called before encoder_get_rpm.
void encoder_driver_init(void);

// Returns the most recently computed weapon motor RPM.
float encoder_get_rpm(void);
