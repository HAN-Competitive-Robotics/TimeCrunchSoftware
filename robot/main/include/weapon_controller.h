#pragma once

#include <stdbool.h>
#include <stdint.h>

#define WEAPON_ATTACK_RPM  5000.0f
#define WEAPON_IDLE_RPM    3000.0f

// Open-loop feedforward: percentage throttle applied as baseline when armed.
// This lets the weapon spin even before KP/KI are tuned. Set to 0 to disable.
#define WEAPON_FF          50.0f   // 50% baseline  adjust based on your ESC/motor

// ---------------------------------------------------------------------------
// Hard output ceiling
// ---------------------------------------------------------------------------
// Absolute maximum throttle percentage the weapon may ever be commanded at,
// applied last, after every other term, in both open and closed loop. Nothing
// downstream of this can raise it: not a tuned KP, not integrator windup, not
// a feedback fault.
//
// READ THIS BEFORE TRUSTING IT FOR A KINETIC ENERGY LIMIT.
//
// A throttle percentage is not an energy measurement. Kinetic energy is
// (1/2) * I * omega^2, so it scales with the SQUARE of rotor speed, and the
// relationship between throttle percentage and steady-state RPM is not linear
// and depends on the ESC, the battery state of charge, and the rotor.
//
// This ceiling is a guard, not a guarantee. To use it for rules compliance:
// spin up at this setting on a charged pack, measure actual RPM, compute the
// energy from the rotor's real moment of inertia, and lower the number until
// the measured figure is inside the limit with margin. Then re-check on a
// fresh pack, because a fully charged battery spins faster at the same
// throttle percentage.
#define WEAPON_MAX_OUTPUT_PCT   60.0f

// ---------------------------------------------------------------------------
// Open-loop fallback levels
// ---------------------------------------------------------------------------
// Used when the Hall sensor is absent or has faulted, so there is no RPM to
// close a loop against. Without these the open-loop path emitted WEAPON_FF for
// every command, making idle and attack indistinguishable.
//
// Both are clamped by WEAPON_MAX_OUTPUT_PCT, so raising them cannot breach the
// ceiling above.
#define WEAPON_OL_IDLE_PCT      30.0f
#define WEAPON_OL_ATTACK_PCT    50.0f

// Closed-loop gains. Both zero ships the historical open-loop behaviour.
//
// Tune with the step-response procedure in docs/firmware/weapon-tuning.md.
// Do NOT guess these: an untuned KP on a weapon with this much stored energy
// is a mechanical hazard, and until the procedure has been run on the actual
// rotor there is no basis for any particular value.
//
// The RPM feedback these act on is only usable since the Hall driver moved to
// edge-interval timing; the previous fixed-window counter quantised RPM to
// 1500 RPM per count, which no gain could have been tuned against.
//
// Overridable at build time (-DWEAPON_KP=...) so candidate gains can be tried
// on the bench, and so the host tests can exercise the saturated case, without
// editing this file.
#ifndef WEAPON_KP
#define WEAPON_KP          0.0f    // tune from step test
#endif
#ifndef WEAPON_KI
#define WEAPON_KI          0.0f    // tune from step test
#endif

// Maximum control interval honoured by the integrator, in seconds. The task
// runs at 100 Hz; if a scheduling hiccup or a long gap between armed periods
// produces a larger dt, integrating over it would inject a step into the
// integral, so it is clamped instead.
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

// Clear integrator and timing. Call whenever the weapon is commanded off, so
// the controller does not resume against a stale integral or a huge dt.
void weapon_controller_reset(void);

// Run one control step and drive the weapon ESC. Call at 100 Hz.
void weapon_controller_update(void);

// Wireless bench test: command a direct open-loop throttle percentage rather
// than a speed. |pct| is clamped by WEAPON_MAX_OUTPUT_PCT and the actuator
// range; the sign selects direction. No RPM loop runs (the operator is setting
// a throttle, not a target speed), and the integrator is cleared so a later
// return to closed-loop control does not resume against a stale integral.
void weapon_controller_test(int pct);

// Magnitude of the most recent commanded output, 0..100. Used by the safety
// monitor to decide whether the weapon is being driven hard enough that the
// Hall sensor ought to be reporting rotation.
float weapon_controller_get_output(void);

// Snapshot of the last control step, for logging and bench tuning.
void weapon_controller_get_telemetry(weapon_telemetry_t *out);
