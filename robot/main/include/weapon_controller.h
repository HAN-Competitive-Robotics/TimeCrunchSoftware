#pragma once

#include <stdint.h>

#define WEAPON_ATTACK_RPM  5000.0f
#define WEAPON_IDLE_RPM    3000.0f

// Open-loop feedforward: percentage throttle applied as baseline when armed.
// This lets the weapon spin even before KP/KI are tuned. Set to 0 to disable.
#define WEAPON_FF          50.0f   // 50% baseline  adjust based on your ESC/motor

// Closed-loop gains. Tune after step-response test with KP/KI both 0 first.
// With FF set, the weapon will spin open-loop until gains are dialled in.
#define WEAPON_KP          0.0f    // tune from step test
#define WEAPON_KI          0.0f    // tune from step test

void weapon_controller_init(void);
void weapon_controller_set_target_rpm(float rpm);
void weapon_controller_update(void);
void weapon_controller_reset(void);
void weapon_controller_set_reverse_flag(int8_t flag);