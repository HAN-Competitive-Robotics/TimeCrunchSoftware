#pragma once

#include <stdbool.h>
#include <stdint.h>

// GPIO pin for the weapon RPM Hall sensor (RS PRO 289-2088).
// Sensor is an NPN open-collector bipolar Hall latch: supply (red) to external
// +V (up to 24 V), GND (black) to common ground, output (white) to this pin.
// Output only sinks to GND — a pull-up to 3.3 V is required and is enabled
// internally by the driver. Sensor V+ must NOT be pulled up to the ESP32 pin.
#define HALL_SENSOR_GPIO   15

// Magnetic transitions per full weapon-shaft revolution. The latch toggles on
// each pole change, so for one diametrically magnetised magnet on the shaft
// (one N-face + one S-face per turn) this is 2. Adjust to match the mechanical
// pole count actually mounted on the rotor.
#define HALL_SENSOR_PULSES_PER_REV  2

// Edges closer together than this are treated as contact bounce or electrical
// noise and discarded. 200 us between edges is 150,000 RPM at 2 pulses/rev,
// far above anything the weapon can reach, so this rejects glitches without
// ever rejecting a real transition.
#define HALL_MIN_EDGE_INTERVAL_US   200u

// If no edge arrives within this window the rotor is treated as stopped and
// get_rpm() returns 0. At 2 pulses/rev, 250 ms between edges is 120 RPM, well
// below the 3000 RPM idle target, so a spinning weapon never looks stalled.
#define HALL_STALL_TIMEOUT_US       250000u

// Initialize the Hall sensor input and edge-interval timing.
// Must be called before hall_sensor_get_rpm.
void hall_sensor_init(void);

// Most recently measured weapon RPM, from the smoothed edge interval.
// Returns 0 if no edge has arrived within HALL_STALL_TIMEOUT_US.
float hall_sensor_get_rpm(void);

// True if an edge arrived within HALL_STALL_TIMEOUT_US, i.e. the sensor is
// actively reporting rotation right now.
//
// A false return does NOT by itself mean the sensor is broken: a stopped
// weapon is correctly silent. Deciding "sensor fault" requires knowing that
// the weapon was commanded to spin and is drawing current, which is why that
// judgement lives in safety_monitor and not here.
bool hall_sensor_signal_fresh(void);

// Total accepted edges since boot. Diagnostics only; wraps at 2^32.
uint32_t hall_sensor_get_edge_count(void);
