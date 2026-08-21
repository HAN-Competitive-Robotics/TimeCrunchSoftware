#pragma once

/* Set to 1 to enable BMP280 thermal safety (per-motor cutoff at 100 °C and
 * system deep-sleep at 90 °C).  Set to 0 if temperature sensors are not
 * installed — tempsensor_driver_init() will not be called and task_thermal
 * will not be created. */
#define THERMAL_PROTECTION_ENABLED 1

/* Byte length of every over-the-air packet.  Must match nrf24_basic_config()
 * call in task_radio and the driver station's _hex_packet() encoding:
 *   byte 0 = left motor   (0–255, center 127)
 *   byte 1 = right motor  (0–255, center 127)
 *   byte 2 = weapon       (127=safe, 160=idle fwd, 255=attack fwd, 95=idle rev)
 *   byte 3 = failsafe     (0=normal, >127=hard killswitch) */
#define BATTLEBOT_PAYLOAD_LEN 4

/* --------------------------------------------------------------------------
 * Link loss
 * --------------------------------------------------------------------------
 * Milliseconds without a valid packet before drive and weapon are cut.
 *
 * 500 ms is the value the robot has always run. Do not tighten it from a
 * guess: task_radio logs the observed inter-packet gap distribution every
 * PACKET_STATS_LOG_MS, so run a match, read the histogram, and set this from
 * the measured worst case with margin. A timeout below the real p100 gap
 * causes the robot to cut out mid-match on ordinary 2.4 GHz interference. */
#define LINK_LOSS_TIMEOUT_MS  500

/* How often task_radio prints the packet-gap histogram. */
#define PACKET_STATS_LOG_MS   5000

/* --------------------------------------------------------------------------
 * Task watchdog
 * --------------------------------------------------------------------------
 * If either real-time task stops feeding the watchdog for this long the chip
 * panics and resets. The ESCs see no PWM while it reboots and disarm, so a
 * hung task cannot leave the weapon powered.
 *
 * task_radio iterates at most every 50 ms (its semaphore timeout) and
 * task_weapon every 10 ms, so 300 ms is roughly a 6x margin on the slower of
 * the two. task_thermal runs at 1 Hz and is deliberately NOT subscribed. */
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

/* How long the weapon may be commanded with no Hall edge at all before the
 * feedback is declared invalid.
 *
 * Must comfortably exceed the worst-case time from a standing start to the
 * FIRST edge, which for a high-inertia disc is the slowest part of spin-up.
 * Too short and a healthy weapon is falsely flagged during spin-up, which
 * costs the closed loop; it is never unsafe, since the fallback is the
 * open-loop behaviour the robot already ships. */
#define WEAPON_FEEDBACK_FAULT_MS       1500

/* --------------------------------------------------------------------------
 * Battery sag protection  (software, via INA3221)
 * --------------------------------------------------------------------------
 * DISABLED by default. Set to the pack's cell count to enable, and validate
 * the threshold on the bench under real weapon load before trusting it: a
 * spinning-up weapon sags the pack hard and briefly, and a cut level set from
 * a datasheet rather than a measurement will drop the weapon mid-match.
 *
 * 3.2 V/cell sustained is a conventional LiPo working floor, but "sustained"
 * is doing the work here — see WEAPON_BATTERY_SAG_SAMPLES. */
#define WEAPON_BATTERY_CELLS           0
#define WEAPON_BATTERY_CUT_V_PER_CELL  3.20f

/* Consecutive 50 ms samples below the cut voltage before the weapon is
 * inhibited. 6 samples = 300 ms sustained, which ignores spin-up transients. */
#define WEAPON_BATTERY_SAG_SAMPLES     6

/* Volts above the cut level the pack must recover to before the weapon is
 * re-enabled, so it cannot chatter on and off at the threshold. */
#define WEAPON_BATTERY_RECOVER_V       0.40f
