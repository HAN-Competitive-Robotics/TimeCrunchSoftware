#pragma once

#define WEAPON_TARGET_RPM  5000.0f
#define WEAPON_KP          0.0f    // tune from step test
#define WEAPON_KI          0.0f    // tune from step test

// Initialize the weapon PI controller using the defines above.
void weapon_controller_init(void);

// Run one PI iteration — call once per control loop.
void weapon_controller_update(void);

// Reset the integrator. Call when disabling the weapon.
void weapon_controller_reset(void);
