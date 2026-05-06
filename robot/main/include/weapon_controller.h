#pragma once

#define WEAPON_ATTACK_RPM  5000.0f
#define WEAPON_IDLE_RPM    3000.0f
#define WEAPON_KP          0.0f    // tune from step test
#define WEAPON_KI          0.0f    // tune from step test

void weapon_controller_init(void);
void weapon_controller_set_target_rpm(float rpm);
void weapon_controller_update(void);
void weapon_controller_reset(void);
