#pragma once

#include <stdbool.h>
#include <stdint.h>

#define WEAPON_ATTACK_RPM  5000.0f
#define WEAPON_IDLE_RPM    3000.0f

// Open-loop feedforward baseline (percent) when armed. 0 to disable.
#define WEAPON_FF          50.0f

// Hard throttle ceiling, applied last in both loops. NOTE: a throttle percent
// is not an energy measurement (KE scales with rpm^2, and %->rpm is nonlinear),
// so this is a guard, not a legality guarantee. See docs/hardware/weapon-limits.md.
#ifndef WEAPON_MAX_OUTPUT_PCT
#define WEAPON_MAX_OUTPUT_PCT   100.0f
#endif

// Open-loop levels used when there is no usable RPM. Clamped by the ceiling.
#define WEAPON_OL_IDLE_PCT      30.0f
#define WEAPON_OL_ATTACK_PCT    100.0f

// Closed-loop gains; both zero = open-loop. Don't guess them - tune per
// docs/firmware/weapon-tuning.md. Overridable with -DWEAPON_KP=... for tests.
#ifndef WEAPON_KP
#define WEAPON_KP          0.0f    // tune from step test
#endif
#ifndef WEAPON_KI
#define WEAPON_KI          0.0f    // tune from step test
#endif

// Max integrator dt (s); clamps a scheduling hiccup from stepping the integral.
#define WEAPON_MAX_DT_S    0.05f

typedef struct {
    float target_rpm;
    float measured_rpm;
    float error;
    float integral;
    float output;        // final commanded magnitude, 0..100
    bool  feedback_ok;   // false when running open-loop on a feedback fault
} weapon_telemetry_t;

void weapon_controller_init(void);
void weapon_controller_set_target_rpm(float rpm);
void weapon_controller_set_reverse_flag(int8_t flag);

// Clear integrator and timing. Call whenever the weapon is commanded off.
void weapon_controller_reset(void);

// Run one control step and drive the weapon ESC. Call at 100 Hz.
void weapon_controller_update(void);

// Wireless bench test: direct open-loop percent, |pct| clamped by the ceiling,
// sign = direction. No RPM loop; clears the integrator.
void weapon_controller_test(int pct);

// Magnitude of the last commanded output, 0..100.
float weapon_controller_get_output(void);

// Snapshot of the last control step, for logging and bench tuning.
void weapon_controller_get_telemetry(weapon_telemetry_t *out);
