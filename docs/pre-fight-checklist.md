# Pre-Fight Checklist - Setting the Bot to Fight Mode

Run through this before every fight. Work top to bottom: settings first (bench),
then hardware, then power-on verification, then the failsafe checks, and only
then arm. **Do not skip the failsafe section** - it is the part that keeps
people safe.

Values in this list are the current repo settings, verified on 2026-09-08.
If you change a setting, update this file.

---

## 1. Firmware and robot config (bench, before flashing)

- [ ] **Flash the latest firmware.** The robot must have the current build.
      Recent firmware changes that must be on it: 100% weapon attack, the
      sensorless feedback-fault fix, and the wireless weapon-test opcode.
      `python scripts/flash.py` (see `robot/README.md`).
- [ ] **Weapon output** (`robot/main/include/weapon_controller.h`):
  - `WEAPON_MAX_OUTPUT_PCT = 100`, `WEAPON_OL_ATTACK_PCT = 100`,
    `WEAPON_OL_IDLE_PCT = 30`. Full-power attack, low idle.
  - Runs **open-loop** (`WEAPON_HALL_SENSOR_FITTED = 0`): no RPM control, no
    RPM readback. Expected - the Hall sensor is not fitted.
- [ ] **Motor direction** (`robot/main/include/robot_config.h`):
  `MOTOR_INVERT_LEFT = 0`, `MOTOR_INVERT_RIGHT = 1`. **Verify on the bench in
  section 6** - if the bot spins on the spot instead of driving forward, flip
  exactly one of these and reflash.
- [ ] Protection flags are as expected for the current hardware:
  `THERMAL_PROTECTION_ENABLED = 0` (no temp sensors) and
  `WEAPON_BATTERY_CELLS = 0` (no firmware low-voltage cutoff - the ESC's own
  LVC does that, default 3.0 V/cell). Both off is correct while those sensors
  are absent.
- [ ] `LINK_LOSS_TIMEOUT_MS = 500` - the robot cuts outputs 500 ms after the
      last packet. Non-latching, recovers when packets resume.

## 2. Station config (`driver/config.json`)

- [ ] **`safety.failsafe_on_dongle_removal` → `false` FOR MATCHES.** This is the
      big one. On the bench it should be `true` (unplug = guaranteed kill), but
      in a match a momentary USB glitch would then permanently deep-sleep the
      bot mid-fight. **Turn it off before you fight.**
- [ ] `serial.rate_hz = 50`.
- [ ] Weapon unlock password is set and the driver knows it. The weapon is
      always LOCKED at startup and never persists unlocked.

## 3. Hardware, before applying power

- [ ] Battery: **4S** LiPo, charged, and mechanically secured. **4S only** - a
      5S pack fails both the tip-speed and energy limits (see
      `docs/hardware/weapon-limits.md`). The pack is part of legality.
- [ ] nRF24 wiring: **VCC = 3.3 V, never 5 V.** SPI wires solid and seated - a
      floating SPI bus reads as all-`0xFF`, which the robot cannot tell from a
      real killswitch and will trigger a phantom deep-sleep. Antenna attached.
- [ ] Weapon ESC calibrated, signal wire on **GPIO 21**. Motor signal pins:
      right wheel **13**, left wheel **12**, weapon **21**.
- [ ] Weapon, wheels, and all fasteners mechanically tight. Nothing loose that
      a full-power spin-up will throw.

## 4. Power-on and radio bringup

- [ ] Weapon ESC beeps on power: one beep per cell then a long beep. **Four
      beeps + long = 4S confirmed** (free battery check).
- [ ] Serial log shows `STATUS = 0x0E` and `RF_CH = 40`.
      `STATUS = 0xFF` means the nRF24 SPI is broken - check 3.3 V and every SPI
      wire before going further. Do not fight on `0xFF`.
- [ ] Link is live: packets flowing, timeout count not climbing.

## 5. Station bringup

- [ ] Dongle plugged into the driver laptop, station shows **SERIAL OK**.
- [ ] Gamepad shows connected (not KEYBOARD ONLY).
- [ ] Correct drive mode selected in the dropdown (Tank or Arcade).
- [ ] Banner reads **DISARMED**, weapon shows **LOCKED**.

## 6. Failsafe checks - DO THESE EVERY TIME (weapon area clear, wheels up)

Prove each kill path actually stops the bot before you trust it in a fight.

- [ ] **Killswitch → deep sleep.** With the bot armed and driving (weapon SAFE),
      hit each of: gamepad **B**, keyboard **F**, and the on-screen **KILL
      ROBOT** button. Each must make the bot go dead and stay dead until
      power-cycled. Banner shows KILLSWITCH LATCHED.
- [ ] **Link loss → outputs cut.** With the bot armed and driving, disconnect
      the dongle. Motors must stop within ~0.5 s. (Reconnect behaviour depends
      on the section-2 flag: OFF for matches = recovers; ON = latches a kill.)
- [ ] **Disarm → weapon safe.** Spin the weapon, then DISARM. Weapon must drop
      to safe immediately and the lock must re-engage.
- [ ] **Weapon lock.** While LOCKED, confirm no gamepad/keyboard input can spin
      the weapon.
- [ ] **Physical killswitch** (if fitted) cuts power as expected.

## 7. Drive and weapon function check

- [ ] **Drive direction correct**: forward drives forward, turns are the right
      way round. If it spins on the spot, fix `MOTOR_INVERT_*` (section 1).
- [ ] Weapon spins the intended direction and idle vs attack behave as expected.
      Use the wireless bench test for a controlled spin-up if you want a set %
      (`WEAPON TEST (BENCH)` section on the station - needs the password, and
      the SPIN button is a 5 s deadman).

## 8. Legality (already computed - confirm nothing changed)

- [ ] Pulley ratio **2:1** (confirmed), drum **85 mm**, **4S** pack.
- [ ] At 100% throttle this is **217 mph / 1,626 J**, inside the 250 mph /
      2,000 J limits. Full maths in `docs/hardware/weapon-limits.md`.
- [ ] Nothing on the weapon drivetrain has changed since that calculation. Any
      change to pulleys, drum, or pack **invalidates it** - recompute.

## 9. Ready to fight

- [ ] Teacher aware, area clear, everyone knows the bot is about to go live.
- [ ] Call it out loud, then **ARM**, then unlock the weapon when you mean it.

### Kill methods, quick reference

| Method | Effect | Recovery |
|---|---|---|
| Gamepad **B** / keyboard **F** / on-screen **KILL ROBOT** | Failsafe 255, deep sleep | Power-cycle, then RESET KILLSWITCH |
| Physical killswitch | Cuts power | Per hardware |
| Pull the dongle | Link loss, outputs cut (soft stop) | Recovers on reconnect (match), or kills if the section-2 flag is on |

**If in doubt, kill it.** There is no cost to stopping a fight; there is a real
cost to letting a ~1.6 kJ weapon run when something looks wrong.
