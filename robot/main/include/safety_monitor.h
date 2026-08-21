#pragma once

#include <stdbool.h>

// Background safety supervision for the weapon path.
//
// Two independent jobs, both of which must exist before the weapon PI gains
// can safely be tuned away from zero:
//
//  1. Feedback fault. If the weapon is being commanded but the Hall sensor is
//     not reporting rotation, the RPM input to the controller is meaningless.
//     Closing a loop on a dead sensor is actively dangerous: measured RPM
//     reads 0, the error becomes the full target, the integrator winds up and
//     the output saturates at full throttle on a spinning weapon. Detecting
//     this and degrading to open-loop feed-forward keeps the failure mode the
//     same as it is today instead of making it worse.
//
//  2. Battery sag. The weapon is by far the largest load on the pack. If the
//     bus voltage collapses, dropping the weapon first preserves the drive
//     motors and the radio link, which is what gets the robot out of trouble.
//     Disabled by default; see WEAPON_BATTERY_CELLS in robot_config.h.
//
// Runs as its own low-rate task so that the I2C reads it needs never sit in
// the 100 Hz weapon control path.

// Create the monitor task. Call after power_sensor_driver_init() and
// hall_sensor_init(). Safe to call when the INA3221 is absent: the battery
// checks self-disable and the feedback-fault check continues to work.
void safety_monitor_init(void);

// True when the weapon has been commanded for longer than
// WEAPON_FEEDBACK_FAULT_MS without the Hall sensor reporting any rotation.
// The weapon controller uses this to hold the integrator and fall back to
// pure feed-forward.
bool safety_weapon_feedback_fault(void);

// True when the pack has been below the sustained-sag threshold long enough
// that the weapon should be cut to protect drive and radio.
// Always false when the software battery monitor is disabled or the INA3221
// is not responding.
bool safety_weapon_inhibited(void);

// Most recent pack voltage in Volts, or NAN if unavailable.
float safety_get_battery_voltage(void);
