#pragma once

/* 1 = BMP280 thermal safety (per-motor cutoff 100 °C, deep-sleep 90 °C).
 * 0 if temp sensors aren't installed. */
#define THERMAL_PROTECTION_ENABLED 0

/* 0 when the weapon Hall sensor is not fitted: weapon runs open-loop and the
 * feedback-fault path is skipped (no sensor to fault against). */
#ifndef WEAPON_HALL_SENSOR_FITTED
#define WEAPON_HALL_SENSOR_FITTED  0
#endif

/* --------------------------------------------------------------------------
 * Motor direction
 * --------------------------------------------------------------------------
 * Set to 1 to reverse that side (normally exactly one is 1 on differential
 * drive). Drives backwards when you push forward: flip BOTH. Spins on the spot
 * instead of straight: flip ONE. */
#define MOTOR_INVERT_LEFT   0
#define MOTOR_INVERT_RIGHT  1

/* Byte length of every over-the-air packet.  Must match nrf24_basic_config()
 * call in task_radio and the driver station's _hex_packet() encoding:
 *   byte 0 = left motor   (0–255, center 127)
 *   byte 1 = right motor  (0–255, center 127)
 *   byte 2 = weapon       (127=safe, 160=idle fwd, 255=attack fwd, 95=idle rev)
 *   byte 3 = failsafe     (0=normal, 1=set trim, >127=hard killswitch) */
#define BATTLEBOT_PAYLOAD_LEN 4

/* --------------------------------------------------------------------------
 * Command opcodes
 * --------------------------------------------------------------------------
 * The failsafe byte doubles as an opcode so commands fit the 4-byte payload.
 *
 * PACKET_OPCODE_SET_TRIM reinterprets the packet as:
 *   byte 0 = left trim + 127, byte 1 = right trim + 127, byte 2 = magic.
 * The magic guards against a corrupted drive packet retrimming mid-match; the
 * packet is skipped for drive (bytes 0/1 aren't throttles). */
#define PACKET_OPCODE_DRIVE     0
#define PACKET_OPCODE_SET_TRIM  1
#define TRIM_COMMAND_MAGIC      0x5A

/*
 * PACKET_OPCODE_WEAPON_TEST is a wireless bench test:
 *   byte 0 = 127 + signed percent (sign = direction), byte 2 = magic.
 * Wheels forced neutral; ceiling and killswitch still apply. The station only
 * sends these while its 5 s deadman is held. */
#define PACKET_OPCODE_WEAPON_TEST  2
#define WEAPON_TEST_MAGIC          0xA7

/* --------------------------------------------------------------------------
 * Link loss
 * --------------------------------------------------------------------------
 * Milliseconds without a packet before drive and weapon cut. Set from the
 * logged gap histogram, not a guess: too tight cuts out on interference. */
#define LINK_LOSS_TIMEOUT_MS  500

/* How often task_radio prints the packet-gap histogram. */
#define PACKET_STATS_LOG_MS   5000

/* --------------------------------------------------------------------------
 * Task watchdog
 * --------------------------------------------------------------------------
 * A stalled real-time task panics and resets the chip; the ESCs disarm on the
 * lost PWM. 300 ms is ~6x task_radio's 50 ms loop. task_thermal isn't subscribed. */
#define TASK_WDT_TIMEOUT_MS   300

/* --------------------------------------------------------------------------
 * Weapon feedback fault
 * --------------------------------------------------------------------------
 * Commanded output (percent) above which the weapon is considered to be
 * driven and therefore expected to produce Hall edges. */
#define WEAPON_FEEDBACK_MIN_OUTPUT     20.0f

/* If the INA3221 is fitted, a weapon current below this means the ESC is not
 * actually delivering power, so sensor silence is expected and no fault is
 * raised. Ignored when the current reading is unavailable. */
#define WEAPON_FEEDBACK_MIN_CURRENT_A  2.0f

/* Time commanded with no Hall edge before feedback is called invalid. Must
 * exceed the standing-start-to-first-edge time (worst on a high-inertia disc). */
#define WEAPON_FEEDBACK_FAULT_MS       1500

/* --------------------------------------------------------------------------
 * Battery sag protection  (software, via INA3221)
 * --------------------------------------------------------------------------
 * DISABLED by default. Set to the cell count to enable, and validate the
 * threshold under real weapon load first (spin-up sags the pack hard). */
#define WEAPON_BATTERY_CELLS           0
#define WEAPON_BATTERY_CUT_V_PER_CELL  3.20f

/* Consecutive 50 ms samples below the cut voltage before the weapon is
 * inhibited. 6 samples = 300 ms sustained, which ignores spin-up transients. */
#define WEAPON_BATTERY_SAG_SAMPLES     6

/* Volts above the cut level the pack must recover to before the weapon is
 * re-enabled, so it cannot chatter on and off at the threshold. */
#define WEAPON_BATTERY_RECOVER_V       0.40f
